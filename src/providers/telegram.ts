export async function pushTelegram(msg: string, timeoutMs: number) {
  const token = process.env.TG_BOT_TOKEN;
  const chatId = process.env.TG_CHAT_ID;
  if (!token || !chatId) {
    return { ok: false, error: "tg_not_configured" as const };
  }

  const ac = new AbortController();
  const t = setTimeout(() => ac.abort(), timeoutMs);

  try {
    const res = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ chat_id: chatId, text: msg }),
      signal: ac.signal,
    });

    if (!res.ok) {
      return { ok: false, error: `tg_http_${res.status}` as const };
    }
    return { ok: true as const };
  } catch (e: any) {
    if (e?.name === "AbortError") return { ok: false, error: "tg_timeout" as const };
    return { ok: false, error: "tg_network" as const };
  } finally {
    clearTimeout(t);
  }
}
