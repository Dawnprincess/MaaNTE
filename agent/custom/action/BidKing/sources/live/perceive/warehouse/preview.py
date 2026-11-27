# -*- coding: utf-8 -*-
"""仓库预览渲染（0b1b1/0b1b2）：网格、页边界、块状态与接缝。（调试使用）"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import cv2
import numpy as np

try:  # 实机：custom.action.BidKing.sources.live.perceive.warehouse
    from .....core.geometry import (
        COLS,
        PAGE_OFFSETS,
        ROWS,
        VISIBLE_ROWS,
        WAREHOUSE_VIEW,
        merge_row_ranges,
    )
except ImportError:  # 离线：BidKing/ 在 sys.path 上，顶层包导入
    from core.geometry import (
        COLS,
        PAGE_OFFSETS,
        ROWS,
        VISIBLE_ROWS,
        WAREHOUSE_VIEW,
        merge_row_ranges,
    )

from .blocks import PAGE_BOUNDARY_ROWS, BlockDetection


def render_preview(
    canvas: np.ndarray,
    view=WAREHOUSE_VIEW,
    page_offsets: Sequence[float] | None = None,
) -> np.ndarray:
    """在合并画布上画格子网格与 page 边界。

    `page_offsets` 为每页实际滚动行（可为小数）；缺省用名义 0/10/15。
    `used p*` 线是合并选择范围（策略线），保持名义值。
    """
    out = canvas.copy()
    height, width = out.shape[:2]
    cell_w = view[2] / COLS
    cell_h = view[3] / VISIBLE_ROWS

    '''
    grid_color = (40, 70, 40)
    for col in range(COLS + 1):
        x = min(width - 1, round(col * cell_w))
        cv2.line(out, (x, 0), (x, height - 1), grid_color, 1)
    for row in range(ROWS + 1):
        y = min(height - 1, round(row * cell_h))
        cv2.line(out, (0, y), (width - 1, y), grid_color, 1)

    offsets = list(page_offsets) if page_offsets is not None else list(PAGE_OFFSETS)
    while len(offsets) < len(PAGE_OFFSETS):
        offsets.append(float(PAGE_OFFSETS[len(offsets)]))
    '''

    # 页实际起始行：细线 + 标签
    '''
    for page, start in enumerate(offsets):
        y = min(height - 1, round(start * cell_h))
        cv2.line(out, (0, y), (width - 1, y), (200, 200, 0), 1)
        cv2.putText(
            out,
            f"page {page} start {start:.2f}",
            (4, min(height - 4, y + 14)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.38,
            (200, 200, 0),
            1,
            cv2.LINE_AA,
        )
    '''
    # 合并实际使用的行段：粗线 + 标签
    '''
    for page, start, end in merge_row_ranges():
        y = min(height - 1, round(start * cell_h))
        cv2.line(out, (0, y), (width - 1, y), (0, 220, 0), 2)
        cv2.putText(
            out,
            f"used p{page} {start}-{end - 1}",
            (4, min(height - 4, y + 28)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.38,
            (0, 255, 0),
            1,
            cv2.LINE_AA,
        )
        '''

    return out


_STATE_COLORS = {
    "silhouette": (225, 225, 225),
    "quality_silhouette": (0, 200, 255),
    "item": (0, 255, 0),
    "quality_hint": (0, 160, 255),
    "unknown": (0, 0, 180),
}

_STATE_ABBR = {
    "silhouette": "sil",
    "quality_silhouette": "qs",
    "item": "item",
    "quality_hint": "hint",
    "unknown": "unk",
}

# OpenCV 的 Hershey 字体不支持中文；调试图用 ASCII 品质缩写。
_QUALITY_ABBR = {"白": "W", "绿": "G", "蓝": "B", "紫": "P", "金": "Y", "红": "R"}


def _label_text(block) -> str:
    quality = _QUALITY_ABBR.get(block.quality, block.quality or "-")
    text = f"{block.block_id}:{_STATE_ABBR.get(block.state, block.state)} {quality}"
    if block.flags:
        text += " " + ",".join(block.flags)
    return text


def render_blocks_preview(
    canvas: np.ndarray,
    detection: BlockDetection,
    debug_edges: bool = False,
    page_offsets: Sequence[float] | None = None,
) -> np.ndarray:
    """在画布上画块 bbox、状态、歧义标记和可选的接缝线。

    这是 0b1b2 的 QA 图，不参与状态输出。
    """
    out = canvas.copy()
    height, width = out.shape[:2]
    cell_w = width / COLS
    cell_h = height / ROWS

    # 淡格子底图，便于对照坐标
    for col in range(COLS + 1):
        x = min(width - 1, round(col * cell_w))
        cv2.line(out, (x, 0), (x, height - 1), (32, 48, 32), 1)
    for row in range(ROWS + 1):
        y = min(height - 1, round(row * cell_h))
        cv2.line(out, (0, y), (width - 1, y), (32, 48, 32), 1)

    if debug_edges:
        for edge in detection.edges:
            if not edge.boundary:
                continue
            if edge.orientation == "v":
                x = round((edge.col + 1) * cell_w)
                y0 = round(edge.row * cell_h) + 5
                y1 = round((edge.row + 1) * cell_h) - 5
                cv2.line(out, (x, y0), (x, y1), (0, 0, 255), 1)
            else:
                y = round((edge.row + 1) * cell_h)
                x0 = round(edge.col * cell_w) + 5
                x1 = round((edge.col + 1) * cell_w) - 5
                cv2.line(out, (x0, y), (x1, y), (0, 0, 255), 1)

    for block in detection.blocks:
        r0, c0, r1, c1 = block.bbox
        x0 = round(c0 * cell_w)
        y0 = round(r0 * cell_h)
        x1 = round((c1 + 1) * cell_w) - 1
        y1 = round((r1 + 1) * cell_h) - 1
        color = _STATE_COLORS.get(block.state, (255, 255, 255))
        cv2.rectangle(out, (x0, y0), (x1, y1), color, 2)

        label = _label_text(block)
        text_y = min(height - 4, max(11, y0 + 11))
        cv2.putText(
            out,
            label,
            (x0 + 2, text_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.32,
            (0, 0, 0),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            out,
            label,
            (x0 + 2, text_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.32,
            color,
            1,
            cv2.LINE_AA,
        )

        if "ambiguous_1x1" in block.flags:
            cx = round((c0 + 0.5) * cell_w)
            cy = round((r0 + 0.5) * cell_h)
            cv2.circle(out, (cx, cy), 7, (255, 0, 255), 2)
            cv2.putText(
                out,
                "?",
                (cx - 4, cy + 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.35,
                (255, 0, 255),
                1,
                cv2.LINE_AA,
            )

    if debug_edges:
        for row in PAGE_BOUNDARY_ROWS:
            y = min(height - 1, round(row * cell_h))
            cv2.line(out, (0, y), (width - 1, y), (200, 200, 0), 1)

    return out


def save_preview(path: Path | str, image: np.ndarray) -> bool:
    """保存预览 PNG；失败返回 False。"""
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return bool(cv2.imwrite(str(path), image))
    except Exception:
        return False


__all__ = ["render_preview", "render_blocks_preview", "save_preview"]
