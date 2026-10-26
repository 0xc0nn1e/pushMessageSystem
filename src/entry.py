import asyncio
import json
import time
from functools import partial
from urllib.parse import urlsplit

from js import AbortController
from workers import DurableObject, Response, WorkerEntrypoint, fetch

from app import ENV_KEYS, MAX_BODY_BYTES, handle_request
from errors import PAYLOAD_TOO_LARGE
from providers.line import push_line
from providers.telegram import push_telegram
from replay import initialize, reserve


async def send_json(url, headers, payload, timeout_ms):
    controller = AbortController.new()
    timer = asyncio.get_running_loop().call_later(
        timeout_ms / 1000, controller.abort
    )
    try:
        response = await fetch(
            url, method="POST", headers=headers,
            body=json.dumps(payload), signal=controller.signal,
        )
        status = response.status
        # Provider response bodies are unused. Release their streams.
        if response.body is not None:
            await response.body.cancel()
        return status
    except Exception:
        if controller.signal.aborted:
            raise TimeoutError("Provider timeout") from None
        raise
    finally:
        timer.cancel()


async def read_body(request):
    # Enforce the old Fastify 1 MiB limit even without Content-Length.
    if request.body is None:
        return b""
    reader = request.body.getReader()
    chunks = []
    size = 0
    try:
        while True:
            chunk = await reader.read()
            if chunk.done:
                break
            size += chunk.value.byteLength
            if size > MAX_BODY_BYTES:
                await reader.cancel()
                raise ValueError(PAYLOAD_TOO_LARGE)
            chunks.append(chunk.value.to_bytes())
    finally:
        reader.releaseLock()
    return b"".join(chunks)


class NonceStore(DurableObject):
    def __init__(self, ctx, env):
        super().__init__(ctx, env)
        initialize(self.ctx.storage.sql)

    async def claim(self, nonce_hash, expires_at_ms):
        return reserve(
            self.ctx.storage.sql, nonce_hash, expires_at_ms,
            int(time.time() * 1000),
        )


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        path = urlsplit(request.url).path
        raw_body = b""
        if request.method == "POST" and path == "/push":
            try:
                raw_body = await read_body(request)
            except ValueError:
                return Response.json(
                    {"ok": False, "error": PAYLOAD_TOO_LARGE}, status=413
                )

        defaults = {"TIME_SKEW_SEC": "120", "SNS_TIMEOUT_MS": "5000"}
        env = {
            key: getattr(self.env, key, defaults.get(key, ""))
            for key in ENV_KEYS
        }

        async def claim_nonce(nonce_hash, expires_at_ms):
            # All isolates use the same stable object. Never rename it during
            # ordinary releases, or outstanding nonces would be forgotten.
            namespace = self.env.NONCES
            stub = namespace.get(namespace.idFromName("push-nonces-v1"))
            return await stub.claim(nonce_hash, expires_at_ms)

        status, data = await handle_request(
            request.method, path, request.headers, raw_body, env, claim_nonce,
            partial(push_telegram, send=send_json),
            partial(push_line, send=send_json),
        )
        if request.method == "HEAD":
            return Response(None, status=status, headers={"content-type": "application/json"})
        return Response.json(data, status=status)
