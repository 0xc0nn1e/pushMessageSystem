import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from providers.line import push_line
from providers.telegram import push_telegram


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = {
            "TG_BOT_TOKEN": "dummy-token", "TG_CHAT_ID": "dummy-chat",
            "LINE_CHANNEL_ACCESS_TOKEN": "dummy-token", "LINE_TARGET_ID": "dummy-target",
        }
        self.send = AsyncMock(return_value=200)

    async def test_missing_configuration_never_calls_network(self):
        for provider, prefix in ((push_telegram, "tg"), (push_line, "line")):
            self.assertEqual(await provider("hello", {}, 5000, self.send),
                             {"ok": False, "error": f"{prefix}_not_configured"})
        self.send.assert_not_awaited()

    async def test_telegram_payload(self):
        self.assertEqual(await push_telegram("hello\n世界", self.env, 250, self.send), {"ok": True})
        self.send.assert_awaited_once_with(
            "https://api.telegram.org/botdummy-token/sendMessage",
            {"content-type": "application/json"},
            {"chat_id": "dummy-chat", "text": "hello\n世界"}, 250,
        )

    async def test_line_payload(self):
        self.assertEqual(await push_line("hello", self.env, 5000, self.send), {"ok": True})
        self.send.assert_awaited_once_with(
            "https://api.line.me/v2/bot/message/push",
            {"content-type": "application/json", "authorization": "Bearer dummy-token"},
            {"to": "dummy-target", "messages": [{"type": "text", "text": "hello"}]}, 5000,
        )

    async def test_http_errors_timeouts_and_network_errors(self):
        for provider, prefix in ((push_telegram, "tg"), (push_line, "line")):
            for status in (400, 401, 429, 500):
                self.send = AsyncMock(return_value=status)
                self.assertEqual(await provider("hello", self.env, 5000, self.send),
                                 {"ok": False, "error": f"{prefix}_http_{status}"})
            for error, suffix in ((TimeoutError(), "timeout"), (OSError("private detail"), "network")):
                self.send = AsyncMock(side_effect=error)
                self.assertEqual(await provider("hello", self.env, 5000, self.send),
                                 {"ok": False, "error": f"{prefix}_{suffix}"})
