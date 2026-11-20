# Roadmap

English · [中文](ROADMAP.zh.md)

BigRobot is a platform that takes over a chat account. The only rule for this roadmap:

> Does this make adding a capability, a platform or a second account cheaper without losing control?

If not, it waits. If it conflicts with the product boundary, it goes under "not doing".

## Shipped

- Account takeover for QQ: protocol start, QR login, watchdog, restart backoff.
- Real visibility: group and direct history, members with roles, files, notices, friends.
- Actions with risk tiers, approvals and a hash-chained audit.
- Agent loop with tool calling, budgets, cancellation and repeat detection.
- Multi-collection knowledge base with persona binding and document ingestion.
- Future tasks that re-run the agent and deliver the result to the original channel.
- Persona capability scopes for tools, skills, MCP and extensions.
- Gateway notice/request events and recall soft-delete.
- Declarative HTTP extension packs and an MCP stdio client.
- Multi-account sessions, memory, actions and delivery isolated per bot account.

## Now

- Close the remaining multi-account edges: account-aware tickets, group-level profile policy, and an explicit decision on per-bot persona inside one group.
- Put extension writes through the same approval path as built-in destructive actions.
- Add an OpenAI-compatible `/v1/chat/completions` surface so other clients can use BigRobot as a model.
- Add streamable HTTP/SSE transport to the MCP client; keep stdio as the default.
- Keep the console at seven top-level areas and make the approval queue reachable from navigation.

## Later

- A second channel adapter that proves capability declarations work without core changes.
- A connection pool for hot MCP tools.
- Optional Postgres storage behind the same store interface.
- Release automation that generates notes from commits, after the commit convention is stable.

## Not doing

- A visual workflow canvas. Configuration is the orchestration surface.
- A plugin marketplace with remote Python installation. It conflicts with the account/permission model.
- Racing on adapter count. QQ is the deep path; breadth comes from declarations, not duplicated products.
- Voice cloning or synthetic persona video. The abuse surface is larger than the value.

## How an item gets here

1. It broke in real use, or it blocks a real deployment.
2. Write one sentence of "why" and one measurable acceptance check.
3. Only then put it in a release.

An item without an acceptance check is a wish, not a roadmap entry.
