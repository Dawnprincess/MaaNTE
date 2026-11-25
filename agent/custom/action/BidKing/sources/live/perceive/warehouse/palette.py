# -*- coding: utf-8 -*-
"""局内仓库品质调色板（0b1b2）。

只做 BGR -> 品质/灰/白的分类；不读物品表、不做图标匹配。
颜色原型来自局内实帧样本：

    紫  fill≈BGR(83,27,71)   border≈(130,46,111)
    绿  fill≈(16,78,47)      border≈(72,235,133)
    金  fill≈(45,95,137)     border≈(126,192,249)
    红  fill≈(45,15,132)     border 亮红
    蓝  fill≈(117,81,20)     border 亮蓝
    白  fill≈(205,212,208)   border 近白
    灰轮廓 fill≈(59,59,59)   border≈(80..114)

OpenCV 的 hue 范围是 0..179；红色跨 0，用环形距离。
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

PALETTE_VERSION = "0b1b2.1"

# 与 core.catalog.QUALITIES 保持一致
QUALITY_NAMES = ("白", "绿", "蓝", "紫", "金", "红")
GRAY = "灰"
WHITE = "白"


@dataclass(frozen=True)
class QualitySpec:
    name: str
    hue: int
    hue_tol: int
    sat_min: int
    val_min: int


# 白/灰用无彩色规则判断，这里只列彩色品质。
COLOR_SPECS: tuple[QualitySpec, ...] = (
    QualitySpec("绿", 45, 14, 115, 55),
    QualitySpec("蓝", 102, 14, 105, 55),
    QualitySpec("紫", 143, 12, 100, 50),
    QualitySpec("金", 17, 10, 110, 55),
    QualitySpec("红", 174, 12, 145, 50),
)


def hue_distance(a: int, b: int) -> int:
    """OpenCV hue 的环形距离（0..90）。"""
    diff = abs(int(a) - int(b)) % 180
    return min(diff, 180 - diff)


def _as_hsv(bgr) -> tuple[int, int, int]:
    b, g, r = (int(round(float(v))) for v in np.asarray(bgr).reshape(-1)[:3])
    b = max(0, min(255, b))
    g = max(0, min(255, g))
    r = max(0, min(255, r))
    h, s, v = cv2.cvtColor(np.uint8([[[b, g, r]]]), cv2.COLOR_BGR2HSV)[0, 0]
    return int(h), int(s), int(v)


def classify_bgr(bgr) -> str | None:
    """把一个颜色分类为品质名 / '灰' / '白' / None。

    白与灰都要求低饱和：白靠高亮度，灰靠中等亮度。
    """
    h, s, v = _as_hsv(bgr)
    if s < 30:
        if v >= 140:
            return WHITE
        if v >= 35:
            return GRAY
        return None

    best_name = None
    best_distance = 999
    for spec in COLOR_SPECS:
        distance = hue_distance(h, spec.hue)
        if (
            distance <= spec.hue_tol
            and s >= spec.sat_min
            and v >= spec.val_min
            and distance < best_distance
        ):
            best_name = spec.name
            best_distance = distance
    return best_name


def is_gray(bgr) -> bool:
    return classify_bgr(bgr) == GRAY


def is_color(bgr) -> bool:
    return classify_bgr(bgr) in QUALITY_NAMES


def is_near_white(bgr, v_min: int = 190) -> bool:
    """低饱和高亮：用来区分白色品质亮边与灰色轮廓描边。"""
    _h, s, v = _as_hsv(bgr)
    return s < 30 and v >= v_min


__all__ = [
    "PALETTE_VERSION",
    "QUALITY_NAMES",
    "GRAY",
    "WHITE",
    "QualitySpec",
    "COLOR_SPECS",
    "hue_distance",
    "classify_bgr",
    "is_gray",
    "is_color",
    "is_near_white",
]
