# -*- coding: utf-8 -*-
"""拍卖之王 - 离线仓库感知。

本包只读已保存的会话帧，不依赖 MaaFramework，也不修改实时流程。
0b1b1 只做三页映射/合并/预览；格子分类与 WarehouseState 在后续子阶段加入。
"""

from .frames import (
    build_canvas,
    crop_view,
    detect_page_offsets,
    find_thumb_center,
    load_events,
    load_page_frames,
)
from .preview import render_preview, save_preview

__all__ = [
    "build_canvas",
    "crop_view",
    "detect_page_offsets",
    "find_thumb_center",
    "load_events",
    "load_page_frames",
    "render_preview",
    "save_preview",
]
