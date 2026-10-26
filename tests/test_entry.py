import asyncio
import importlib
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# CPython cannot import Workers' JS bridge. Only the bridge is replaced here;
# local Wrangler smoke checks cover the real Worker and Durable Object.
with patch.dict(sys.modules, {
    "js": SimpleNamespace(AbortController=SimpleNamespace()),
    "workers": SimpleNamespace(
        DurableObject=type("DurableObject", (), {}),
        WorkerEntrypoint=type("WorkerEntrypoint", (), {}),
        Response=SimpleNamespace(), fetch=AsyncMock(),
    ),
}):
    entry = importlib.import_module("entry")


class EntryTests(unittest.IsolatedAsyncioTestCase):
    async def test_transport_timeout_aborts_fetch(self):
        signal = SimpleNamespace(aborted=False)
        aborted = asyncio.Event()
        def abort():
            signal.aborted = True
            aborted.set()
        controller = SimpleNamespace(signal=signal, abort=abort)
        async def fetch(*args, **kwargs):
            self.assertIs(kwargs["signal"], signal)
            await asyncio.wait_for(aborted.wait(), 1)
            raise OSError("AbortError")
        with patch.object(entry, "AbortController", SimpleNamespace(new=lambda: controller)), patch.object(entry, "fetch", fetch):
            with self.assertRaises(TimeoutError):
                await entry.send_json("https://example.invalid", {}, {}, 1)
        self.assertTrue(signal.aborted)

    async def test_transport_cancels_timer_and_response_body(self):
        signal = SimpleNamespace(aborted=False)
        abort = unittest.mock.Mock()
        body = SimpleNamespace(cancel=AsyncMock())
        response = SimpleNamespace(status=200, body=body)
        controller = SimpleNamespace(signal=signal, abort=abort)
        with patch.object(entry, "AbortController", SimpleNamespace(new=lambda: controller)), patch.object(entry, "fetch", AsyncMock(return_value=response)):
            self.assertEqual(await entry.send_json("https://example.invalid", {}, {}, 1), 200)
            await asyncio.sleep(0.01)
        abort.assert_not_called()
        body.cancel.assert_awaited_once()

    def reader(self, chunks):
        values = [
            SimpleNamespace(done=False, value=SimpleNamespace(
                byteLength=len(chunk), to_bytes=lambda value=chunk: value,
            ))
            for chunk in chunks
        ] + [SimpleNamespace(done=True)]
        return SimpleNamespace(
            read=AsyncMock(side_effect=values), cancel=AsyncMock(),
            releaseLock=unittest.mock.Mock(),
        )

    async def test_streamed_body_keeps_exact_bytes(self):
        reader = self.reader([b'{ "msg": ', '"世界" }'.encode()])
        request = SimpleNamespace(body=SimpleNamespace(getReader=lambda: reader))
        self.assertEqual(await entry.read_body(request), '{ "msg": "世界" }'.encode())
        reader.releaseLock.assert_called_once()

    async def test_streamed_body_limit_cancels_reader(self):
        reader = self.reader([b"x" * entry.MAX_BODY_BYTES, b"x"])
        request = SimpleNamespace(body=SimpleNamespace(getReader=lambda: reader))
        with self.assertRaisesRegex(ValueError, "payload_too_large"):
            await entry.read_body(request)
        reader.cancel.assert_awaited_once()
        reader.releaseLock.assert_called_once()
