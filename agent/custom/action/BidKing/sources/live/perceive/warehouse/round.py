# -*- coding: utf-8 -*-
"""单回合仓库感知编排（0b1b2）。

把三页原始帧变成 RoundPerception：实际页偏移、10×25 画布、块检测结果。
本模块是实时感知层的一部分，但**不依赖 MaaFramework**：观察窗口在截完图后
直接调用，离线工具/测试也可以对历史帧重放。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

try:  # 实机：custom.action.BidKing.sources.live.perceive.warehouse
    from .....core.geometry import (
        WAREHOUSE_SCROLLBAR_TRACK,
        WAREHOUSE_THUMB_TOP,
        WAREHOUSE_VIEW,
    )
except ImportError:  # 离线：BidKing/ 在 sys.path 上，顶层包导入
    from core.geometry import (
        WAREHOUSE_SCROLLBAR_TRACK,
        WAREHOUSE_THUMB_TOP,
        WAREHOUSE_VIEW,
    )

from .blocks import BlockDetection, detect_blocks
from .frames import build_canvas, detect_page_offsets


@dataclass
class RoundPerception:
    """一轮观察窗口的仓库感知结果。"""

    pages: list[Optional[np.ndarray]]
    offsets: list[float]
    canvas: np.ndarray
    detection: BlockDetection


def perceive_round(
    pages: Sequence[Optional[np.ndarray]],
    view=WAREHOUSE_VIEW,
    track_roi=WAREHOUSE_SCROLLBAR_TRACK,
    thumb_h: int = WAREHOUSE_THUMB_TOP[3],
) -> RoundPerception:
    """三页帧 -> 实际页偏移 -> 10×25 画布 -> 块检测。"""
    # normalized补页，确保下游固定看到3页
    normalized = list(pages or [])
    while len(normalized) < 3:
        normalized.append(None)

    offsets = detect_page_offsets(normalized, view, track_roi, thumb_h)
    canvas = build_canvas(normalized, view=view, page_offsets=offsets)
    detection = detect_blocks(canvas)
    return RoundPerception(
        pages=normalized,
        offsets=offsets,
        canvas=canvas,
        detection=detection,
    )


__all__ = ["RoundPerception", "perceive_round"]
