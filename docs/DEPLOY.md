# BigRobot 部署与接入

一份文档覆盖：装、起、接协议端、验、运维、排障。深度历史记录见 `docs/archive/`。

## 0. 选哪条路

| 场景 | 走哪条 | 说明 |
|---|---|---|
| 生产 / 云 VPS / 想长期稳定 | **Docker**（推荐） | 自带运行环境，QQ 版本与你无关，单端口对外 |
| 开发 / 想改代码 / 无 Docker | 源码（Python 3.12+） | `pip install -e .` 后直接跑 |
| 个人 Windows 桌面、不想装任何东西 | exe（非推荐） | 打包是为了"一个文件能跑"，不是部署标准；数据在 `bigrobot-data/` |

```bash
# 源码三条命令
pip install -e . && bigrobot init && bigrobot run
# -> 打开 http://127.0.0.1:8010，用 init 打印的管理员令牌登录
```

`bigrobot init` 生成 `.env` 与两把随机令牌；`bigrobot run --gateway` 同时拉起协议端网关。
出问题先 `bigrobot doctor`，它报的是实际状态（端口被谁占、Key 到底配没配）。

## 1. 准备清单

| 项 | 必要性 | 说明 |
|---|---|---|
| 部署机 | ✅ | 1 核 1G 起步；装 Docker |
| 协议端账号（QQ 小号） | ✅ 仅 QQ 渠道 | **首次登录必须扫码**，只能在部署机完成（腾讯风控） |
| 模型 API Key | ⭕ 推荐 | 任意 OpenAI 兼容端点；不填 = 规则 + 检索模式，照样能跑 |
| 域名 | ⭕ | 只在需要 HTTPS / 好记地址时 |

## 2. Docker 五步上线

```bash
# ① 一键脚本（首次生成 .env 并随机化两把令牌）
git clone --depth 1 https://gitcode.com/badhope/bigrobot.git /opt/bigrobot
bash /opt/bigrobot/scripts/deploy.sh

# ② 编辑 /opt/bigrobot/.env：NAPCAT_QQ、USER_LLM_API_KEY
vim /opt/bigrobot/.env

# ③ 重跑脚本 → 构建镜像并启动（core 自带控制台，单端口 8010）
bash /opt/bigrobot/scripts/deploy.sh

# ④ 扫码登录协议端（三选一见第 4 节）

# ⑤ 验收（见第 5 节）
curl http://127.0.0.1:8010/healthz          # {"ok":true}
```

端口分配：`core 8010`（控制台 + API）、`gateway 8011`、`executor 8020`（仅内网）、
`napcat WebUI 6099`（只绑本机）、`NapCat WS 3001`（compose 内网）。

**家宅 + 隧道变体**：`.env` 写 `BIGROBOT_BIND=127.0.0.1`，用 `cloudflared` / frp 指向
`http://127.0.0.1:8010`，机器不直接暴露公网。

## 3. 配置

三层解析：**代码默认值 → 环境变量 → 数据库**。控制台写数据库层，改完即生效。
全部键见 [`.env.example`](../.env.example)；2.0 起统一 `BIGROBOT_*` 前缀，
旧的 `CS_AGENT_*` / `ZHIKE_*` 自动映射，老 `.env` 不用改。

## 4. 接协议端（QQ）

三条路，按场景选：

| 情况 | 走哪条 | 代价 |
|---|---|---|
| 机器没装桌面 QQ，或愿意跑容器 | **compose 容器**（推荐） | 自带一份 QQ，宿主机版本无关 |
| 已经跑着容器，只想最快登录 | **控制台扫码** | 不用开 NapCat WebUI，令牌不进浏览器 |
| 已登录桌面 QQ，想复用凭据免扫码 | **本机注入** | 对 QQ 版本敏感，**升级即静默失效** |

### 4.1 容器（推荐）

```bash
docker compose -f docs/napcat-compose.yaml up -d
docker compose -f docs/napcat-compose.yaml logs -f napcat
# 打开 http://127.0.0.1:6099/webui 扫码（默认令牌 bigrobot-local，可用 NAPCAT_WEBUI_TOKEN 覆盖）
```

数据落在 `docs/data/`（QQ 凭据 / 配置 / 插件）：备份它就能迁移，删掉 `data/qq` 就要重扫。
Windows 上 `docker info` 报 `cannot find the file specified`，多半是 Docker Desktop 没起，
或 WSL/`VirtualMachinePlatform` 没启用——`python scripts/qq_doctor.py` 会把两者分开报。

### 4.2 控制台扫码

`.env` 配好 WebUI 地址与令牌，控制台「运行总览 → 渠道连接 → QQ → 扫码登录」：

```env
NAPCAT_WEBUI_URL=http://127.0.0.1:6099
NAPCAT_WEBUI_TOKEN=<启动日志里的 token，compose 里自设的值>
```

令牌只存在核心进程内，浏览器拿不到；二维码约 2 分钟换新；扫码成功网关自动连，无需重启。
NapCat 大版本升级后该内部接口可能失效，控制台会明说拿不到二维码，退回 WebUI 路径。

### 4.3 本机注入（免扫码，慎用）

```bash
python scripts/napcat_local.py start --qq <机器人QQ号>   # 桌面 QQ 会被顶掉
python scripts/qq_doctor.py                             # 判断这台机器该走哪条路
```

**它为什么会"静默失效"**：注入包 `qqnt.json` 写死了适配的 QQ 版本。QQ 自动升级后
`QQ.exe` 能起来但内存只有约 20MB，6099 / 3001 都不监听，`logs/` 不产生新文件，
`run.log` 只写 `Process resumed` —— 用户看到的是"群里一直没人回"，日志全"正常"。

> 权威结论：**本机注入对 QQ 版本敏感，容器不受影响**。反复失效就别再修版本号，改容器。

### 4.4 网关排障顺序

1. `3001` 有没有在监听（容器内网 / 防火墙）。
2. NapCat 网络配置里"WebSocket 服务端"是否启用（`messagePostFormat: array`）。
3. 控制台渠道页 `onebot_v11` 是否 `online`；`GET /api/channels/status` 看 `bots`、`self_id`。
4. 群里 @ 不回：先看群节流与互刷护栏是否命中（`gateway/loop_guard.py`，默认开）。

## 5. 验收

### 5.1 机器可自动验收（无需真机扫码）

```bash
.venv/bin/python scripts/qq_e2e.py    # 模拟 NapCat 走通 OneBot→网关→核心→回复
python scripts/e2e_check.py --base-url http://127.0.0.1:8010   # 18 项端到端
```

> `e2e_check.py` 会写会话/消息/工单并清理，**只能对隔离实例跑**。

### 5.2 真机验收（唯一人工环节）

- [ ] 小号扫码，NapCat 显示在线
- [ ] 私聊问知识库问题 → 秒回带引用
- [ ] 私聊发图 → 无视觉模型时明确说"看不了图，请用文字描述"
- [ ] 拉群 @机器人 → 正常回复；不 @ 不理人
- [ ] 说"转人工" → 明确告知只有机器人，不进入待接管
- [ ] 未带令牌 `POST /v1/ingest` → **401**

## 6. 运维

```bash
bash /opt/bigrobot/scripts/deploy.sh                       # 升级（拉代码重建）
docker logs -f bigrobot-core                               # 日志
docker logs -f bigrobot-gateway
```

**备份必须走 `sqlite3 .backup`**（WAL 模式下直接 `cp` 会拿到"主库已写、WAL 未合并"的快照）：

```bash
docker run --rm -v bigrobot_core_data:/data -v "$PWD":/b alpine \
  sh -c 'apk add --no-cache sqlite >/dev/null && sqlite3 /data/cs_agent.db ".backup /b/backup.db"'
```

**回滚**：`git -C /opt/bigrobot checkout <旧 tag 或 sha> && bash scripts/deploy.sh`

**恢复演练（每季度，脚本化）**：停 core → 用备份 `.backup` 回写 → 起 core →
`/healthz` → `/api/admin/audit/verify` 应 `ok=true`（哈希链完整）→ 抽样对比
`/api/admin/overview` 的 sessions/messages 计数。

## 7. 可观测性

| 端点 | 用途 |
|---|---|
| `GET /healthz` | 存活探针（容器 healthcheck） |
| `GET /readyz` | 就绪：schema 版本、KB 条数、LLM 是否已配 |
| `GET /metrics` | Prometheus：`bigrobot_http_requests_total`、`..._duration_seconds`、`bigrobot_llm_calls_total{result}`、`bigrobot_uptime_seconds` |
| `GET /api/admin/logs` | 最近事件（控制台日志中心） |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | 可选 trace 导出（装 `requirements-tracing.txt`） |

建议的三条告警：5xx 比例 > 2%、LLM 失败率 > 20%、单接口 P95 > 2s。

## 8. 安全基线（生产必做）

- 两把令牌均由脚本随机化，不要改回占位符。
- 公网部署 `BIGROBOT_LOCAL_TOKEN_BOOTSTRAP=0`，关掉"本机自动下发令牌"（默认只放行回环）。
- 不确定就收紧：`BIGROBOT_BIND=127.0.0.1` + 反代/隧道对外。
- NapCat WebUI（6099）只绑本机，SSH 隧道访问。
- 公网直连时 `BIGROBOT_CORS_ORIGINS` 填控制台实际域名。
- `executor` 默认拒绝 `../` 穿越、`.env`、符号链接逃逸、`; rm -rf /`、`python -c` 等；
  `shell.exec` / `fs.delete` / `proc.kill` 属于 L2，必须人工审批。

## 9. 常见问题

| 症状 | 处理 |
|---|---|
| gateway 连不上协议端 | WS 3001 没开 / 不在同一网络 / `messagePostFormat` 不是 array |
| 登录频繁掉线 | 换固定设备登录，别频繁重启容器；登录态在 `napcat_data` volume |
| 控制台 401 | 本机应自动登录；远程用「管理中心 → 访问令牌」；仍是旧令牌就清 `localStorage` |
| 模型不生效 | 管理中心 LLM 配置做连通测试；`USER_LLM_API_KEY` 为空即规则模式 |
| 群里不回但私聊正常 | 群节流或互刷护栏命中；看 `gateway/loop_guard.py` 与渠道页统计 |
| 升级后数据"消失" | 用了旧的 `zhike-data/` 目录：2.0 会优先复用旧目录，确认 `BIGROBOT_HOME` 指向哪里 |
