# 角色能力边界（Persona Capabilities）

[English](../persona-capabilities.md) · 中文

> 每个预设角色可以有自己的工具、技能、MCP、扩展范围。默认继承全部；只有显式设置白名单才收缩。

## 为什么需要

同一个 Agent 平台里，不同角色不该拥有同样的执行面：

- 「问」是教学角色，不需要读本机文件、也不需要以机器人身份发消息；
- 「砚」做资料核查，应该只拿检索与文档工具；
- 「零」在群里接梗，可以拿 QQ 发送、表情包，但不该碰运维脚本。

能力边界解决的是「角色人设」之外的**权限可见性**：模型看不到未授权工具，
即使通过提示注入直接点名，执行层也会拒绝。

## 默认与边界

- 没有配置的角色 → 继承全局能力，行为与升级前完全一致。
- 白名单只能选择**全局已启用**的子集，不能绕过：
  - 工具注册表里的开关；
  - 扩展/MCP 服务器自身的启停；
  - `PRIVILEGED_TOOLS` 与主体权限闸门；
  - 执行器的文件根目录策略。
- `mode=allow` 且 `ids=[]` 表示**这个角色什么都不允许**（显式收缩，不是继承）。
- 知识库集合绑定是独立的一套（`kb.json` 的 `collections[].persona_ids`），
  与这里的能力边界互不替代。

## 配置结构

`config.persona_caps.items`：

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

四类：

| 字段 | 控制什么 | 不控制什么 |
|---|---|---|
| `tools` | 模型可调用的工具清单 | 工具本身的全局开关、执行器权限 |
| `skills` | 注入提示词的技能说明书 | 工具实现是否存在 |
| `mcp` | 角色可见的 MCP 服务器 | 服务器进程是否启用 |
| `extensions` | 角色可见的声明式扩展 | 扩展包是否安装/启用 |

旧写法兼容：某类直接写成数组时，按 `allow` 处理。

## API

需要 `X-Admin-Token`。

```http
GET    /api/persona-caps
PUT    /api/persona-caps
DELETE /api/persona-caps/{persona_id}
```

`PUT` 提交整张能力表：

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

服务端会校验角色 id 与白名单项是否存在；未知项直接 400，避免保存一张永远不生效的配置。

## 在管线里怎么生效

1. `build_context` 先反查当前预设角色 `persona_id`。
2. `tools.active_tools(cfg, persona_id)` 与 `tool_schema_block(cfg, persona_id)`
   同时过滤内置工具和动态工具（扩展按 `extension`，MCP 按 `server`）。
3. `skills.render(cfg, allowed_ids)` 过滤内置/自定义技能；
   `extensions.render_skills(...)` 过滤扩展技能。
4. 模型真正调用时，`invoke` / `invoke_with` 先过 `_persona_denied`，
   再走原有的主体权限闸门——两层都过才执行。
5. `future_task` 执行时会恢复任务创建时的 `persona_id`，因此同一任务隔天执行
   不会突然换成另一个角色的能力范围。

## 控制台

「能力 → 角色能力」页：

- 选择角色；
- 四组能力分别选「继承全部」或「只允许选中」；
- 保存后即时生效；
- 「恢复继承全部」删除该角色的单独配置。

## 已知限制

- 只支持有稳定 `persona_id` 的预设角色；自定义角色卡没有预设 id 时仍走全局能力。
- 白名单是静态配置，不做按群/按时间的动态授权；那属于策略与审批层。
- 角色能力不替代审批：写操作仍受 `PRIVILEGED_TOOLS`、L2 审批与审计约束。
