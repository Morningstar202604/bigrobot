# Local models

English · [中文](zh/LOCAL-MODELS.md)

BigRobot can download a small GGUF model, run it with `llama.cpp`, and switch to it without touching a cloud API. The model runs on your machine; prompts and replies never leave it.

## What is in the catalog

The catalog separates user-selectable models from test fixtures. The console does not choose for the user; it only checks what fits this machine:

| Model | Size | Context | Role |
|---|---|---|---|
| Qwen3.5-9B | 9B / Q4_K_M | 256K | 16GB RAM tier; daily driver, code, long documents and complex tools. |
| Qwen3.5-4B | 4B / Q4_K_M | 256K | 8GB RAM tier; general-purpose pick. |
| MiniCPM5-2B | 2B-class / Q4_K_M (2.52B total) | 128K | 2B-class option for 4GB RAM; Q4 about 1.56GB, meant for full-feature validation. |
| MiniCPM5-1B | 1.08B / Q4_K_M | 128K | Capability testing and low-spec validation only; not a built-in recommendation. |
| BotPsy-0.8B | 0.8B / Q4_K_M | 256K | Tool-call regression fixture. |
| Qwen3.5-0.8B | 0.8B / Q4_K_M | 256K | Original baseline fixture. |

Each card only says "runnable / not enough memory"; the user chooses what to download and enable. 4GB can pick 2B, 8GB can pick 4B, 16GB can pick 9B. Exact file size and license are shown before download.

## Download and run

1. Open **Settings → Local models**.
2. Press **Download**. Bytes go to `data/models/<id>/`, with a `.part` file kept for resume.
3. When the file is complete, press **Enable**. BigRobot starts `llama_cpp.server` on a free local port, checks `/v1/models`, then writes `llm.base_url`, `llm.model` and the real `n_ctx` into the active config.

Install the optional runtime once:

```bash
pip install -r requirements-local.txt
```

The downloader tries `BIGROBOT_HF_ENDPOINT`, then `hf-mirror.com`, then `huggingface.co`. Set `BIGROBOT_MODELS_DIR` to move weights to another disk.

## Small-model mode

4B/9B models use the full persona and all tools. Only sub-2B models enter compact mode. A 0.5B–1B model does not have room for a 2,000-character persona and thirty tool schemas, so BigRobot automatically:

- keeps the first identity sentence of the persona and drops the life story;
- exposes eight core tools (`now`, `remind`, `reminders`, `weather`, `remember`, `recall_memory`, `calc`, `web_search`);
- limits history to four turns and the prompt budget to roughly 1,300 characters.

This is a real setting, not a hidden prompt trick: `llm.local_compact` can be turned off in the config, and the console shows the compact tool list in `ctx_used`.

## What works with a local model

The eight compact tools are the tested path: time, reminders, weather, memory, arithmetic and web search. BigRobot routes them deterministically so a 0.8B model does not have to guess argument names.

The full tool registry has 27 tools. With `local_compact=false` the model sees all of them, but sub-2B tool selection becomes less reliable; keep compact mode on unless you are debugging.

Common utilities have deterministic intent routing, so they work in compact mode without exposing 27 schemas: color conversion, unit conversion, Base64/JSON, random pick, exchange rates, translation and QR codes. Translation falls back to the current model when the free MyMemory quota is exhausted. QR codes are generated locally and shown as an image in the console.

These tools need extra infrastructure and stay explicitly "not configured" rather than pretending success:

- `ocr`: works with a local `tesseract` install (Chinese + English). Upload an image in the console and ask "read the text in this image"; no extra Python package is needed.
- `describe_image`: set `multimodal.vision_model` (the local text model cannot read images).
- `generate_image`: set `IMAGE_API_BASE_URL` and `IMAGE_API_KEY`; llama.cpp has no image endpoint.
- `fs` / `write_file`: start the executor and set `EXECUTOR_URL`.
- QQ tools: connect a QQ/OneBot gateway and account.
- `translate`: uses MyMemory first; if the free quota is exhausted it falls back to the current model, so a configured model is enough.

## Limits

- CPU only on a 2-core / 4GB box: 8–20 seconds per short turn. GPU is not required, but it changes the experience.
- 4B/9B support 256K context; BigRobot starts at 8K because KV cache has to fit in RAM. Raise `n_ctx` in `POST /api/local-models/activate` if the machine can take it.
- Q4 files are about 2.7GB for 4B and 5.7GB for 9B; check free disk before downloading.
- `llama_cpp.server` reads `PORT` and `HOST` from the environment. BigRobot strips both for the child process so the model never takes the console's port.
- `logits_all` is forced off. Leaving it on allocates `n_ctx × vocab` floats (7.6GB at 8K for this vocabulary) and kills 4GB machines.

## API

All routes require `X-Admin-Token`. Set the token before starting the server, otherwise the admin API returns 503 by design:

```bash
export ADMIN_TOKEN="$(openssl rand -hex 32)"
```


| Route | Purpose |
|---|---|
| `GET /api/local-models` | Catalog, detected CPU/RAM/GPU, per-machine recommendation, installed files, running server, free disk |
| `POST /api/local-models/download` | Start or resume a download |
| `GET /api/local-models/jobs/{id}` | Progress, speed, ETA, error |
| `POST /api/local-models/jobs/{id}/cancel` | Stop a download, keep the `.part` file |
| `POST /api/local-models/activate` | Start the server and make it the active model |
| `POST /api/local-models/stop` | Stop the server |
| `DELETE /api/local-models/{id}` | Delete the model files |
