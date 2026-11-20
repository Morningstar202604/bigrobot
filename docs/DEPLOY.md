# Deployment

English · [中文](zh/DEPLOY.md)

This covers install, start-up, the QQ protocol side, verification, operations and common failures. Historical notes live in `docs/archive/`.

## Choose a path

| Situation | Path | Notes |
|---|---|---|
| Production, a VPS, long-running | **Docker** (recommended) | Ships its own runtime; host QQ version does not matter; one public port |
| Development, code changes, no Docker | Source (Python 3.12+) | `pip install -e .` then run |
| A Windows desktop, nothing installed | exe (not recommended) | Packaging is for "one file runs", not a deployment standard; data stays in `bigrobot-data/` |

```bash
pip install -e . && bigrobot init && bigrobot run
# open http://127.0.0.1:8010 and use the admin token printed by init
```

`bigrobot init` writes `.env` and two random tokens. `bigrobot run --gateway` also starts the protocol gateway. If something is wrong, run `bigrobot doctor` first: it reports actual state, including who owns the port and whether a key is configured.

## Prerequisites

| Item | Needed | Notes |
|---|---|---|
| Host | Yes | 1 core / 1 GB is enough; Docker installed |
| QQ account | QQ channel only | First login requires a QR scan on the deployment host |
| Model API key | Recommended | Any OpenAI-compatible endpoint; without one, rules and retrieval still run |
| Domain | Optional | Only for HTTPS or a memorable address |

## Docker in five steps

```bash
git clone --depth 1 https://gitcode.com/badhope/bigrobot.git /opt/bigrobot
bash /opt/bigrobot/scripts/deploy.sh       # first run creates .env and random tokens

vim /opt/bigrobot/.env                     # set NAPCAT_QQ and USER_LLM_API_KEY

bash /opt/bigrobot/scripts/deploy.sh       # build and start; core serves the console on 8010

# scan the QR code (section 4), then verify
curl http://127.0.0.1:8010/healthz          # {"ok":true}
```

Ports: `core 8010` (console and API), `gateway 8011`, `executor 8020` (internal only), NapCat WebUI `6099` (loopback only), NapCat WebSocket `3001` (compose network).

For a home server behind a tunnel, set `BIGROBOT_BIND=127.0.0.1` and point `cloudflared` or frp at `http://127.0.0.1:8010`; do not expose the host directly.

## Configuration

Resolution order: code defaults → environment → database. The console writes the database layer and changes apply immediately. All keys are in [`.env.example`](../.env.example). Since 2.0 the prefix is `BIGROBOT_*`; old `CS_AGENT_*` and `ZHIKE_*` names are mapped automatically.

## Connect QQ

| Situation | Path | Cost |
|---|---|---|
| No desktop QQ, or containers are fine | **Compose container** (recommended) | Ships its own QQ; host version does not matter |
| Container already running, fastest login | **Console QR** | No NapCat WebUI needed; token never reaches the browser |
| Desktop QQ already logged in, reuse credentials | **Local injection** | Sensitive to QQ version; a QQ update can silently break it |

### Container

```bash
docker compose -f docs/napcat-compose.yaml up -d
docker compose -f docs/napcat-compose.yaml logs -f napcat
# open http://127.0.0.1:6099/webui and scan (default token bigrobot-local; override with NAPCAT_WEBUI_TOKEN)
```

Data lives in `docs/data/` (credentials, config, plugins). Back it up to migrate; deleting `data/qq` requires a new scan. On Windows, `docker info` saying `cannot find the file specified` usually means Docker Desktop is not running or WSL/VirtualMachinePlatform is disabled. `python scripts/qq_doctor.py` separates those cases.

### Console QR

Set the WebUI URL and token, then use **Overview → Channels → QQ → Scan**:

```env
NAPCAT_WEBUI_URL=http://127.0.0.1:6099
NAPCAT_WEBUI_TOKEN=<token from the start log or the compose value>
```

The token stays in the core process; the browser never receives it. A QR code expires after about two minutes. The gateway connects automatically after a successful scan. A major NapCat upgrade can remove the internal endpoint; the console says so and falls back to the WebUI path.

### Local injection

```bash
python scripts/napcat_local.py start --qq <bot QQ>   # the desktop QQ session is replaced
python scripts/qq_doctor.py                          # decide which path this host should use
```

The injection package pins the QQ version. After an automatic QQ update, `QQ.exe` may start with about 20 MB of memory while 6099 and 3001 never listen and no new log file appears. The visible symptom is "nobody answers", while logs look normal. Treat local injection as version-sensitive; use the container instead of chasing version numbers.

### Gateway troubleshooting

1. Is `3001` listening (container network or firewall)?
2. Is the NapCat WebSocket server enabled with `messagePostFormat: array`?
3. Does the channel page show `onebot_v11` as `online`? `GET /api/channels/status` should list `bots` and `self_id`.
4. No reply to an @mention: check group pacing and the loop guard (`gateway/loop_guard.py`, on by default).

## Verification

Machine-checkable, no real QQ scan:

```bash
.venv/bin/python scripts/qq_e2e.py
python scripts/e2e_check.py --base-url http://127.0.0.1:8010
```

`e2e_check.py` writes sessions, messages and tickets and cleans them up. Run it only against an isolated instance.

Manual checklist:

- [ ] The bot account is online in NapCat after a QR scan.
- [ ] A direct message asking about the knowledge base returns promptly with a citation.
- [ ] Sending an image without a vision model produces a clear "cannot see images" response.
- [ ] An @mention in a group gets a reply; no @mention stays silent.
- [ ] "Hand off to a human" explains that only the bot is present.
- [ ] `POST /v1/ingest` without a token returns **401**.

## Operations

```bash
bash /opt/bigrobot/scripts/deploy.sh       # upgrade: pull and rebuild
docker logs -f bigrobot-core
docker logs -f bigrobot-gateway
```

Back up with `sqlite3 .backup`. In WAL mode a plain `cp` can capture a main file without the WAL:

```bash
docker run --rm -v bigrobot_core_data:/data -v "$PWD":/b alpine \
  sh -c 'apk add --no-cache sqlite >/dev/null && sqlite3 /data/bigrobot.db ".backup /b/backup.db"'
```

Rollback: `git -C /opt/bigrobot checkout <old tag or sha> && bash scripts/deploy.sh`.

Quarterly restore drill: stop core, restore with `.backup`, start core, check `/healthz`, then `/api/admin/audit/verify` should return `ok=true`; compare a few session and message counts with `/api/admin/overview`.

## Observability

| Endpoint | Use |
|---|---|
| `GET /healthz` | Liveness probe |
| `GET /readyz` | Readiness: schema version, KB count, LLM configured |
| `GET /metrics` | Prometheus: HTTP requests, latency, LLM calls, uptime |
| `GET /api/admin/logs` | Recent events in the console log centre |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Optional trace export (`requirements-tracing.txt`) |

Useful alerts: 5xx rate above 2%, LLM failure rate above 20%, p95 latency above 2s for a route.

## Production security baseline

- Keep the random tokens generated by the script; do not restore placeholders.
- For public deployments set `BIGROBOT_LOCAL_TOKEN_BOOTSTRAP=0` and disable local token bootstrap.
- When unsure, bind to `127.0.0.1` and put a reverse proxy or tunnel in front.
- Bind NapCat WebUI (6099) to loopback and reach it over an SSH tunnel.
- For a direct public origin, set `BIGROBOT_CORS_ORIGINS` to the console origin.
- The executor rejects `../`, `.env`, symlink escapes and shell metacharacters. `shell.exec`, `fs.delete` and `proc.kill` are destructive and require approval.

## Common failures

| Symptom | Fix |
|---|---|
| Gateway cannot reach the protocol | WS 3001 closed, wrong network, or `messagePostFormat` is not `array` |
| Login drops repeatedly | Use a fixed device, avoid restarting the container; the session is in the `napcat_data` volume |
| Console returns 401 | Local access should auto-login; remote access needs an access token; clear stale `localStorage` |
| Model has no effect | Test the LLM connection in admin settings; an empty `USER_LLM_API_KEY` means rules mode |
| Groups silent, direct messages work | Group pacing or loop guard; inspect `gateway/loop_guard.py` and channel stats |
| Data "disappeared" after upgrade | An old `zhike-data/` directory is being reused; confirm `BIGROBOT_HOME` |
