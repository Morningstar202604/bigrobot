# 本地模型

[English](../LOCAL-MODELS.md) · 中文

BigRobot 可以直接下载小体积 GGUF 模型，用 `llama.cpp` 在本机跑起来并切换过去，不经过云端 API。提示词和回复都留在自己的机器上。

## 推荐目录

| 模型 | 体积 | 上下文 | 为什么选它 |
|---|---|---|---|
| **MiniCPM5-1B（默认推荐）** | 1.08B / Q4_K_M | 128K | 2026-05 发布的 1B 级开源 SOTA；Agent 工具调用、代码和困难推理领先同尺寸，通用能力比 0.8B 更稳。 |
| BotPsy-0.8B | 0.8B / Q4_K_M | 256K | 工具调用特化，体积最小、响应最快；内存特别紧或只做提醒/天气时选它。 |
| Qwen3.5-0.8B | 0.8B / Q4_K_M | 256K | BotPsy 的基座，原厂通用基线；复杂 Agent 任务不如 MiniCPM5。 |

三个都是 Apache-2.0，参数都严格低于 2B。下载前控制台会给出准确的文件大小和许可。

MiniCPM5-2B 虽然宣传叫“2B-class”，官方总参数 2,516,756,480，已经超过 2B 硬上限，所以没有放进推荐目录。

## 下载与运行

1. 打开 **设置 → 本地模型**。
2. 点 **下载**。文件落在 `data/models/<id>/`，半截文件保留为 `.part`，下次续传。
3. 下载完成后点 **启用**。BigRobot 会在空闲本地端口启动 `llama_cpp.server`，探测 `/v1/models`，然后把 `llm.base_url`、`llm.model` 和真实 `n_ctx` 写入当前配置。

先装一次可选运行时：

```bash
pip install -r requirements-local.txt
```

下载源依次尝试 `BIGROBOT_HF_ENDPOINT`、`hf-mirror.com`、`huggingface.co`。用 `BIGROBOT_MODELS_DIR` 可以把权重放到别的盘。

## 小模型模式

0.5B—1B 装不下两千字人设和三十个工具 schema。当前端点在本机时，BigRobot 会自动：

- 只保留人设第一句身份，丢掉成长故事；
- 只暴露八个核心工具（`now`、`remind`、`reminders`、`weather`、`remember`、`recall_memory`、`calc`、`web_search`）；
- 历史压到四轮，提示词预算约 1300 字。

这是配置项而不是暗改：`llm.local_compact` 可以关掉，`ctx_used` 里能看到实际生效的精简工具清单。

## 本地模型能用到哪些工具

八个核心工具是实测通路：时间、提醒、天气、记忆、算术、联网搜索。BigRobot 对这些请求做确定性路由，0.8B 不需要自己猜参数名。

完整工具表有 27 个。关掉 `local_compact` 后模型能看到全部，但 2B 以下选工具会明显变差；除非在调试，否则建议保持精简模式。

颜色转换、单位换算、Base64/JSON、随机抽取、汇率、翻译、二维码这些常用工具有确定性意图路由，精简模式也能用，不必把 27 个 schema 全塞给模型。翻译在 MyMemory 免费额度耗尽时会用当前模型兜底；二维码在本地生成并在控制台直接显示。

下面这些工具需要额外设施，没配就明确说“未接入”，不会假装成功：

- `ocr`：本机装 `tesseract` 就能用，支持中英文；控制台上传图片后直接说“识别这张图的文字”即可，不需要额外 Python 包。
- `describe_image`：要配 `multimodal.vision_model`；本地文字模型看不了图。
- `generate_image`：要配 `IMAGE_API_BASE_URL` 和 `IMAGE_API_KEY`；llama.cpp 没有生图端点。
- `fs` / `write_file`：要启动执行器并配 `EXECUTOR_URL`。
- QQ 类工具：要接 QQ/OneBot 网关和账号。
- `translate`：先走 MyMemory，免费额度用完会用当前模型兜底；只要模型可用就能翻译。

## 限制

- 2 核 / 4GB 纯 CPU：一轮短对话大约 8—20 秒。不是必须 GPU，但有无 GPU 体验差别很大。
- 模型本身支持 256K，但 BigRobot 默认只开 8K，因为 KV cache 要占内存。机器扛得住时可在 `POST /api/local-models/activate` 里调大 `n_ctx`。
- `llama_cpp.server` 会读环境变量 `PORT`、`HOST`。BigRobot 给子进程剥掉这两个变量，避免本地模型抢占控制台端口。
- `logits_all` 强制关闭。开着会按 `n_ctx × 词表` 分配浮点数组（8K 上下文约 7.6GB），4GB 机器会直接 OOM。

## API

所有路由都需要 `X-Admin-Token`。启动前先设置，未设置时管理接口按安全默认返回 503：

```bash
export ADMIN_TOKEN="$(openssl rand -hex 32)"
```


| 路由 | 用途 |
|---|---|
| `GET /api/local-models` | 目录、已装文件、运行状态、剩余磁盘 |
| `POST /api/local-models/download` | 开始或续传下载 |
| `GET /api/local-models/jobs/{id}` | 进度、速度、剩余时间、错误 |
| `POST /api/local-models/jobs/{id}/cancel` | 取消下载，保留 `.part` |
| `POST /api/local-models/activate` | 启动并切换为当前模型 |
| `POST /api/local-models/stop` | 停止本地服务 |
| `DELETE /api/local-models/{id}` | 删除模型文件 |
