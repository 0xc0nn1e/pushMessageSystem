# Push Message System

A signed HTTP push service written in Python and hosted on Cloudflare Workers.
It forwards text messages to Telegram and the LINE Messaging API.

<img src="https://flight.connie.hk/static/img/pushup_tg.jpg" height="500"><img src="https://flight.connie.hk/static/img/pushup_line.jpg" height="500">

## Architecture

```text
Client -- HTTPS + HMAC-SHA256 --> Python Worker
                                  |-- Durable Object: reserve nonce atomically
                                  |-- Telegram Bot API
                                  `-- LINE Messaging API
```

The application runs in Cloudflare's Python runtime. There is no application
server to start, listening port to expose, or systemd/reverse-proxy service to
manage. Node.js is still needed locally by Cloudflare's Wrangler tooling.

Each verified request reserves its nonce in a SQLite-backed Durable Object
before sending. All Worker instances share the same object, so concurrent
requests cannot reuse a nonce. Records survive Worker restarts and are kept
for at least `TIME_SKEW_SEC`, and until the signed timestamp's entire acceptance
window ends. Expired records are removed on the next verified request.
Only nonce hashes and expiry times are stored, never messages or credentials.
This is replay protection, not a message queue or delivery retry mechanism.

## Local development

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and a
Node.js version supported by Wrangler. uv manages the project's Python 3.12
environment; Cloudflare selects its Python runtime from the compatibility date.

```bash
uv sync --locked
cp .dev.vars.example .dev.vars
```

Set a local `SIGN_SECRET` in `.dev.vars`. Leave provider credentials blank
when checking authentication without sending messages. Then start the Worker:

```bash
uv run pywrangler dev
```

The local endpoint is `http://127.0.0.1:8787`. Wrangler emulates Durable Objects
locally and persists their data under `.wrangler/`. No Cloudflare login is
needed for these local checks. The first run downloads runtime dependencies.

```bash
curl http://127.0.0.1:8787/health
uv run python -m unittest discover -s tests -v
uv run pywrangler deploy --dry-run
```

The test suite uses mocked outbound requests and SQLite fixtures. It never
sends Telegram or LINE messages. The dry run bundles the Worker without
deploying it.

## Configuration

Non-secret defaults are in `wrangler.toml`. Local secrets belong in the ignored
`.dev.vars` file. Production credentials use Worker secrets.

| Name | Default / purpose |
| --- | --- |
| `SIGN_SECRET` | Required shared HMAC secret |
| `TIME_SKEW_SEC` | `120`; positive integer clock window, in seconds |
| `SNS_TIMEOUT_MS` | `5000`; positive integer timeout per provider, in milliseconds |
| `TG_BOT_TOKEN` | Telegram bot token |
| `TG_CHAT_ID` | Telegram chat/channel ID |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Messaging API access token |
| `LINE_TARGET_ID` | LINE user/group ID |
| `NONCES` | Durable Object binding configured in Wrangler |

Each provider requires both of its configuration values. An unconfigured
provider reports `tg_not_configured` or `line_not_configured` without making
a network request. `PUSH_URL` is a client setting only; `PORT` is no longer used.
Do not commit secrets, local runtime state, or generated dependency folders.

## API

### GET /health

Returns HTTP 200 with `{"ok": true}`. It requires no signature and does not
check provider credentials or storage. `HEAD /health` returns an empty body.

### POST /push

Send `Content-Type: application/json` and a UTF-8 JSON body, up to 1 MiB:

```json
{"msg": "Your message text"}
```

`msg` must be a non-empty string. Unicode and newlines are supported.

| Header | Value |
| --- | --- |
| `X-Timestamp` | Unix timestamp in seconds |
| `X-Nonce` | Fresh random string for each request |
| `X-Signature` | Base64-encoded HMAC-SHA256 signature |

Calculate the signature with `SIGN_SECRET` over the UTF-8 bytes of:

```text
{timestamp}.{nonce}.{raw_body}
```

The raw body must match the bytes sent, including whitespace. Do not sign
parsed/reformatted JSON. The protocol is unchanged from the Node.js service,
so existing correctly signed clients continue to work.

Providers run concurrently. The response remains HTTP 200 after dispatch,
including when both providers fail:

```json
{
  "ok": true,
  "tg": {"ok": true},
  "line": {"ok": false, "error": "line_timeout"}
}
```

Top-level `ok` is true if either provider succeeds. A failed provider does not
cancel the other one. Errors include `*_not_configured`, `*_http_<status>`,
`*_timeout`, `*_network`, and `*_crash`, with `tg` or `line` prefixes.
A nonce remains consumed even if the message is invalid or delivery fails.

### Send from Python

`scripts/send.py` uses only the Python standard library. Set `PUSH_URL` and
`SIGN_SECRET` in your shell or secret manager, then run:

```bash
export PUSH_URL=http://127.0.0.1:8787
# Set SIGN_SECRET to match the server without placing it in shell history.
uv run python scripts/send.py "Hello from Python"
```

The script generates a fresh timestamp and nonce, signs the exact body,
sends it, and prints the JSON response. This command sends real messages
if the target Worker has provider credentials configured.

### Errors

Application errors use `{"ok": false, "error": "<code>"}`.

| HTTP | Error | Meaning |
| --- | --- | --- |
| 400 | `missing_msg` | Missing, empty, or non-string message |
| 400 | `invalid_json` | Invalid JSON or UTF-8 |
| 401 | `missing_signature_headers` | A required signature header is missing |
| 401 | `bad_timestamp` | Timestamp is not a finite number |
| 401 | `timestamp_out_of_window` | Timestamp is outside the accepted window |
| 401 | `invalid_signature` | Signature does not match the raw body |
| 401 | `replay_detected` | Nonce has already been reserved |
| 404 | `not_found` | Unknown route or unsupported method |
| 413 | `payload_too_large` | Request body exceeds 1 MiB |
| 415 | `unsupported_media_type` | Content type is not application/json |
| 500 | `server_misconfig` | Missing signing secret or invalid numeric configuration |
| 503 | `replay_unavailable` | Nonce storage failed; no messages were sent |

Input/routing errors now use this JSON envelope instead of Fastify-generated
parser messages. Existing authentication and provider error codes are retained.

## Deploy to Cloudflare

Review the Worker name and compatibility date in `wrangler.toml`, then:

```bash
uv run pywrangler login
uv run pywrangler deploy
uv run pywrangler secret put SIGN_SECRET
uv run pywrangler secret put TG_BOT_TOKEN
uv run pywrangler secret put TG_CHAT_ID
uv run pywrangler secret put LINE_CHANNEL_ACCESS_TOKEN
uv run pywrangler secret put LINE_TARGET_ID
```

The first deployment creates the Worker and its SQLite Durable Object via
migration `v1`. Push requests fail closed until `SIGN_SECRET` is configured.
Configure at least one provider before directing clients to the Worker.
Enter secret values at the prompts; skip both secrets for unused providers.

Use the HTTPS `workers.dev` URL printed by Wrangler, or configure a Worker
custom domain, as the client `PUSH_URL`. Custom domains are not preconfigured
in this repository. Further releases use `uv run pywrangler deploy`.

Keep the `NONCES` binding, `NonceStore` class, migration history, and
`push-nonces-v1` object name stable so releases retain replay state.
Do not replace this storage with an isolate-local dictionary or an eventually
consistent cache.

### Migrating from the Node.js service

1. Retain the existing shared signing secret and provider configuration.
2. Configure and validate the Worker before changing client URLs.
3. The old in-memory nonce cache cannot be transferred. To preserve replay
   protection across cutover, stop old ingress and let the full timestamp
   window drain before admitting requests to the Worker
   (`2 * TIME_SKEW_SEC + 1` seconds covers future-dated requests).
4. Update `PUSH_URL` and stop the old Node.js service after cutover.

The pnpm/TypeScript build and systemd deployment are replaced by
`pyproject.toml`, `uv.lock`, the runtime `pylock.toml` generated by pywrangler,
and `wrangler.toml`. No changes to the old production host are performed by
this repository's local development commands.

## References

- [Cloudflare Python Workers](https://developers.cloudflare.com/workers/languages/python/)
- [SQLite Durable Object storage](https://developers.cloudflare.com/durable-objects/api/sqlite-storage-api/)
- [Worker secrets](https://developers.cloudflare.com/workers/configuration/secrets/)

## License

Private / Internal Use.
