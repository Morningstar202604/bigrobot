# Phone remote control

BigRobot follows the boundary of [ZCode Remote Control](https://zcode.z.ai/en/docs/remote-control): the desktop generates a QR code / link, and the phone joins the **whole console**, not a read-only mirror. Commands, files and the browser still run on the desktop machine.

## Use it

1. Click **Remote control** in the left sidebar on the desktop.
2. Pick a transport:
   - **Auto** — use `BIGROBOT_PUBLIC_URL` when set; otherwise try a localhost.run reverse tunnel; fall back to LAN direct.
   - **Direct only** — `BIGROBOT_PUBLIC_URL`, a reverse-proxy host, or the machine's LAN address.
   - **Tunnel only** — localhost.run, fail loudly if unavailable.
3. Click **Generate QR**. Scan it with the phone, or copy the link.
4. After pairing, the phone gets the full console. Closing the dialog does not disconnect; click **Stop remote** to end it.

## Security model

- The QR link carries a **one-time pairing token** in the URL fragment (`/remote#t=...`). Fragments are not sent in access logs or Referer. The token lives 5 minutes and is consumed once.
- Pairing returns a 12-hour temporary token. It grants admin rights and is kept only in the phone browser's localStorage.
- One phone at a time. Generating a new QR or refreshing immediately kicks the old phone.
- **Stop remote** clears the pairing token and all temporary tokens; the old phone gets 401 on its next request.
- Treat the link as a temporary key. Do not post it in a group. If it leaks, refresh.
- localhost.run terminates TLS on its side, so that service can see HTTP content in transit. Use it for temporary access only. For permanent use, set your own domain + HTTPS reverse proxy and `BIGROBOT_PUBLIC_URL`.

## Endpoints

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| `POST` | `/api/remote/start` | Admin | Issue a new pairing token; revoke the old phone |
| `GET` | `/api/remote/status` | Admin | Waiting / connected clients / tunnel state |
| `POST` | `/api/remote/pair` | Public (one-time token) | Exchange for a session token |
| `POST` | `/api/remote/stop` | Admin | Stop remote control and revoke every token |

Temporary tokens use `X-Admin-Token`, the same header as the local `ADMIN_TOKEN`.

## Environment

| Variable | Default | Purpose |
| --- | --- | --- |
| `BIGROBOT_PUBLIC_URL` | empty | Public origin, e.g. `https://robot.example.com`; disables the tunnel in auto mode |
| `BIGROBOT_REMOTE_TUNNEL` | `1` | Set `0` to forbid localhost.run |
| `BIGROBOT_REMOTE_SCHEME` | `http` | Scheme for direct links; set `https` behind TLS |

## Limits

- Temporary tokens live in process memory. Restarting the server forces every phone to re-pair.
- Free localhost.run hostnames rotate; use your own domain or tunnel for long-running access.
- The phone runs the same responsive React console. It is not a native app, and wide tables may scroll horizontally.
