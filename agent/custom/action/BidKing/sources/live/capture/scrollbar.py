# -*- coding: utf-8 -*-
"""拍卖之王 - 滑条几何、thumb 检测与多页采集。

本模块只做「滚动 + 截图」的机械动作：
  - `find_thumb_center` 从一帧里找滑条 thumb 的亮度中心；
  - `drag_thumb` 拖拽滑条；
  - `capture_pages` 按顶/中/底三页采集，失败不抛出。

不做物品识别，不做网格映射；这些属于感知层（0b1b+）。
"""

from __future__ import annotations

import time
from typing import Callable, Optional, Sequence

import cv2

from utils.logger import logger

# 包裹总行数 / 可见行数（10×25 容器）
TOTAL_ROWS = 25
VISIBLE_ROWS = 10

# 三页对应的滚动行偏移：顶部 0；中部 10；底部 15
PAGE_OFFSETS = (0, 10, 15)

# 拖动后等待滚动 + 物品刷新动画落定的时间（秒）；实测 1.3s。
SCROLL_SETTLE_SECONDS = 1.3

# 亮条阈值：行均值 > 总体均值 + factor × 标准差
THUMB_THRESHOLD_FACTOR = 0.5
# 最短 thumb 高度；低于它认为没检测到
MIN_THUMB_HEIGHT = 20

# ============ 纯几何 ============


def thumb_center_y(roi) -> float:
    """thumb ROI 的纵向中心。"""
    return roi[1] + roi[3] / 2.0


def target_center_y(
    track_roi,
    thumb_h: int,
    offset_rows: int,
    total_rows: int = TOTAL_ROWS,
    visible_rows: int = VISIBLE_ROWS,
) -> float:
    """把「滚动行偏移」换算成 thumb 中心 y。"""
    track_top, track_h = track_roi[1], track_roi[3]
    travel = track_h - thumb_h
    max_offset = max(1, total_rows - visible_rows)
    ratio = min(max(offset_rows, 0), max_offset) / max_offset
    return track_top + thumb_h / 2.0 + ratio * travel


def offset_rows(
    center_y: float,
    track_roi,
    thumb_h: int,
    total_rows: int = TOTAL_ROWS,
    visible_rows: int = VISIBLE_ROWS,
) -> float:
    """把 thumb 中心 y 反算成滚动行偏移（用于日志/校准）。"""
    track_top, track_h = track_roi[1], track_roi[3]
    travel = track_h - thumb_h
    if travel <= 0:
        return 0.0
    ratio = (center_y - (track_top + thumb_h / 2.0)) / travel
    return ratio * max(0, total_rows - visible_rows)


# ============ thumb 检测 ============


def find_thumb_center(frame, track_roi) -> float:
    """
    在轨道 ROI 内找最长的亮条，返回其纵向中心；找不到则返回轨道几何中心。

    只比较像素亮度，不认识滑条语义。
    """
    x, y, w, h = [int(v) for v in track_roi]
    fallback = y + h / 2.0
    if frame is None or w <= 0 or h <= 0:
        return fallback

    height, width = frame.shape[:2]
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(width, x + w), min(height, y + h)
    if x2 <= x1 or y2 <= y1:
        return fallback

    strip = frame[y1:y2, x1:x2]
    gray = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY) if strip.ndim == 3 else strip
    rows = gray.mean(axis=1)
    threshold = float(rows.mean() + THUMB_THRESHOLD_FACTOR * rows.std())
    run = _longest_run(rows > threshold)
    if run is None or run[1] - run[0] < MIN_THUMB_HEIGHT:
        logger.warning("⚠️ 未检测到滑条 thumb，回退轨道中心")
        return fallback
    return y1 + (run[0] + run[1]) / 2.0


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


# ============ 拖动与采集 ============


def drag_thumb(
    controller,
    from_xy: tuple[float, float],
    to_xy: tuple[float, float],
    steps: int = 6,
    step_delay: float = 0.03,
) -> bool:
    """拖动滑条 thumb；失败只告警，返回 False。"""
    fx, fy = from_xy
    tx, ty = to_xy
    try:
        controller.post_touch_move(int(fx), int(fy)).wait()
        time.sleep(0.05)
        controller.post_touch_down(int(fx), int(fy)).wait()
        for index in range(1, steps + 1):
            x = fx + (tx - fx) * index / steps
            y = fy + (ty - fy) * index / steps
            controller.post_touch_move(int(x), int(y)).wait()
            time.sleep(step_delay)
        controller.post_touch_up().wait()
        return True
    except Exception as exc:  # noqa: BLE001 - 采集失败不得中断出价
        logger.warning("⚠️ 拖动滑条失败: %s", exc)
        return False


def capture_pages(
    grab: Callable[[], object],
    drag: Callable[[tuple[float, float], tuple[float, float]], bool],
    settle: Callable[[], None],
    track_roi,
    thumb_h: int,
    should_stop: Optional[Callable[[], bool]] = None,
) -> list:
    """
    按顶/中/底三页采集。

    - `grab()` 返回一帧图像或 None；
    - `drag(from_xy, to_xy)` 拖动滑条；
    - `settle()` 等待滚动落定；
    - 返回长度固定为 3 的列表，失败页为 None。

    任何异常都只写日志，不向调用方抛出。
    """
    pages: list = []
    try:
        first = grab()
    except Exception as exc:  # noqa: BLE001
        logger.warning("⚠️ 首次截图失败，无法定位滑条: %s", exc)
        first = None

    current_y = find_thumb_center(first, track_roi)
    center_x = track_roi[0] + track_roi[2] / 2.0
    targets = [target_center_y(track_roi, thumb_h, offset) for offset in PAGE_OFFSETS]
    logger.info(
        "📏 滑条 thumb=%.1f，目标=%s",
        current_y,
        "/".join(f"{target:.1f}" for target in targets),
    )

    for index, offset in enumerate(PAGE_OFFSETS):
        if should_stop is not None and should_stop():
            break
        target_y = targets[index]
        try:
            drag((center_x, current_y), (center_x, target_y))
            settle()
            page = grab()
        except Exception as exc:  # noqa: BLE001
            logger.warning("⚠️ 采集第 %d 页失败: %s", index + 1, exc)
            page = None
        pages.append(page)
        current_y = target_y

    while len(pages) < len(PAGE_OFFSETS):
        pages.append(None)
    return pages


def capture_live_pages(
    controller,
    track_roi,
    thumb_h: int,
    should_stop: Optional[Callable[[], bool]] = None,
) -> list:
    """实机包装：注入截图、拖拽与滚动等待。"""
    from ..utils import get_image

    def grab():
        return get_image(controller)

    def drag(from_xy, to_xy):
        return drag_thumb(controller, from_xy, to_xy)

    def settle():
        time.sleep(SCROLL_SETTLE_SECONDS)

    return capture_pages(grab, drag, settle, track_roi, thumb_h, should_stop)


__all__ = [
    "TOTAL_ROWS",
    "VISIBLE_ROWS",
    "PAGE_OFFSETS",
    "thumb_center_y",
    "target_center_y",
    "offset_rows",
    "find_thumb_center",
    "drag_thumb",
    "capture_pages",
    "capture_live_pages",
]
