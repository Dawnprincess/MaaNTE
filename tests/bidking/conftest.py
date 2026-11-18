import sys
from pathlib import Path

# 让测试以顶层包导入 core / sources（与 tools/replay.py 的方式一致），
# 不经过 custom.action，避免加载 MaaFramework。
BIDKING_DIR = (
    Path(__file__).resolve().parents[2] / "agent" / "custom" / "action" / "BidKing"
)
if str(BIDKING_DIR) not in sys.path:
    sys.path.insert(0, str(BIDKING_DIR))

# recorder 等实机模块会 import `utils.logger`；只加路径，不 import custom.action。
AGENT_DIR = BIDKING_DIR.parents[2]
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))
