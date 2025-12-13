export async function pushLine(msg: string, timeoutMs: number) {
  const token = process.env.LINE_CHANNEL_ACCESS_TOKEN;
  const to = process.env.LINE_TO;
  if (!token || !to) {
    return { ok: false, error: "line_not_configured" as const };
  }

  const ac = new AbortController();
  const t = setTimeout(() => ac.abort(), timeoutMs);

  try {
    const res = await fetch("https://api.line.me/v2/bot/message/push", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "authorization": `Bearer ${token}`,
      },
      body: JSON.stringify({
        to,
        messages: [{ type: "text", text: msg }],
      }),
      signal: ac.signal,
    });

    if (!res.ok) {
      return { ok: false, error: `line_http_${res.status}` as const };
    }
    return { ok: true as const };
  } catch (e: any) {
    if (e?.name === "AbortError") return { ok: false, error: "line_timeout" as const };
    return { ok: false, error: "line_network" as const };
  } finally {
    clearTimeout(t);
  }
}
