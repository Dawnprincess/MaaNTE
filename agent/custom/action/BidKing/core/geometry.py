# -*- coding: utf-8 -*-
"""拍卖之王 - 仓库几何（核心层，零框架依赖）

10×25 包裹、10×10 可见视口、三页滚动偏移与绝对行/格子坐标。
采集（sources/live）与离线感知（perception）共用这一份常量，避免两套坐标漂移。

0 基约定：
    page 0 -> 绝对行 0..9
    page 1 -> 绝对行 10..19
    page 2 -> 绝对行 15..24
    page 0/1 边界 9/10；page 1/2 在 15..19 重叠。

合并时：
    行 0..9 用 page 0
    行 10..17 用 page 1（避开 page 1 底部 18..19 边缘）
    行 18..24 用 page 2（避开 page 2 顶部 15..17 边缘）
"""

from __future__ import annotations

COLS = 10
ROWS = 25
VISIBLE_ROWS = 10

# 三页的绝对起始行
PAGE_OFFSETS = (0, 10, 15)

# 合并后的行来源切换点（0 基）
_MERGE_PAGE1_END = 18

# 局内/结算 10×10 紧视口（不含滑条）
# 实测格子网格从 x=876 到 x=1251（10×37.5），右侧 2px 是边框/间隙。
WAREHOUSE_VIEW = (876, 144, 375, 375)
SETTLEMENT_VIEW = (876, 144, 375, 375)

# 局内滑条：轨道与 thumb 参考位置（检测/测试/几何用；
# 实际拖拽目标由 sources/live/capture/scrollbar.CAPTURE_PAGE_OFFSETS 计算）
WAREHOUSE_SCROLLBAR_TRACK = (1255, 152, 6, 357)
WAREHOUSE_THUMB_TOP = (1255, 152, 6, 143)
WAREHOUSE_THUMB_MID = (1255, 291, 6, 145)
WAREHOUSE_THUMB_BOTTOM = (1255, 363, 6, 146)

# 结算包裹与局内使用同一套视口/滑条（实机确认）
SETTLEMENT_SCROLLBAR_TRACK = (1255, 152, 6, 357)
SETTLEMENT_THUMB_TOP = (1255, 152, 6, 143)
SETTLEMENT_THUMB_MID = (1255, 291, 6, 145)
SETTLEMENT_THUMB_BOTTOM = (1255, 363, 6, 146)


def page_row_range(page: int) -> range:
    """某一页覆盖的绝对行范围（0 基，末端不含）。"""
    if not 0 <= page < len(PAGE_OFFSETS):
        raise ValueError(f"page 越界: {page}")
    start = PAGE_OFFSETS[page]
    return range(start, min(start + VISIBLE_ROWS, ROWS))


def merge_page_for_row(row: int) -> int:
    """合并后某个绝对行取自哪一页。"""
    if not 0 <= row < ROWS:
        raise ValueError(f"row 越界: {row}")
    if row < PAGE_OFFSETS[1]:
        return 0
    if row < _MERGE_PAGE1_END:
        return 1
    return 2


def merge_row_ranges() -> tuple[tuple[int, int, int], ...]:
    """(page, start_row, end_row) 列表，end 不含。"""
    return (
        (0, 0, PAGE_OFFSETS[1]),
        (1, PAGE_OFFSETS[1], _MERGE_PAGE1_END),
        (2, _MERGE_PAGE1_END, ROWS),
    )


def cell_size(view=WAREHOUSE_VIEW) -> tuple[float, float]:
    """视口内单个格子的宽/高（像素，浮点）。"""
    return view[2] / COLS, view[3] / VISIBLE_ROWS


def cell_rect(col: int, row_in_view: int, view=WAREHOUSE_VIEW) -> tuple[int, int, int, int]:
    """视口内第 (col, row_in_view) 个格子的像素矩形 [x, y, w, h]。"""
    if not 0 <= col < COLS:
        raise ValueError(f"col 越界: {col}")
    if not 0 <= row_in_view < VISIBLE_ROWS:
        raise ValueError(f"row_in_view 越界: {row_in_view}")
    cell_w, cell_h = cell_size(view)
    x0 = view[0] + round(col * cell_w)
    x1 = view[0] + round((col + 1) * cell_w)
    y0 = view[1] + round(row_in_view * cell_h)
    y1 = view[1] + round((row_in_view + 1) * cell_h)
    return x0, y0, x1 - x0, y1 - y0


def page_cell_rect(
    col: int, row_abs: int, page: int, view=WAREHOUSE_VIEW
) -> tuple[int, int, int, int]:
    """某一页里、绝对行 row_abs 的格子矩形。"""
    row_in_view = row_abs - PAGE_OFFSETS[page]
    if not 0 <= row_in_view < VISIBLE_ROWS:
        raise ValueError(f"row {row_abs} 不在 page {page} 的可见范围内")
    return cell_rect(col, row_in_view, view)


__all__ = [
    "COLS",
    "ROWS",
    "VISIBLE_ROWS",
    "PAGE_OFFSETS",
    "WAREHOUSE_VIEW",
    "SETTLEMENT_VIEW",
    "WAREHOUSE_SCROLLBAR_TRACK",
    "WAREHOUSE_THUMB_TOP",
    "WAREHOUSE_THUMB_MID",
    "WAREHOUSE_THUMB_BOTTOM",
    "SETTLEMENT_SCROLLBAR_TRACK",
    "SETTLEMENT_THUMB_TOP",
    "SETTLEMENT_THUMB_MID",
    "SETTLEMENT_THUMB_BOTTOM",
    "page_row_range",
    "merge_page_for_row",
    "merge_row_ranges",
    "cell_size",
    "cell_rect",
    "page_cell_rect",
]
