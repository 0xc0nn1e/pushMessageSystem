from providers.common import post_json


async def push_telegram(msg, env, timeout_ms, send):
    token = env.get("TG_BOT_TOKEN")
    chat_id = env.get("TG_CHAT_ID")
    if not token or not chat_id:
        return {"ok": False, "error": "tg_not_configured"}
    return await post_json(
        "tg",
        f"https://api.telegram.org/bot{token}/sendMessage",
        {"content-type": "application/json"},
        {"chat_id": chat_id, "text": msg},
        timeout_ms,
        send,
    )
