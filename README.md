Push Message System
---


A lightweight, signed HTTP push service that forwards messages to Telegram and LINE.
Designed for server-side alerts, cron jobs, trading bots, and internal systems.

## screenshot

<img src="https://flight.connie.hk/static/img/pushup_tg.jpg" height="500"><img src="https://flight.connie.hk/static/img/pushup_line.jpg" height="500">
<br/>Both TG and Line


### Overview

- Tech stack: Node.js + Fastify + TypeScript
- Auth: HMAC-SHA256 signed requests
- Transport: HTTPS (behind Caddy + Cloudflare)
- Supports:
  - Telegram Bot API
  - LINE Notify / Messaging API
- Replay protection with timestamp + nonce
- Production-ready (systemd, reverse proxy)

Architecture
 ---

```
Client
↓ (signed request)
Cloudflare
↓
Caddy (reverse proxy, port 80)
↓
Node.js service (port 3000, internal only)
```


### Server

- Listens on `0.0.0.0:3000`
- **Not exposed directly to the internet**
- Only accessible via reverse proxy

API
---

### Base URL
```
$PUSH_URL   # e.g. https://your-domain.example
```


## Health Check
### GET `/health`

### Used for:
1. uptime monitoring
2. load balancer / reverse proxy checks

### Response

```bash
{
  "ok": true
}
```

## Push Message API

### POST `/push`

### Used for:
1. Send a message to **Telegram** and **LINE**.


### Headers (Required)

| Header        | Description                          |
|---------------|--------------------------------------|
| `Content-Type`  | application/json                     |
| `X-Timestamp`   | Unix timestamp (seconds)             |
| `X-Nonce `      | Random unique string                 |
| `X-Signature`   | HMAC-SHA256 signature (Base64)       |

---
### Request Body 
```
{
  "msg": "Your message text"
}
```
1. msg must be a non-empty string
2. UTF-8 supported
3. Newlines allowed (\n)

---
### Signature Generation
```

{timestamp}.{nonce}.{raw_body}

```
### HMAC:
1. Algorithm: HMAC-SHA256
2. Key: SIGN_SECRET
3. Output: Base64

### Example (Node.js)
```
require("dotenv").config();
const crypto = require("crypto");

const ts = Math.floor(Date.now() / 1000).toString();
const nonce = crypto.randomBytes(12).toString("hex");
const body = JSON.stringify({ msg: "test message" });

const sig = crypto
  .createHmac("sha256", process.env.SIGN_SECRET)
  .update(`${ts}.${nonce}.${body}`)
  .digest("base64");

console.log({ ts, nonce, sig });
```
---
### Example Request
```

curl -X POST "$PUSH_URL/push" \
  -H "Content-Type: application/json" \
  -H "X-Timestamp: 1765696399" \
  -H "X-Nonce: 1b08ae1f5308fa4e412bd5f8" \
  -H "X-Signature: e4fOx+I5ow/v9olLrRw8PapzZjpkzupOHY5GgRIVPMk=" \
  -d '{"msg":"Hello from push-message-system"}'

```

---
### Shell Example Request
```

#!/bin/bash
[ -z "$SSH_CONNECTION" ] && return
[ -z "$SSH_TTY" ] && return
API_SECRET="API_SECRET"
PUSH_URL="${PUSH_URL:-https://your-domain.example}"
IP="$(echo "$SSH_CONNECTION" | awk '{print $1}')"
HOSTNAME="$(hostname)"
USER="$(whoami)"
NOW="$(date '+%Y-%m-%d %H:%M:%S')"
MSG="[Login][$HOSTNAME] user=$USER ip=$IP time=$NOW"
TS="$(date +%s)"
NONCE="$(head /dev/urandom | tr -dc A-Za-z0-9 | head -c 16)"
MSG_ESCAPED="$(printf '%s' "$MSG" | sed 's/\\/\\\\/g;s/"/\\"/g')"
RAWBODY="$(printf '{"msg":"%s"}' "$MSG_ESCAPED")"
PAYLOAD="$(printf '%s.%s.%s' "$TS" "$NONCE" "$RAWBODY")"
SIG="$(printf '%s' "$PAYLOAD" | openssl dgst -sha256 -hmac "$API_SECRET" -binary | base64 -w 0)"
curl -s -X POST "$PUSH_URL/push" -H 'content-type: application/json' -H "X-Timestamp: $TS" -H "X-Nonce: $NONCE" -H "X-Signature: $SIG" --data-binary "$RAWBODY" >/dev/null 2>&1 || true

```

### Success Response
```

{
  "ok": true,
  "tg": { "ok": true },
  "line": { "ok": true }
}

```

### Error Responses

| HTTP | error                     | Meaning                       |
|------|---------------------------|-------------------------------|
| 400  | `missing_msg`             | Request body missing `msg`    |
| 401  | `missing_signature_headers` | Signature headers missing     |
| 401  | `bad_timestamp`           | Invalid timestamp             |
| 401  | `timestamp_out_of_window` | Timestamp expired             |
| 401  | `replay_detected`         | Nonce already used            |
| 401  | `invalid_signature`       | Signature mismatch            |
| 500  | `server_misconfig`        | Missing env config            |

## Environment Variables
```

PORT=3000

# Signature
SIGN_SECRET=your_shared_secret
TIME_SKEW_SEC=120

# Telegram
TG_BOT_TOKEN=xxxxx
TG_CHAT_ID=xxxxx

# LINE
LINE_CHANNEL_ACCESS_TOKEN=xxxxx
LINE_TARGET_ID=xxxxx

# Client (used by the request examples, not the server)
PUSH_URL=https://your-domain.example

```

## Development

```bash
pnpm install
pnpm dev
```

Runs with:
- hot reload (tsx)
- listens on 0.0.0.0:3000

## Production

```bash
pnpm install --frozen-lockfile
pnpm build
pnpm start
```

Recommended:
- behind Caddy / Nginx
- Cloudflare in front

## Production systemd setting

```bash

sudo /etc/systemd/system/push-message-system.service

[Unit]
Description=push-message-system
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=user
WorkingDirectory=/home/user/apps/push-message-system
Environment=NODE_ENV=production
ExecStart=/home/user/.nvm/versions/node/v24.12.0/bin/node dist/index.js
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target

```

## Production update

```bash

git pull
pnpm install --frozen-lockfile
pnpm build
sudo systemctl restart push-message-system

```

## Security Notes
- All requests must be signed

- Timestamp + nonce prevents replay attacks

- Node service not exposed directly to internet

### License
Private / Internal Use