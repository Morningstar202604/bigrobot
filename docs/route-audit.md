# Route consumer audit

English · [中文](zh/route-audit.md)

The audit counts routes from `app.openapi()["paths"]`, then searches for each path in `frontend/src`, `scripts`, `tests` and `gateway`. Placeholders `{x}` match a path segment (`[^/'"]+`), including template literals such as `${...}`.

Two mistakes seen before:

1. Searching the escaped literal `{group_id}` marks every parameterised route as unused. The audit once reported 31 dead routes; the real number was 3.
2. Scanning only `.ts` and `.tsx` misses `.jsx`. `OperatorDesk.jsx` calls `/api/operator/notes/{sid}`; a partial scan would have deleted a live route.

The only route with no consumer today is `/api/debug/conn`. It returns 404 unless `BIGROBOT_DEV=1` is set.

Maintenance rule: a new route needs a caller or a test, otherwise it is not merged. Run this audit before deleting anything.
