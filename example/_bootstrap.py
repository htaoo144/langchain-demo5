"""example 目录公共引导：把项目根目录加入 sys.path，并统一控制台 UTF-8 编码。

每个示例文件第一行都必须 `from _bootstrap import *`。
运行方式（在项目根目录下）：
    python example/1_config_example.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
