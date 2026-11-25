# -*- coding: utf-8 -*-
"""局内仓库的纯感知库（0b1b1/0b1b2）。

本子包不依赖 MaaFramework / utils，只依赖 cv2/numpy 与 `core.geometry`；
实时感知（observe_round）、定盘预览（capture_settlement）、离线 CLI 与 pytest
共用同一份实现。包导入本身必须保持框架无关，分层守卫会检查。
"""

from .blocks import (
    PERCEPTION_VERSION,
    Block,
    BlockDetection,
    EdgeScore,
    detect_blocks,
)
from .frames import (
    build_canvas,
    crop_view,
    detect_page_offsets,
    find_thumb_center,
    load_events,
    load_page_frames,
)
from .palette import PALETTE_VERSION, classify_bgr
from .preview import render_blocks_preview, render_preview, save_preview
from .round import RoundPerception, perceive_round
from .session import PreviewResult, generate_session_previews

__all__ = [
    "PERCEPTION_VERSION",
    "PALETTE_VERSION",
    "Block",
    "BlockDetection",
    "EdgeScore",
    "RoundPerception",
    "PreviewResult",
    "build_canvas",
    "classify_bgr",
    "crop_view",
    "detect_blocks",
    "detect_page_offsets",
    "find_thumb_center",
    "generate_session_previews",
    "load_events",
    "load_page_frames",
    "perceive_round",
    "render_blocks_preview",
    "render_preview",
    "save_preview",
]
