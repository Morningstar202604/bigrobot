# 发布流程

[English](../RELEASING.md) · 中文

这份 runbook 让三个月没碰项目的人也能从头走完一次发布，不用猜。

## 版本号

遵循 [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html)。

| 递增 | 何时 | 例子 |
|---|---|---|
| MAJOR | 运维或 API 使用方需要改行为 | 删除配置键、重命名接口、需要手工步骤的迁移 |
| MINOR | 向后兼容的新能力 | 新工具、新页面、新可选依赖 |
| PATCH | 向后兼容的修复 | Bug、性能、依赖补丁、文档 |

版本号只存在三处，必须一致：

1. `core/version.py`
2. 根目录 `VERSION`
3. `pyproject.toml` 的 `[project] version`

`python scripts/check_version.py` 会校验，CI 也跑。

## 分支

`main` 是唯一长期分支，其余分支合并后删除。从 `main` 切出，squash 合回；合并后删除本地和所有远端的特性分支。

## 发布清单

### 1. 预检

```bash
git switch main
git pull --ff-only
python scripts/check_version.py
```

- [ ] 工作区干净，没有 stash。
- [ ] `CHANGELOG.md` 在“未发布”段落有本次条目的完整说明，面向读者而不是提交日志。
- [ ] `ROADMAP.md` 已移动实际完成项。
- [ ] 三处版本号一致。

### 2. 后端

```bash
python -m ruff check core executor gateway scripts tests
python -m pytest tests -q
```

- [ ] Ruff 无发现。
- [ ] Pytest 全过，跳过项有原因。
- [ ] 覆盖率不低于 CI 门槛。

### 3. 前端

```bash
cd frontend
npx tsc --noEmit
npx oxlint src
npm test
npm run build
```

- [ ] 类型检查干净。
- [ ] Lint 零错误。
- [ ] 单测通过。
- [ ] 生产构建成功。

### 4. 运行时冒烟

```bash
BIGROBOT_STATIC_DIR=frontend/dist python -m uvicorn core.main:app --port 8010
```

- [ ] `/healthz` 返回 `{"ok": true, "version": "<expected>"}`。
- [ ] `/readyz` 返回 200，包含 `db`、`kb`、`llm`、`search`。
- [ ] `/` 能打开控制台。
- [ ] 用管理员令牌登录，依次打开总览、会话、知识库、提醒、运行记录。
- [ ] 浏览器 devtools 没有错误。

README 截图在这一步重出（见 `scripts/take_screenshots.py`）。

### 5. 社区文件

- [ ] `SECURITY.md` 的联系方式可用。
- [ ] `CONTRIBUTING.md` 的命令还能跑。
- [ ] Issue/PR 模板与实际流程一致。

### 6. 打标签并发布

```bash
git add -A
git commit -m "chore(release): vX.Y.Z"
git tag -a vX.Y.Z -m "BigRobot vX.Y.Z"
git push origin main
git push origin vX.Y.Z
```

- [ ] 使用 annotated tag，不用 lightweight tag。
- [ ] 发布说明使用 `CHANGELOG.md` 对应段落，不写“看提交”。
- [ ] 同一轮推送所有镜像远端。

### 7. 发布后

- [ ] 把“未发布”内容移到本次版本标题，再开一个空的未发布段落。
- [ ] 部署实例的 `/healthz` 显示新版本。
- [ ] 如果改了配置键，同步 `.env.example` 和 `docs/zh/DEPLOY.md`。

## 镜像

同一份历史推到多个平台，不是独立 fork。

| 平台 | remote | 说明 |
|---|---|---|
| GitHub | `github-*` | 唯一运行 Actions 的平台，CI 以这里为准 |
| Gitee | `gitee` | 代码镜像，不在平台上重复写一套 CI |
| GitCode | `origin` | 代码镜像，不在平台上重复写一套 CI |

推送 `main` 和发布 tag 到所有已配置镜像。不要用 force-push 掩盖分叉；先查原因。各平台仓库介绍与标签保持一致。

## 回滚

1. 在 `main` 上 `git revert` 发布提交，不重写历史。
2. 发一个 PATCH 修复版本。
3. 如果是迁移问题，先按 `docs/zh/ARCHITECTURE.md` 的存储说明从备份恢复，再回滚代码。
