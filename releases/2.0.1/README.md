# BigRobot 2.0.1 — Windows x64

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `bigrobot-2.0.1-win64.exe` | 45,188,603 B（43.1 MiB） | `5d457cf0d0535762fac429d4b8b594d73bacbb59d7f036525b0dba19d321683a` |

单文件、免安装，不需要目标机器装 Python。适用于 Windows 10/11 x64。首次运行会在用户数据目录创建 `bigrobot-data/`。

校验：

```powershell
Get-FileHash .\bigrobot-2.0.1-win64.exe -Algorithm SHA256
Get-Content .\SHA256SUMS.txt
```

包由 GitHub Actions 的 `windows-latest` 构建，`scripts/build_exe.py` 已跑过 `/healthz`、`/readyz`、首页和一次真实工具调用冒烟。构建提交 `94c25ba`。

**未做代码签名**，Windows SmartScreen 可能拦截，选择「更多信息 → 仍要运行」；企业环境请先用上面的 SHA-256 核验。

源码与发布说明见仓库根目录 `CHANGELOG.md` 的 2.0.1 段。
