# 知识库：多集合、角色绑定与资料摄入

[English](../knowledge-base.md) · 中文

知识库不是一张平铺的 FAQ 表。每个角色有自己的历史、设定和专业底稿；
业务 FAQ 又要对所有角色共用。混在一个数组里，检索时必然互相串味。

## 数据模型

真相源仍是可读、可导出的 `core/data/kb.json`：

```json
{
  "version": 2,
  "collections": [
    {"id": "default", "name": "默认知识库", "persona_ids": [], "enabled": true}
  ],
  "kb": [
    {"id": "KB101", "collection": "default", "title": "发货时效", "text": "...", "answer": "..."}
  ]
}
```

- `collections`：知识库集合。`persona_ids` 为空表示全角色共用；非空时只对列出的预设角色生效。
- `kb[].collection`：条目所属集合，缺省为 `default`。
- 旧版只有 `{"kb": [...]}` 的文件会自动按默认库读取，不需要手工迁移。
- 条目可带 `source`（来源文件名/`manual`/`import`）和 `created_at`/`updated_at`，便于回溯。

## 检索范围

- 自定义角色没有预设 id：检索全部集合，保持旧行为。
- 预设角色：只检索公共集合 + 绑定到自己的集合。
- `lookup_policy` 工具与对话上下文使用同一套范围，避免工具把别的角色设定翻出来。
- 集合停用后，任何角色都不会召回它。

## 摄入方式

| 方式 | 入口 | 说明 |
| --- | --- | --- |
| 单条新增 | `POST /api/kb` | 可指定 `collection`；ID 留空自动编号 |
| Markdown 批量 | `POST /api/kb/import` | `replace=true` 只清空目标集合 |
| 文档导入 | `POST /api/kb/import/document` | PDF / DOCX / XLSX / MD / TXT，按标题与段落分块，保留来源文件名 |
| 历史资料 | 同上 | 角色年表、访谈、设定稿按 Markdown 标题分节导入对应角色库 |
| 导出 | `GET /api/kb/export` | 默认 Markdown；`format=json` 保留多库元数据 |

分块上限 500 字，单文档 10 MB。解析失败会返回可读的 400，不会写半截数据。

## 管理 API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/api/kb?collection=<id>` | 列出条目；不带参数返回全部 |
| `GET` | `/api/kb/collections` | 集合列表与条目数 |
| `POST` | `/api/kb/collections` | 新建集合 |
| `PUT` | `/api/kb/collections/{id}` | 改名、改说明、改角色绑定、启停 |
| `POST` | `/api/kb/collections/{id}/toggle` | 单独启停 |
| `DELETE` | `/api/kb/collections/{id}?move_to=default` | 删除集合，条目迁移到目标库 |
| `POST` | `/api/kb/test` | 指定集合试召回 |

所有管理接口都要求管理员令牌。

## 边界

- 默认库不能删除，只能改名/停用；删除其它库时条目默认迁到默认库，不会静默丢失。
- 集合 ID 只能用小写字母、数字、下划线、短横线，2–41 字符。
- 角色绑定只接受当前存在的预设角色 ID；未知 ID 直接 400。
- 知识库文件写入仍走进程内锁 + 文件锁 + 临时文件原子替换；索引是派生缓存，文件 mtime 变化自动重建。
