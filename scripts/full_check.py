"""一条命令跑完全部检查：后端测试、静态检查、前端 lint/测试/构建、路由统计。

用法：
    python scripts/full_check.py            # 全部
    python scripts/full_check.py --fast     # 跳过 pytest（约 3.5 分钟）

任何一步失败都会继续跑完，最后给出汇总表并以非零退出码结束——
这样 CI 里看到的是一张完整报告，而不是"第一个错误就中断"。
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAST = "--fast" in sys.argv


def run(name: str, cmd: list[str], cwd: Path | None = None, env: dict | None = None) -> tuple[str, bool, str]:
    started = time.time()
    merged = {**os.environ, **(env or {})}
    try:
        p = subprocess.run(cmd, cwd=cwd or ROOT, capture_output=True, text=True, timeout=900, env=merged)
        ok = p.returncode == 0
        tail = (p.stdout + p.stderr).strip().splitlines()
        detail = tail[-1] if tail else ""
    except subprocess.TimeoutExpired:
        ok, detail = False, "超时（>900s）"
    return name, ok, f"{detail[:90]}  ({time.time() - started:.1f}s)"


def main() -> int:
    checks: list[tuple[str, bool, str]] = []
    checks.append(run("ruff", [sys.executable, "-m", "ruff", "check", "core", "executor", "gateway", "scripts", "tests"]))
    checks.append(run("mypy", [sys.executable, "-m", "mypy", "core", "executor", "gateway"]))
    if FAST:
        checks.append(("pytest", True, "已跳过（--fast）"))
    else:
        checks.append(run("pytest", [sys.executable, "-m", "pytest", "tests", "-q"]))
    checks.append(run("oxlint", ["npx", "oxlint", "src"], cwd=ROOT / "frontend"))
    checks.append(run("vitest", ["npm", "test", "--silent"], cwd=ROOT / "frontend"))
    checks.append(run("build", ["npm", "run", "build"], cwd=ROOT / "frontend"))
    checks.append(run("routes", [sys.executable, "-c",
                                 "from core.main import create_app;print(len(create_app().openapi()['paths']))"],
                       env={"ADMIN_TOKEN": "t", "BIGROBOT_DB": "/tmp/fullcheck.db"}))
    checks.append(run("harness", [sys.executable, "scripts/harness_all.py"]))

    width = max(len(c[0]) for c in checks)
    print("\n" + "=" * 60)
    failed = 0
    for name, ok, detail in checks:
        print(f"{name.ljust(width)}  {'PASS' if ok else 'FAIL'}  {detail}")
        failed += 0 if ok else 1
    print("=" * 60)
    print(f"{len(checks) - failed}/{len(checks)} 通过")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
