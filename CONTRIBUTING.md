# Contributing

English · [中文](CONTRIBUTING.zh.md)

Issues, documentation, bug fixes and features are welcome.

## Development setup

```bash
git clone https://github.com/badhope/bigrobot && cd bigrobot
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cd frontend && npm ci && cd ..
```

On Windows use `.venv\Scripts\pip`.

## Before a pull request

```bash
python -m pytest tests -q
python -m ruff check core executor gateway scripts tests
cd frontend && npx tsc --noEmit && npm test && npm run build
```

CI runs the same checks plus a coverage floor, `pip-audit` on production dependencies and `npm audit --omit=dev --audit-level=high`.

## Commits

- Conventional Commits: `feat:`, `fix:`, `docs:`, `test:`, `chore:`, `refactor:`.
- One commit does one thing, so it can be reviewed and reverted.
- Say what changed and why, not "update".
- **Never commit keys, tokens, real QQ or group ids, chat logs or database files.**

## Adding a tool or channel

1. Register the tool in `core/tools.py` with a `TOOL_META` entry and add a real call test.
2. If it needs external configuration, add it to `_REQUIRES_CONFIG`; an unconfigured tool should disappear from the pool rather than fail after the model calls it.
3. Actions that change state go through `core/actions/registry.py` with a risk tier. Destructive actions require approval.
4. Channel adapters live in `gateway/adapters/` and keep the `NormalizedMessage` field semantics.

## Bugs and security

Search existing issues first. Security reports do not belong in a public issue; see [SECURITY.md](SECURITY.md).

By contributing you agree that your work is licensed under the MIT license in [LICENSE](LICENSE).
