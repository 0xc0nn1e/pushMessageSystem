async def post_json(prefix, url, headers, payload, timeout_ms, send):
    try:
        status = await send(url, headers, payload, timeout_ms)
        if not 200 <= status < 300:
            return {"ok": False, "error": f"{prefix}_http_{status}"}
        return {"ok": True}
    except TimeoutError:
        return {"ok": False, "error": f"{prefix}_timeout"}
    except Exception:
        return {"ok": False, "error": f"{prefix}_network"}
