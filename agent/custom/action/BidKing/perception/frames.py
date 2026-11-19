# -*- coding: utf-8 -*-
"""会话帧读取与三页合并（0b1b1）。

只做几何：把每回合的三页仓库帧按绝对行合并成 10×25 画布。
不做格子分类、不识别物品、不写状态。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Sequence

import cv2
import numpy as np

from core.geometry import (
    COLS,
    PAGE_OFFSETS,
    ROWS,
    VISIBLE_ROWS,
    WAREHOUSE_SCROLLBAR_TRACK,
    WAREHOUSE_THUMB_TOP,
    WAREHOUSE_VIEW,
    merge_page_for_row,
)


def load_events(session_dir: Path | str) -> list[dict]:
    """读 events.jsonl；坏行跳过。"""
    path = Path(session_dir) / "events.jsonl"
    events: list[dict] = []
    if not path.exists():
        return events
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except Exception:
            continue
    return events


def load_page_frames(
    session_dir: Path | str, event: dict
) -> list[Optional[np.ndarray]]:
    """按事件里的 frames 顺序读三页；缺失/读不到的位置为 None。"""
    frames_dir = Path(session_dir) / "frames"
    pages: list[Optional[np.ndarray]] = []
    for name in (event.get("frames") or [])[: len(PAGE_OFFSETS)]:
        path = frames_dir / str(name)
        image = cv2.imread(str(path)) if path.exists() else None
        pages.append(image)
    while len(pages) < len(PAGE_OFFSETS):
        pages.append(None)
    return pages


def crop_view(frame: Optional[np.ndarray], view=WAREHOUSE_VIEW) -> Optional[np.ndarray]:
    """裁出 10×10 紧视口；越界收敛。"""
    if frame is None:
        return None
    x, y, w, h = view
    height, width = frame.shape[:2]
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(width, x + w), min(height, y + h)
    if x2 <= x1 or y2 <= y1:
        return None
    return frame[y1:y2, x1:x2]


def _longest_run(mask) -> Optional[tuple[int, int]]:
    best = None
    start = None
    for index, value in enumerate(mask):
        if value and start is None:
            start = index
        elif not value and start is not None:
            if best is None or index - start > best[1] - best[0]:
                best = (start, index)
            start = None
    if start is not None:
        if best is None or len(mask) - start > best[1] - best[0]:
            best = (start, len(mask))
    return best


def find_thumb_center(
    frame: Optional[np.ndarray], track_roi=WAREHOUSE_SCROLLBAR_TRACK
) -> Optional[float]:
    """从一帧里找滑条 thumb 的亮度中心；找不到返回 None。"""
    if frame is None:
        return None
    x, y, w, h = [int(v) for v in track_roi]
    height, width = frame.shape[:2]
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(width, x + w), min(height, y + h)
    if x2 <= x1 or y2 <= y1:
        return None
    strip = frame[y1:y2, x1:x2]
    gray = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY) if strip.ndim == 3 else strip
    rows = gray.mean(axis=1)
    threshold = float(rows.mean() + 0.5 * rows.std())
    run = _longest_run(rows > threshold)
    if run is None or run[1] - run[0] < 20:
        return None
    return y1 + (run[0] + run[1]) / 2.0


def _offset_rows(center_y: float, track_roi, thumb_h: int) -> float:
    track_top, track_h = track_roi[1], track_roi[3]
    travel = track_h - thumb_h
    if travel <= 0:
        return 0.0
    ratio = (center_y - (track_top + thumb_h / 2.0)) / travel
    return ratio * max(0, ROWS - VISIBLE_ROWS)


def _grid_phase(
    frame: Optional[np.ndarray], view=WAREHOUSE_VIEW, cell_h: Optional[float] = None
) -> Optional[float]:
    """用视口内横向格线估计网格相位（0..cell_h）；不可靠时返回 None。"""
    if frame is None:
        return None
    x, y, w, h = [int(v) for v in view]
    height, width = frame.shape[:2]
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(width, x + w), min(height, y + h)
    if x2 <= x1 or y2 - y1 < 10:
        return None

    gray = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
    profile = np.abs(np.diff(gray.astype(np.float32), axis=0)).mean(axis=1)
    if profile.size == 0 or float(profile.max()) < 8.0:
        return None

    if cell_h is None:
        cell_h = (y2 - y1) / VISIBLE_ROWS
    scores: list[tuple[float, float]] = []
    for phase in np.arange(0.0, cell_h, 0.25):
        score = 0.0
        line = phase
        while line < profile.size:
            index = int(round(line)) - 1
            if 0 <= index < profile.size:
                lo, hi = max(0, index - 1), min(profile.size, index + 2)
                score += float(profile[lo:hi].max())
            line += cell_h
        scores.append((float(phase), score))

    best_phase, best_score = max(scores, key=lambda item: item[1])
    mean_score = sum(score for _, score in scores) / len(scores)
    if best_score <= mean_score * 1.15:
        return None
    return best_phase


def detect_page_offsets(
    pages: Sequence[Optional[np.ndarray]],
    view=WAREHOUSE_VIEW,
    track_roi=WAREHOUSE_SCROLLBAR_TRACK,
    thumb_h: int = WAREHOUSE_THUMB_TOP[3],
) -> list[float]:
    """
    检测每页实际滚动行偏移。

    优先用格子相位（可识别 page1 顶部被视口截掉 0.2 行这类情况）；
    格子不可靠时回退滑条 thumb，再回退名义 0/10/15。
    """
    cell_h = view[3] / VISIBLE_ROWS
    offsets: list[float] = []
    for page, nominal in enumerate(PAGE_OFFSETS):
        frame = pages[page] if page < len(pages) else None
        phase = _grid_phase(frame, view, cell_h)
        if phase is not None:
            line_row = round(nominal + phase / cell_h)
            offsets.append(float(line_row - phase / cell_h))
            continue
        center = find_thumb_center(frame, track_roi)
        offsets.append(
            _offset_rows(center, track_roi, thumb_h) if center is not None else float(nominal)
        )
    return offsets


def build_canvas(
    pages: Sequence[Optional[np.ndarray]],
    view=WAREHOUSE_VIEW,
    page_offsets: Optional[Sequence[float]] = None,
) -> np.ndarray:
    """
    把三页合并成 10×25 画布（宽=视口宽，高=25×格子高）。

    行来源：0–9 page0；10–17 page1；18–24 page2。
    `page_offsets` 是每页实际滚动行（可为小数）；缺省用 0/10/15。
    缺失页对应行保持黑色。
    """
    view_w, view_h = view[2], view[3]
    cell_w = view_w / COLS
    cell_h = view_h / VISIBLE_ROWS
    canvas_h = int(round(ROWS * cell_h))
    canvas = np.zeros((canvas_h, view_w, 3), dtype=np.uint8)

    offsets = list(page_offsets) if page_offsets is not None else list(PAGE_OFFSETS)
    while len(offsets) < len(PAGE_OFFSETS):
        offsets.append(float(PAGE_OFFSETS[len(offsets)]))

    for row in range(ROWS):
        page = merge_page_for_row(row)
        frame = pages[page] if page < len(pages) else None
        if frame is None:
            continue

        row_in_view = row - offsets[page]
        # 允许轻微负值：页面实际滚动超过名义行时，该行顶部在视口上沿之外，
        # 但完整原始帧里仍有像素，必须取回来才能保持顶部格子完整。
        if not -1.0 <= row_in_view < VISIBLE_ROWS:
            continue
        src_y0 = view[1] + round(row_in_view * cell_h)
        src_y1 = view[1] + round((row_in_view + 1) * cell_h)
        if src_y0 < 0 or src_y1 > frame.shape[0]:
            continue
        dst_y0 = round(row * cell_h)
        dst_y1 = round((row + 1) * cell_h)

        src = frame[src_y0:src_y1, view[0] : view[0] + view_w]
        if src.size == 0:
            continue
        if src.shape[1] != view_w:
            src = cv2.resize(src, (view_w, dst_y1 - dst_y0))
        elif src.shape[0] != dst_y1 - dst_y0:
            src = cv2.resize(src, (view_w, dst_y1 - dst_y0))
        canvas[dst_y0:dst_y1, :] = src

    return canvas


def page_coverage(pages: Sequence[Optional[np.ndarray]]) -> list[tuple[int, int, int]]:
    """返回 [(page, start_row, end_row), ...]，只列可用页。"""
    result = []
    for page, _offset in enumerate(PAGE_OFFSETS):
        if page < len(pages) and pages[page] is not None:
            start = PAGE_OFFSETS[page]
            end = min(start + VISIBLE_ROWS, ROWS)
            result.append((page, start, end))
    return result


__all__ = [
    "load_events",
    "load_page_frames",
    "crop_view",
    "find_thumb_center",
    "detect_page_offsets",
    "build_canvas",
    "page_coverage",
]
