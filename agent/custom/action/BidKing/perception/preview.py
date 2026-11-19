# -*- coding: utf-8 -*-
"""仓库预览渲染（0b1b1）：网格、页边界、来源标签。"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import cv2
import numpy as np

from core.geometry import (
    COLS,
    PAGE_OFFSETS,
    ROWS,
    VISIBLE_ROWS,
    WAREHOUSE_VIEW,
    merge_row_ranges,
)


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

    # 页实际起始行：细线 + 标签
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

    # 合并实际使用的行段：粗线 + 标签
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

    return out


def save_preview(path: Path | str, image: np.ndarray) -> bool:
    """保存预览 PNG；失败返回 False。"""
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return bool(cv2.imwrite(str(path), image))
    except Exception:
        return False


__all__ = ["render_preview", "save_preview"]
