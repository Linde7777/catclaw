import os
from pathlib import Path

# 注意：这里必须在 import 项目代码之前生效。
# 否则 `src/commons.py` 等模块在 import 阶段就会把默认路径缓存到 `~/.bionic-bot`，
# 在 Codex CLI 沙盒里会因为只读而导致测试失败。
_ROOT = Path("/tmp/bionic-bot-pytest")
_MEMORIES_ROOT = _ROOT / "memories"
_ROOT.mkdir(parents=True, exist_ok=True)
_MEMORIES_ROOT.mkdir(parents=True, exist_ok=True)
os.environ["BIONIC_BOT_ROOT"] = str(_ROOT)
os.environ["BIONIC_BOT_MEMORIES_ROOT"] = str(_MEMORIES_ROOT)
