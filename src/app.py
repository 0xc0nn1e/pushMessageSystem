import asyncio
import base64
import hashlib
import hmac
import json
import math
import time

import errors as err

MAX_BODY_BYTES = 1024 * 1024
ENV_KEYS = (
    "SIGN_SECRET",
    "TIME_SKEW_SEC",
    "SNS_TIMEOUT_MS",
    "TG_BOT_TOKEN",
    "TG_CHAT_ID",
    "LINE_CHANNEL_ACCESS_TOKEN",
    "LINE_TARGET_ID",
)


def failure(status, code):
    return status, {"ok": False, "error": code}


def reject_json_constant(value):
    # Python otherwise accepts NaN/Infinity, unlike JSON.parse.
    raise ValueError("Invalid JSON constant")


async def handle_request(
    method, path, headers, raw_body, env, claim_nonce, send_telegram, send_line,
    *, now=None,
):
    if path == "/health" and method in ("GET", "HEAD"):
        return 200, {"ok": True}
    if path != "/push" or method != "POST":
        return failure(404, err.NOT_FOUND)

    headers = {key.lower(): value for key, value in headers.items()}
    if len(raw_body) > MAX_BODY_BYTES:
        return failure(413, err.PAYLOAD_TOO_LARGE)
    media_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type != "application/json":
        return failure(415, err.UNSUPPORTED_MEDIA_TYPE)
    try:
        body = json.loads(raw_body.decode("utf-8"), parse_constant=reject_json_constant)
    except (UnicodeDecodeError, ValueError, RecursionError):
        return failure(400, err.INVALID_JSON)

    secret = env.get("SIGN_SECRET", "")
    try:
        skew = int(env.get("TIME_SKEW_SEC", "120"))
        timeout_ms = int(env.get("SNS_TIMEOUT_MS", "5000"))
        if not secret or skew <= 0 or not 0 < timeout_ms <= 2_147_483_647:
            raise ValueError("Invalid configuration")
    except (TypeError, ValueError):
        return failure(500, err.SERVER_MISCONFIG)

    timestamp = headers.get("x-timestamp")
    nonce = headers.get("x-nonce")
    signature = headers.get("x-signature")
    if not all(isinstance(value, str) for value in (timestamp, nonce, signature)):
        return failure(401, err.MISSING_SIGNATURE_HEADERS)
    try:
        timestamp_number = float(timestamp)
        if not math.isfinite(timestamp_number):
            raise ValueError("Invalid timestamp")
    except (ValueError, OverflowError):
        return failure(401, err.BAD_TIMESTAMP)
    now = time.time() if now is None else now
    if abs(math.floor(now) - timestamp_number) > skew:
        return failure(401, err.TIMESTAMP_OUT_OF_WINDOW)

    payload = f"{timestamp}.{nonce}.".encode("utf-8") + raw_body
    expected = base64.b64encode(
        hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()
    )
    if not hmac.compare_digest(expected, signature.encode("utf-8")):
        return failure(401, err.INVALID_SIGNATURE)

    # Keep future-dated requests reserved for their full acceptance window,
    # including the last second accepted by the integer-second clock check.
    expires_at_ms = math.ceil(max(now + skew, timestamp_number + skew + 1) * 1000)
    nonce_hash = hashlib.sha256(nonce.encode("utf-8")).hexdigest()
    try:
        accepted = await claim_nonce(nonce_hash, expires_at_ms)
    except Exception:
        # A storage outage must never bypass replay protection.
        return failure(503, err.REPLAY_UNAVAILABLE)
    if not accepted:
        return failure(401, err.REPLAY_DETECTED)

    msg = body.get("msg") if isinstance(body, dict) else None
    if not isinstance(msg, str) or not msg:
        return failure(400, err.MISSING_MSG)

    results = await asyncio.gather(
        send_telegram(msg, env, timeout_ms),
        send_line(msg, env, timeout_ms),
        return_exceptions=True,
    )
    tg, line = (
        {"ok": False, "error": f"{prefix}_crash"}
        if isinstance(result, BaseException) else result
        for prefix, result in zip(("tg", "line"), results)
    )
    return 200, {"ok": tg["ok"] or line["ok"], "tg": tg, "line": line}
