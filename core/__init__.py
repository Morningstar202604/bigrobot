"""BigRobot core 包。

统一在包导入时加载 .env，保证 `python -m uvicorn core.main:app`、`python gateway/bot.py`、
测试与脚本看到同一份配置。必须在任何模块读取 os.environ 之前执行，因此放在包初始化。
"""
from core.env import alias_legacy_env as _alias_legacy_env
from core.env import load_env as _load_env

_load_env()
# .env 缺失或未装 dotenv 时，load_env 也要保证旧前缀被映射；这里再兜一次，幂等。
_alias_legacy_env()
