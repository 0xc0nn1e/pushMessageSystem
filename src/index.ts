import Fastify from "fastify";
import "dotenv/config";
import crypto from "node:crypto";
import { LRUCache } from "lru-cache";


const app = Fastify({ logger: true });
const port = Number(process.env.PORT ?? 3000);
const nonceCache = new LRUCache<string, true>({ max: 5000, ttl: Number(process.env.TIME_SKEW_SEC ?? 120) * 1000 });

app.addContentTypeParser("application/json", { parseAs: "string" }, (req, body, done) => {
  (req as any).rawBody = body;
  try { done(null, JSON.parse(body as string)); } catch (e) { done(e as Error); }
});

function timingSafeEqualB64(a: string, b: string) {
  const ab = Buffer.from(a);
  const bb = Buffer.from(b);
  if (ab.length !== bb.length) return false;
  return crypto.timingSafeEqual(ab, bb);
}
function sign(secret: string, payload: string) {
  return crypto.createHmac("sha256", secret).update(payload).digest("base64");
}


app.get("/health", async () => {
  return { ok: true };
});

app.post("/push", async (req, reply) => {
  const secret = process.env.SIGN_SECRET ?? "";
  if (!secret) return reply.code(500).send({ ok: false, error: "server_misconfig" });
  const ts = req.headers["x-timestamp"];
  const nonce = req.headers["x-nonce"];
  const sig = req.headers["x-signature"];
  if (typeof ts !== "string" || typeof nonce !== "string" || typeof sig !== "string") return reply.code(401).send({ ok: false, error: "missing_signature_headers" });
  const tsNum = Number(ts);
  if (!Number.isFinite(tsNum)) return reply.code(401).send({ ok: false, error: "bad_timestamp" });
  const now = Math.floor(Date.now() / 1000);
  const skew = Number(process.env.TIME_SKEW_SEC ?? 120);
  if (Math.abs(now - tsNum) > skew) return reply.code(401).send({ ok: false, error: "timestamp_out_of_window" });
  if (nonceCache.has(nonce)) return reply.code(401).send({ ok: false, error: "replay_detected" });
  nonceCache.set(nonce, true);
  const rawBody = (req as any).rawBody as string | undefined;
  if (!rawBody) return reply.code(400).send({ ok: false, error: "missing_raw_body" });
  const expected = sign(secret, `${ts}.${nonce}.${rawBody}`);
  if (!timingSafeEqualB64(expected, sig)) return reply.code(401).send({ ok: false, error: "invalid_signature" });
  const body = req.body as { msg?: string };
  const msg = body?.msg;
  if (typeof msg !== "string" || msg.length === 0) return reply.code(400).send({ ok: false, error: "missing_msg" });
  return { ok: true };
});


app.listen({ port, host: "127.0.0.1" })
  .then(() => {
    app.log.info(`listening on http://127.0.0.1:${port}`);
  })
  .catch(err => {
    app.log.error(err);
    process.exit(1);
  });
