# BigRobot 2.0.2 — Windows x64

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `bigrobot-2.0.2-win64.exe` | 45,188,054 B（43.1 MiB） | `dd99ac3235cc272187e74b6e511178e1c1c7ab3cc1c417a343cc5668b947ce5f` |

单文件、免安装，不需要目标机器装 Python。适用于 Windows 10/11 x64。首次运行会在用户数据目录创建 `bigrobot-data/`。

校验：

```powershell
Get-FileHash .\bigrobot-2.0.2-win64.exe -Algorithm SHA256
Get-Content .\SHA256SUMS.txt
```

包由 GitHub Actions 的 `windows-latest` 构建，`scripts/build_exe.py` 已跑过 `/healthz`、`/readyz`、首页和一次真实工具调用冒烟。构建提交 `5469cb3`。

**未做代码签名**，Windows SmartScreen 可能拦截，选择「更多信息 → 仍要运行」；企业环境请先用上面的 SHA-256 核验。

源码与发布说明见仓库根目录 `CHANGELOG.md` 的 2.0.2 段。
