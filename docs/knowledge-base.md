# Knowledge base: collections, persona binding and ingestion

English · [中文](zh/knowledge-base.md)

A knowledge base is not one flat FAQ table. Each persona has its own history, setting notes and specialist material; shared business answers still need to reach every persona. One mixed array makes retrieval bleed across topics.

## Data model

The source of truth is a readable, exportable `core/data/kb.json`:

```json
{
  "version": 2,
  "collections": [
    {"id": "default", "name": "Default", "persona_ids": [], "enabled": true}
  ],
  "kb": [
    {"id": "KB101", "collection": "default", "title": "Delivery time", "text": "...", "answer": "..."}
  ]
}
```

- `collections`: `persona_ids` empty means shared by all; a non-empty list limits the collection to those preset personas.
- `kb[].collection`: owning collection; defaults to `default`.
- An old file with only `{"kb": [...]}` is read as the default collection; no manual migration.
- Entries may carry `source` (`manual`, `import` or a file name) and `created_at` / `updated_at` for traceability.

## Retrieval scope

- Custom personas have no preset id and search every collection, preserving the old behaviour.
- Preset personas search shared collections plus collections bound to them.
- The `lookup_policy` tool and chat context use the same scope, so a tool cannot surface another persona's notes.
- A disabled collection is never retrieved by any persona.

## Ingestion

| Path | Entry point | Notes |
|---|---|---|
| Single entry | `POST /api/kb` | Optional `collection`; leave the id empty to auto-number |
| Markdown batch | `POST /api/kb/import` | `replace=true` clears only the target collection |
| Document import | `POST /api/kb/import/document` | PDF, DOCX, XLSX, MD, TXT; chunked by heading and paragraph; source file name kept |
| Historical material | Same | Timelines, interviews and setting drafts imported by Markdown heading into a persona collection |
| Export | `GET /api/kb/export` | Markdown by default; `format=json` keeps collection metadata |

Chunks are capped at 500 characters and documents at 10 MB. A parse failure returns a readable 400 and writes no partial data.

## Management API

| Method | Path | Use |
|---|---|---|
| `GET` | `/api/kb?collection=<id>` | List entries; omit the parameter for all |
| `GET` | `/api/kb/collections` | Collections and entry counts |
| `POST` | `/api/kb/collections` | Create a collection |
| `PUT` | `/api/kb/collections/{id}` | Rename, describe, bind personas, enable or disable |
| `POST` | `/api/kb/collections/{id}/toggle` | Toggle one collection |
| `DELETE` | `/api/kb/collections/{id}?move_to=default` | Delete and move entries to a target collection |
| `POST` | `/api/kb/test` | Test retrieval in a collection |

Every management endpoint requires the admin token.

## Boundaries

- The default collection cannot be deleted, only renamed or disabled. Deleting another collection moves entries to the default unless a target is given; nothing is silently lost.
- Collection ids use lowercase letters, digits, underscores and hyphens, 2–41 characters.
- Persona binding accepts only existing preset ids; an unknown id is a 400.
- Writes use an in-process lock, a file lock and an atomic temporary-file replace. The index is a derived cache and rebuilds when the file mtime changes.
