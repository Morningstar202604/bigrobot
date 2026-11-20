# 扩展包与 MCP

[English](../extensions.md) · 中文

BigRobot 的外部能力接入分两条路：

| 方式 | 适合什么 | 运行在哪 | 安全边界 |
|---|---|---|---|
| 声明式 HTTP 扩展 | 调 REST API、读健康接口、接内部服务 | 核心进程只发 HTTP 请求 | 默认拒绝内网、写操作需管理员 |
| MCP 客户端（stdio） | 现成的 MCP 服务器：文件系统、数据库、搜索、浏览器 | 独立子进程 | 每次调用起进程；工具默认只读，写权限显式声明 |

两条路的工具都会进入 Agent 的工具清单，和内置工具一样被模型调用。

## 一、安装扩展

控制台：`能力 → 扩展 → 扩展包`。

- **上传 zip**：zip 根目录（或唯一子目录）必须有 `manifest.json`；
- **从链接安装**：支持公开可访问的 zip 直链；安装时会校验每个重定向目标，拒绝内网和云元数据地址。

安装后写入 `data/extensions/<id>/`；停用/删除立刻生效。覆盖安装会保留最近 3 个版本，可点“回滚”。

## 二、manifest.json

```json
{
  "id": "weather-http",
  "name": "Weather",
  "version": "0.0.1",
  "description": "查天气",
  "author": "you",
  "kind": "http",
  "base_url": "https://api.example.com",
  "allow_private": false,
  "allow_untrusted": false,
  "tools": [
    {
      "name": "weather_now",
      "description": "查某城市当前天气",
      "method": "GET",
      "path": "/weather",
      "risk": "read",
      "params": {
        "city": {
          "type": "string",
          "required": true,
          "in": "query",
          "description": "城市名"
        }
      },
      "headers": {
        "Authorization": "Bearer ${ENV:WEATHER_KEY}"
      }
    }
  ],
  "skills": [
    {
      "name": "天气查询",
      "description": "先查再答，不要凭记忆报天气",
      "file": "skills/weather.md"
    }
  ]
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| `id` | 小写字母/数字/下划线/短横线，2–41 字符；目录名与 id 一致 |
| `kind` | v1 只允许 `http`；Python 插件入口不开放 |
| `base_url` | 只允许 `http/https`；默认必须是公网地址 |
| `allow_private` | 管理员显式允许内网/回环地址（本地开发 API 用）；云元数据地址永远拒绝 |
| `allow_untrusted` | 允许非管理员调用**只读**工具；写工具永远要求可信主体 |
| `tools[].method` | `GET` / `POST` |
| `tools[].risk` | `read` / `write`；`write` 会走权限闸门 |
| `tools[].params[].in` | `query` / `path` / `body`；路径参数用 `{name}` 占位 |
| `tools[].headers` | 值支持 `${ENV:NAME}`，缺变量时调用会失败而不是静默发空值 |
| `skills[].file` | 相对扩展目录的 Markdown；安装时读入，渲染到提示词 |

工具名必须全局唯一：不能和内置工具重名，也不能和已安装扩展重名。

## 三、MCP 服务器

控制台：`能力 → 扩展 → MCP`。

填写：

- 名称：显示用；
- 命令：`npx` / `uvx` / `python3` / 绝对路径；
- 参数：每行一个；
- 环境变量：每行 `KEY=value`；敏感值建议写 `env:NAME`，运行时从进程环境读取，不落库；
- 权限：`read` / `write`；
- 允许普通成员：只对只读服务器生效。

添加后点刷新按钮，BigRobot 会拉起子进程、`initialize`、`list_tools`，把工具缓存到配置里。之后每轮对话构建不再启动子进程，只有真正调用工具时才启动。

当前 transport：stdio。SSE/HTTP 流式 MCP 还没接；需要时再加。

## 四、当前限制

- 不支持 Python 插件直接跑在核心进程。第三方 Python 插件若跑在宿主环境里，供应链与权限边界都不可控；BigRobot 先做声明式 HTTP，后续如果要做 Python 宿主，必须走独立进程 + 权限清单。
- MCP 每次调用起一个子进程：隔离好，但冷启动慢；高频工具后续可以加长连接池。
- 扩展只能声明 HTTP 工具，不能注册命令、不能自带前端页面。需要更复杂的交互时，先走 MCP 或等扩展页槽位。
- 写工具目前只做“可信主体”判定，没接完整的审批流；需要审批的写操作应放进 `policy/approvals` 或后续扩展权限模型。
