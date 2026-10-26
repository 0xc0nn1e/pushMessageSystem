import asyncio
import base64
import hashlib
import hmac
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app import MAX_BODY_BYTES, handle_request


class AppTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = {"SIGN_SECRET": "test-secret"}
        self.claim = AsyncMock(return_value=True)
        self.telegram = AsyncMock(return_value={"ok": True})
        self.line = AsyncMock(return_value={"ok": True})
        self.body = b'{"msg":"hello"}'

    def headers(self, body=None, timestamp="1700000000", nonce="test-nonce"):
        body = self.body if body is None else body
        signature = base64.b64encode(hmac.new(
            b"test-secret", f"{timestamp}.{nonce}.".encode() + body, hashlib.sha256
        ).digest()).decode()
        return {
            "content-type": "application/json",
            "x-timestamp": timestamp, "x-nonce": nonce, "x-signature": signature,
        }

    async def call(self, *, body=None, headers=None, method="POST", path="/push"):
        return await handle_request(
            method, path, self.headers() if headers is None else headers,
            self.body if body is None else body,
            self.env, self.claim, self.telegram, self.line, now=1700000000.25,
        )

    async def test_health_and_head_need_no_configuration(self):
        self.env.clear()
        for method in ("GET", "HEAD"):
            self.assertEqual(await self.call(method=method, path="/health"), (200, {"ok": True}))
        self.claim.assert_not_awaited()
        self.telegram.assert_not_awaited()

    async def test_unknown_route_and_wrong_method(self):
        for method, path in (("GET", "/push"), ("POST", "/health"), ("POST", "/other")):
            self.assertEqual((await self.call(method=method, path=path))[0], 404)

    async def test_success_and_defaults(self):
        self.assertEqual(await self.call(), (
            200, {"ok": True, "tg": {"ok": True}, "line": {"ok": True}}
        ))
        self.telegram.assert_awaited_once_with("hello", self.env, 5000)
        self.assertEqual(self.claim.await_args.args[0], hashlib.sha256(b"test-nonce").hexdigest())

    async def test_node_signature_fixture_with_unicode_and_whitespace(self):
        body = '{ "msg": "Hello 世界\\nline 2" }'.encode()
        headers = self.headers(body, nonce="fixed-nonce")
        # Generated independently with Node.js crypto.createHmac.
        headers["x-signature"] = "kYu1r3vU3PpN4PSUqO3Q38KNlkGeT1R7Ea33B+ax8Fc="
        self.assertEqual((await self.call(body=body, headers=headers))[0], 200)
        self.telegram.assert_awaited_once_with("Hello 世界\nline 2", self.env, 5000)

    async def test_raw_body_must_match_without_reserialization(self):
        result = await self.call(body=b'{ "msg" : "hello" }')
        self.assertEqual(result, (401, {"ok": False, "error": "invalid_signature"}))
        self.claim.assert_not_awaited()

    async def test_missing_signature_headers(self):
        for key in ("x-timestamp", "x-nonce", "x-signature"):
            with self.subTest(key=key):
                headers = self.headers()
                del headers[key]
                self.assertEqual((await self.call(headers=headers))[1]["error"], "missing_signature_headers")
        self.claim.assert_not_awaited()
        self.telegram.assert_not_awaited()

    async def test_bad_timestamps_and_clock_window(self):
        for timestamp in ("bad", "NaN", "Infinity", "-Infinity"):
            with self.subTest(timestamp=timestamp):
                self.assertEqual((await self.call(headers=self.headers(timestamp=timestamp)))[1]["error"], "bad_timestamp")
        for timestamp in ("1699999879", "1700000121"):
            self.assertEqual((await self.call(headers=self.headers(timestamp=timestamp)))[1]["error"], "timestamp_out_of_window")
        self.claim.assert_not_awaited()

    async def test_timestamp_window_boundaries_and_future_retention(self):
        for timestamp in ("1699999880", "1700000120"):
            self.assertEqual((await self.call(headers=self.headers(timestamp=timestamp)))[0], 200)
        self.assertEqual(self.claim.await_args.args[1], 1700000241000)

    async def test_bad_signature_never_reserves_nonce(self):
        for value in ("invalid", "", "é"):
            headers = self.headers()
            headers["x-signature"] = value
            self.assertEqual((await self.call(headers=headers))[1]["error"], "invalid_signature")
        self.claim.assert_not_awaited()

    async def test_replay_and_storage_failure_never_send(self):
        self.claim.return_value = False
        self.assertEqual((await self.call())[1]["error"], "replay_detected")
        self.claim.side_effect = RuntimeError("private storage detail")
        self.assertEqual(await self.call(), (503, {"ok": False, "error": "replay_unavailable"}))
        self.telegram.assert_not_awaited()
        self.line.assert_not_awaited()

    async def test_invalid_json_and_content_type(self):
        for body in (b"{", b"", b'{"msg":NaN}', b"\xff"):
            self.assertEqual((await self.call(body=body))[1]["error"], "invalid_json")
        headers = self.headers()
        headers["content-type"] = "text/plain"
        self.assertEqual((await self.call(headers=headers))[0], 415)
        self.assertEqual((await self.call(body=b"x" * (MAX_BODY_BYTES + 1)))[0], 413)
        self.claim.assert_not_awaited()

    async def test_missing_messages_consume_verified_nonce(self):
        for value in ({}, {"msg": ""}, {"msg": 1}, [], None):
            body = json.dumps(value).encode()
            self.assertEqual((await self.call(body=body, headers=self.headers(body)))[1]["error"], "missing_msg")
        self.assertEqual(self.claim.await_count, 5)
        self.telegram.assert_not_awaited()

    async def test_configuration_errors(self):
        for setting, value in (
            ("SIGN_SECRET", ""), ("TIME_SKEW_SEC", "0"),
            ("TIME_SKEW_SEC", "bad"), ("SNS_TIMEOUT_MS", "-1"),
        ):
            with self.subTest(setting=setting):
                self.env = {"SIGN_SECRET": "test-secret", setting: value}
                self.assertEqual((await self.call())[1]["error"], "server_misconfig")
        self.claim.assert_not_awaited()

    async def test_providers_run_concurrently(self):
        started = asyncio.Event()
        async def telegram(*args):
            await asyncio.wait_for(started.wait(), 1)
            return {"ok": True}
        async def line(*args):
            started.set()
            return {"ok": False, "error": "line_timeout"}
        self.telegram = telegram
        self.line = line
        status, data = await self.call()
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["line"]["error"], "line_timeout")

    async def test_provider_crash_and_total_failure_keep_http_200(self):
        self.telegram.side_effect = RuntimeError("private provider details")
        self.line.return_value = {"ok": False, "error": "line_not_configured"}
        self.assertEqual(await self.call(), (
            200, {"ok": False, "tg": {"ok": False, "error": "tg_crash"},
                  "line": {"ok": False, "error": "line_not_configured"}}
        ))

    async def test_custom_timeout(self):
        self.env["SNS_TIMEOUT_MS"] = "250"
        await self.call()
        self.line.assert_awaited_once_with("hello", self.env, 250)
