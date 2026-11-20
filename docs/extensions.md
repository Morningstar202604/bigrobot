# Extensions and MCP

English · [中文](zh/extensions.md)

BigRobot has two ways to add external capability:

| Path | Best for | Runs in | Boundary |
|---|---|---|---|
| Declarative HTTP pack | REST APIs, health endpoints, internal services | Core process makes HTTP calls | Private addresses blocked by default; writes need a trusted subject |
| MCP client (stdio) | Existing MCP servers: files, databases, search, browsers | Separate child process | Process per call; read by default, writes declared explicitly |

Tools from both paths enter the same agent tool registry as built-in tools.

## Install a pack

Console: **Capabilities → Extensions → Packs**.

- **Upload a zip**: the zip root, or its only subdirectory, must contain `manifest.json`.
- **Install from a link**: a publicly reachable zip URL. Every redirect target is checked; private and cloud-metadata addresses are rejected.

Installed packs live in `data/extensions/<id>/`. Disable and delete take effect immediately. Overwriting keeps the last three versions and supports rollback.

## `manifest.json`

```json
{
  "id": "weather-http",
  "name": "Weather",
  "version": "0.0.1",
  "description": "Current weather",
  "author": "you",
  "kind": "http",
  "base_url": "https://api.example.com",
  "allow_private": false,
  "allow_untrusted": false,
  "tools": [
    {
      "name": "weather_now",
      "description": "Current weather for a city",
      "method": "GET",
      "path": "/weather",
      "risk": "read",
      "params": {
        "city": {
          "type": "string",
          "required": true,
          "in": "query",
          "description": "City name"
        }
      },
      "headers": {
        "Authorization": "Bearer ${ENV:WEATHER_KEY}"
      }
    }
  ],
  "skills": [
    {
      "name": "Weather lookup",
      "description": "Look it up; do not answer from memory",
      "file": "skills/weather.md"
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `id` | Lowercase letters, digits, underscores and hyphens; 2–41 characters; directory name must match |
| `kind` | `http` only in v1. Python entry points are not accepted |
| `base_url` | `http` or `https`; must be public by default |
| `allow_private` | Admin opt-in for private or loopback addresses; cloud metadata is always rejected |
| `allow_untrusted` | Lets non-admin subjects call **read-only** tools; write tools always need a trusted subject |
| `tools[].method` | `GET` or `POST` |
| `tools[].risk` | `read` or `write`; writes pass through the permission gate |
| `tools[].params[].in` | `query`, `path` or `body`; path parameters use `{name}` |
| `tools[].headers` | Values support `${ENV:NAME}`; a missing variable fails the call instead of sending an empty value |
| `skills[].file` | Markdown relative to the pack directory; read on install and rendered into the prompt |

Tool names must be globally unique: not the same as a built-in tool or another installed pack.

## MCP servers

Console: **Capabilities → Extensions → MCP**.

Fill in:

- Name: display label.
- Command: `npx`, `uvx`, `python3` or an absolute path.
- Arguments: one per line.
- Environment: `KEY=value` per line. For secrets use `env:NAME`; the value is read from the process environment and is not stored.
- Permission: `read` or `write`.
- Allow ordinary members: read-only servers only.

After saving, press refresh. BigRobot starts the child process, calls `initialize`, lists tools and caches them. Later turns do not start the process until a tool is actually called.

Transport is stdio. Streamable HTTP and SSE MCP are not wired yet.

## Current limits

- No Python plugins inside the core process. Declarative HTTP is deliberate; a Python host, if added, must run in a separate process with a permission manifest.
- A new MCP child process per call gives good isolation but slow cold starts. A connection pool can come later for hot tools.
- Packs can declare HTTP tools only; they cannot register commands or ship frontend pages. Use MCP or wait for extension slots.
- Write tools currently require a trusted subject but do not enter the full approval chain. Put approval-sensitive operations in `policy/approvals` until the extension permission model grows.
