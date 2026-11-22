# Documentation

English · [中文](zh/README.md)

## Current

Update these when the code changes.

| Document | Purpose |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Process model and layer responsibilities: core, gateway, executor |
| [DEPLOY.md](DEPLOY.md) | Install, start, QQ protocol side, verification, operations |
| [RELEASING.md](RELEASING.md) | Versioning and release steps |
| [route-audit.md](route-audit.md) | How routes are checked for real consumers |
| [PERSONA-EVAL.md](PERSONA-EVAL.md) | Persona evaluation methods and results |
| [COMPARISON.md](COMPARISON.md) | Product boundary: what BigRobot is and is not |
| [extensions.md](extensions.md) | Declarative HTTP packs and the MCP client |
| [knowledge-base.md](knowledge-base.md) | Collections, persona binding and ingestion |
| [future-tasks.md](future-tasks.md) | Schedule an agent run and deliver the result |
| [channel-events.md](channel-events.md) | Notices, requests and recall soft-delete |
| [multi-account.md](multi-account.md) | Session, memory and action isolation per bot account |
| [persona-capabilities.md](persona-capabilities.md) | Per-persona tool, skill, MCP and extension scope |
| [LOCAL-MODELS.md](LOCAL-MODELS.md) | Download, run and switch to a sub-2B local model |
| [remote-control.md](remote-control.md) | Phone remote control: pairing, security model and limits |

## Archive

`docs/archive/` keeps early `*-v1.md` notes and competitor research. It records what was believed at the time; commands and entry points may be stale. Do not follow them.

## Assets

| Path | Content |
|---|---|
| `docs/screenshots/` | Console screenshots produced by `scripts/take_screenshots.py` |
| `docs/media/` | Demo media |
| `docs/logo*.svg`, `docs/og-1200x630.png` | Brand assets |
| `docs/index.html` | Project landing page |
| `docs/napcat-compose.yaml` | Protocol-side compose example |

## Conventions

1. Put current docs at the root of `docs/`; history goes in `archive/`.
2. If a document references a script, changing the script means changing the document.
3. Screenshots are generated, not hand-edited.
4. Chinese translations live under `docs/zh/` and link back to the English page.
