# Persona capabilities

English · [中文](zh/persona-capabilities.md)

A preset persona can have its own tools, skills, MCP servers and extensions. The default is full inheritance; only an explicit allowlist narrows access.

## Why

Different personas should not share the same execution surface:

- A teaching persona does not need local file access or the ability to send messages as the bot.
- A research persona should get retrieval and document tools, not shell access.
- A chat persona can send QQ messages and stickers, but should not touch operations scripts.

Capabilities control **visibility** on top of the persona prompt. The model does not see an unauthorised tool; if a prompt injection names it directly, the execution layer still refuses.

## Defaults and boundaries

- No configuration → inherit global capabilities, exactly as before.
- An allowlist can only select a subset of what is already enabled globally. It cannot bypass:
  - tool registry switches;
  - extension or MCP server enablement;
  - `PRIVILEGED_TOOLS` and subject permission gates;
  - the executor's filesystem root policy.
- `mode=allow` with `ids=[]` means **nothing is allowed** for that persona; it is an explicit empty set, not inheritance.
- Knowledge-base collection binding is separate (`collections[].persona_ids` in `kb.json`) and does not replace capabilities.

## Shape

`config.persona_caps.items`:

```json
{
  "zero": {
    "tools":      {"mode": "allow", "ids": ["reminders", "web_search"]},
    "skills":     {"mode": "allow", "ids": ["builtin-web-research"]},
    "mcp":        {"mode": "allow", "ids": ["echo"]},
    "extensions": {"mode": "all",   "ids": []}
  }
}
```

| Field | Controls | Does not control |
|---|---|---|
| `tools` | Tools the model can call | Global tool switches, executor permissions |
| `skills` | Skill instructions injected into the prompt | Whether the implementation exists |
| `mcp` | MCP servers visible to the persona | Whether the server is enabled |
| `extensions` | Declarative extensions visible to the persona | Whether the pack is installed or enabled |

A legacy array form is accepted and treated as `mode=allow`.

## API

Requires `X-Admin-Token`.

```http
GET    /api/persona-caps
PUT    /api/persona-caps
DELETE /api/persona-caps/{persona_id}
```

`PUT` replaces the whole table:

```json
{
  "items": {
    "zero": {
      "tools": {"mode": "allow", "ids": ["reminders"]},
      "skills": {"mode": "all", "ids": []},
      "mcp": {"mode": "all", "ids": []},
      "extensions": {"mode": "all", "ids": []}
    }
  }
}
```

The server validates persona ids and allowlist entries; an unknown id is a 400, so an ineffective configuration is not saved.

## Pipeline behaviour

1. `build_context` resolves the current preset `persona_id`.
2. `tools.active_tools(cfg, persona_id)` and `tool_schema_block(cfg, persona_id)` filter built-in and dynamic tools; extensions filter by `extension`, MCP by `server`.
3. `skills.render(cfg, allowed_ids)` filters built-in and custom skills; `extensions.render_skills(...)` filters extension skills.
4. At call time, `invoke` / `invoke_with` check `_persona_denied` first, then the existing subject gate. Both must pass.
5. A future task restores the `persona_id` captured when it was created, so a task run tomorrow does not silently switch capability scope.

## Console

**Capabilities → Persona capabilities**:

- pick a persona;
- set each of the four groups to inherit all or allow selected items;
- save applies immediately;
- "restore inheritance" removes the persona's override.

## Limits

- Only presets with a stable `persona_id` are covered. Custom cards without a preset id still use global capabilities.
- The allowlist is static configuration, not per-group or time-based authorisation. That belongs in policy and approvals.
- Capabilities do not replace approvals: write actions still pass `PRIVILEGED_TOOLS`, destructive-action approval and audit.
