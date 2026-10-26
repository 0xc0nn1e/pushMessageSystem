from providers.common import post_json


async def push_line(msg, env, timeout_ms, send):
    token = env.get("LINE_CHANNEL_ACCESS_TOKEN")
    target = env.get("LINE_TARGET_ID")
    if not token or not target:
        return {"ok": False, "error": "line_not_configured"}
    return await post_json(
        "line",
        "https://api.line.me/v2/bot/message/push",
        {"content-type": "application/json", "authorization": f"Bearer {token}"},
        {"to": target, "messages": [{"type": "text", "text": msg}]},
        timeout_ms,
        send,
    )
