# Security policy

English · [中文](SECURITY.zh.md)

## Reporting a vulnerability

Do **not** disclose details in a public issue. Use GitHub's
[private vulnerability reporting](https://github.com/badhope/bigrobot/security/advisories/new), or open an issue with no details asking for a private channel.

Include the affected version, reproduction steps and impact. We fix first, then disclose after a fix is available.

## Supported versions

Security fixes apply to the latest commit on `main`.

## Deployment checklist

- Set `ADMIN_TOKEN` and `CHANNEL_TOKEN` in production. Without them, admin APIs and `/v1/ingest` run in development mode.
- On a public host, set `BIGROBOT_LOCAL_TOKEN_BOOTSTRAP=0` to disable local token bootstrap.
- The executor listens on loopback by default. Set `EXECUTOR_TOKEN` before binding it to `0.0.0.0`.
- Bind NapCat WebUI (6099) and OneBot (3001) to `127.0.0.1`; never map them to the public internet.
- `AUTHORIZED_QQ` is the only account allowed to reach privileged tools such as file access or sending as the bot.

## Boundaries in this repository

- No keys, tokens, real accounts or chat logs are committed. `.gitignore` excludes `*.db`, `.env`, `logs/` and `out/`.
- LLM keys entered in the console are Fernet-encrypted in SQLite and always masked on read. Keys from environment variables are never stored.
- Actions are tiered: read-only, reversible write and destructive write with forced approval. Every decision is in a SHA-256 hash chain.
