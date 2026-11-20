# 路由消费者审计

[English](../route-audit.md) · 中文

统计口径：`app.openapi()["paths"]`，逐条在 `frontend/src`、`scripts`、`tests`、`gateway` 中搜索调用点。占位符 `{x}` 按路径段匹配（`[^/'"]+`），能命中 `${...}` 模板字符串。

**容易踩的坑**：

1. 用转义后的字面量 `{group_id}` 去搜，会把所有带参数路由误判成“没人用”。曾误报 31 条，真实是 3 条。
2. 只扫 `.ts/.tsx` 会漏 `.jsx`。`OperatorDesk.jsx` 一直在调 `/api/operator/notes/{sid}`，漏扫就会误删在用的接口。

当前唯一没有消费者的路由是 `/api/debug/conn`。它默认返回 404，只有 `BIGROBOT_DEV=1` 才可用。

维护约定：新增路由必须同时有调用点或测试，否则不合并；删除前先跑本审计。
