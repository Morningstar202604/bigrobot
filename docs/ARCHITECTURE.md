# Architecture

English · [中文](zh/ARCHITECTURE.md)

## Processes

```
QQ user ── NapCat ──▶ OneBot v11
                         │ reverse WebSocket
                         ▼
                    gateway (NoneBot2 + human-like layer)
                    · group pacing / ping-pong guard / sticker learning
                    · optional voice transcription
                         │ HTTP /v1/ingest (CHANNEL_TOKEN)
                         ▼
Web visitor ───────▶ core (FastAPI; serves the console on the same port)
                     · pipeline: annotation → tools → LLM → rules
                     · retrieval: FTS5 + optional vectors + RRF
                     · store: SQLite + versioned migrations
                     · actions: risk tiers + approvals + audit chain
                         │ HTTP (EXECUTOR_TOKEN)
                         ▼
                    executor (optional desktop runner)
                    · path allowlist / command allowlist
```

The three processes can be deployed separately. `core` alone is enough when `BIGROBOT_STATIC_DIR` serves the built frontend on one port.

## Core map

```
core/
├─ main.py            FastAPI assembly: middleware, auth dependencies, REST routes, WebSockets
├─ api/               route package (auth dependencies, knowledge-base API)
├─ pipeline.py        message path: prepare → route → engine → output gate
├─ llm.py             model client: failover race, protocol fallback, streaming
├─ agent_loop.py      multi-step ReAct: budgets, cancellation, repeat detection
├─ agent_llm.py       single-step decision (function calling with JSON fallback)
├─ tools.py           tool registry and rule-based routing
├─ retrieval.py       FTS5 BM25 + optional sqlite-vec + RRF fusion
├─ store.py           single-file SQLite store with versioned migrations
├─ migrations.py      schema version management
├─ config.py          runtime config (code defaults ← env ← DB, cached)
├─ personas.py        built-in persona presets
├─ ws_hub.py          WebSocket hub (broadcast and cleanup)
├─ kb_store.py        knowledge-base file store (cross-process lock, atomic writes)
├─ spa.py             frontend hosting (immutable cache, traversal guard)
├─ metrics.py         Prometheus metrics
├─ request_id.py      request correlation via contextvars
├─ events_log.py      in-memory ring plus rotating file log
├─ tracing.py         optional OpenTelemetry GenAI spans
├─ security.py        constant-time comparison and token checks
├─ ratelimit.py       SQLite sliding-window rate limit shared by workers
├─ guardrail.py       input and output injection guard
├─ quality.py         output discriminator and one rewrite pass
├─ ensemble.py        multi-model selection by rule score
├─ intent.py          intent classification
├─ websearch.py       search backends with a fallback race
├─ docparse.py        document parsing and chunking
├─ url_guard.py       SSRF protection (DNS checks and redirect re-checks)
├─ asr.py             speech transcription (faster-whisper or an external command)
├─ mcp_server.py      MCP tool exposure
└─ actions/           action layer
   ├─ registry.py     action list and risk tiers
   ├─ authz.py        subject × risk × tier → decision
   ├─ service.py      execution, idempotency, approvals, audit
   ├─ client.py       protocol-side calls
   └─ computer.py     desktop executor client
```

## Message path

1. A channel calls `POST /v1/ingest` with `CHANNEL_TOKEN`.
2. `sessions.resolve_session` finds or creates a session for the chat and account. A session has a TTL and carries context when it changes.
3. `store.add_message` stores the visitor message.
4. `pipeline.run`:
   - `_prepare`: truncation, persona card, input hooks, memory opt-out, web-search decision, context build, skills/profile/intent, injection guard, handoff decision, image capability check.
   - `_run_body`: annotation, sticker shortcut, tool shortcut, URL/file prefetch, engine (LLM ensemble or rules), output gate, output hooks.
5. Store the agent message, write audit rows, open a ticket when needed, broadcast over WebSocket.
6. Return `reply`; the gateway decides whether to speak (`no_model` and `rate_limited` stay silent).

### Two persona layers

- **Built-in cards** (`core/data/characters/<id>.json`, read-only): structured canon for the presets. `core/character.py` renders them in a fixed order; `core/character_guard.py` compares rendered output and checks consistency at the output gate.
- **Session-bound cards** (SQLite `character_cards` and `card_bindings`, console CRUD): user-authored cards imported from SillyTavern V2 or written in the console. They override `context.persona` per session and are not forced through the built-in consistency guard.

The split keeps one source of truth for each kind of card: built-in facts are maintained and checked by the project, user cards belong to their author.

### Gateway resilience

- Gateway → NapCat: NoneBot reconnects the forward WebSocket; messages are deduplicated by `message_id` with an LRU.
- Gateway → core: ingest retries once on a network error, then schedules a delayed retry (`GATEWAY_INGEST_RETRY_DELAY`, default 30s, concurrency capped). A short core restart does not lose messages.
- The gateway reports a heartbeat every 30s and uses the shared HTTP pool for core calls.

### Retrieval

```
query
 ├─ empty / stop-words only → []
 ├─ FTS5 index (bigram expansion, AND→OR, coverage gate)
 ├─ vector index (optional, cosine gate)
 └─ RRF fusion → absolute score calibration → overlap filter → top_k
       ↓ index unavailable
     bigram fallback
```

### Actions

```
tool call
 → actions_service.execute
   → validate_params
   → idempotency check (replay only terminal states)
   → authz.decide (destructive actions always need approval; agent permission = min(deployment tier, requester tier))
   → audit row (redacted parameters and digest)
   → execute or open an approval
 → observation (truncated and scanned for injection)
```

## Configuration order

```
code defaults  <  .env (python-dotenv, does not overwrite existing env)  <  process env  <  SQLite config table
```

`config.get_config()` caches on `(config_version, LLM key fingerprint)`. A DB write bumps the version, so workers see it immediately.

## Extension points

| Add | Where | Not needed |
|---|---|---|
| Tool | `core/tools.py`: implementation, `TOOL_META`, registry entry | pipeline |
| OneBot action | `core/actions/registry.py`: `ActionSpec` | permissions, audit, approvals |
| Channel | `gateway/adapters/`: adapter | core (`/v1/ingest` stays the same) |
| Persona preset | `core/personas.py` | frontend |
| Search backend | `core/websearch.py` | fallback chain |
| Metric | `core/metrics.py` | `/metrics` |
| Offline check | `scripts/harness_all.py` | CI |

## Regression layers

`pytest` covers functions and APIs. The harness covers invariants that are not unit tests: persona consistency, version strings in three places, and sticker tags matching disk. Run it after changing personas, prompts or versions.

```bash
python scripts/harness_all.py
python scripts/harness_all.py --list
python scripts/harness_all.py --live   # adds checks that need a model or a running service
```

## Invariants

1. Destructive actions always require approval. No tier or subject bypasses it.
2. Agent permission = min(deployment tier, requester tier).
3. Without `ADMIN_TOKEN`, admin APIs return 503. There is no "open dev mode".
4. The knowledge-base JSON is the source of truth; SQLite is a derived index.
5. The prompt tool list and the API tool list must not diverge.
6. Deleted messages never enter model context.
7. Tool results, web pages and search results are data, not instructions.
