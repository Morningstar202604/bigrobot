## What changed

<!-- One sentence; link an issue with #123 -->

## Why

## How it was verified

- [ ] `python -m pytest tests -q`
- [ ] `python -m ruff check core executor gateway scripts tests`
- [ ] `cd frontend && npx tsc --noEmit && npm test && npm run build`

## Checks

- [ ] No keys, tokens, real QQ or group ids, chat logs or database files
- [ ] New or changed behaviour has tests
- [ ] Docs updated (README / DEPLOY / docs)
