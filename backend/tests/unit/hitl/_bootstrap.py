"""测试引导：不依赖 conftest.py（归 Teammate 4），直接把 backend/ 加入 sys.path。"""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[3]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
