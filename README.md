# BigRobot

[中文](README.zh.md) · **English**

A console for chat accounts you already run — not another bot framework.

Most chat bots are built to answer messages. BigRobot starts from the other side: it takes over an existing account, shows what is actually in it, and puts an AI secretary on top. QQ is the first channel because QQ has no usable backend — you log in and see nothing. Here you see the groups, the members, the files and the history, and you can act on them.

## What it does

| Area | What you get |
|---|---|
| Account takeover | Start the protocol, scan a QR code, keep it alive with a watchdog and restart backoff |
| Visibility | Group and direct-message history stored locally, member list with roles, group files, notices, friends |
| Action | Send text/image/voice/file, recall, mute, kick, edit card, publish notice |
| Voice | Audio kept with the message, transcoded to wav, transcribed, written back into the transcript |
| AI secretary | Tool calling with per-action risk levels, approvals, audit trail, knowledge base, reminders |
| Console | One account dialog, one session drawer, capability-driven UI instead of per-platform hardcoding |

## Design notes

**Capabilities, not platform names.** `core/adapters_registry.py` declares what a channel can do (`group.member_list`, `voice.transcribe`, …). The console renders from capabilities; adding a platform means adding a declaration, not editing the UI.

**Nothing pretends to work.** No protocol connection returns 409, unconfigured transcription returns 503, unsupported audio returns 422. A failed step is reported as failed instead of producing plausible-looking output.

**Additive migrations.** Schema changes add nullable columns first, and data is backfilled only where it can be known. Old sessions keep `account_id = NULL` rather than being filled with a guess.

## Quick start

```bash
pip install -r requirements.txt
ADMIN_TOKEN=change-me python -m uvicorn core.main:app --port 8010
```

Open `http://127.0.0.1:8010`. QQ needs a local protocol implementation (NapCat); the account dialog walks through deploy → start → scan. Details in [docs/DEPLOY.md](docs/DEPLOY.md).

## Verify

```bash
python scripts/full_check.py        # everything, ~4 min
python scripts/full_check.py --fast # skip the test suite
```

Backend tests, ruff, mypy, frontend lint/tests/build, route count and harness checks in one run — and it still prints a full report when something fails.

## Layout

```
core/      API, storage, agent loop, channel adapters
gateway/   bridge to the chat protocol
executor/  sandboxed action runner
frontend/  console (React)
docs/      current docs plus an archive — see docs/README.md
```

## Docs

[Deployment](docs/DEPLOY.md) · [Architecture](docs/ARCHITECTURE.md) · [Releasing](docs/RELEASING.md) · [Route audit](docs/route-audit.md) · [Persona eval](docs/PERSONA-EVAL.md)

## Status

Working: QQ account takeover, history, members, files, voice transcription, tool calling with approvals.
Not yet: a second channel implementation, and an end-to-end run against a live account in CI.

## License

MIT — see [LICENSE](LICENSE).
