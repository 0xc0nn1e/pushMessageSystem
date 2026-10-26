"""Send a signed push request using only the Python standard library."""

import argparse
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("message")
    args = parser.parse_args()
    url = os.environ.get("PUSH_URL", "").rstrip("/")
    secret = os.environ.get("SIGN_SECRET", "")
    if not url or not secret:
        parser.error("Set PUSH_URL and SIGN_SECRET in the environment.")
    timestamp = str(int(time.time()))
    nonce = secrets.token_hex(12)
    body = json.dumps({"msg": args.message}, ensure_ascii=False).encode("utf-8")
    signature = base64.b64encode(
        hmac.new(
            secret.encode("utf-8"),
            f"{timestamp}.{nonce}.".encode("utf-8") + body,
            hashlib.sha256,
        ).digest()
    ).decode("ascii")
    request = urllib.request.Request(
        f"{url}/push", data=body, method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Timestamp": timestamp,
            "X-Nonce": nonce,
            "X-Signature": signature,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            print(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        print(exc.read().decode("utf-8"))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
