# -*- coding: utf-8 -*-
"""局内仓库的块级分割与分类（0b1b2）。

核心假设（已用实帧验证）：

- 每件已揭示藏品是一个独立绘制的圆角块，带亮色描边；
- 块与块之间有暗缝；块内部跨格子没有描边；
- 藏品形状是矩形（规则 5.1），所以块的格子 bbox 就是 shape+pos。

因此先按“亮脊/暗谷”把格子图切成块，再在块上分类，最后把状态继承给格子；
不做逐格颜色分类。
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Iterable, Optional

import cv2
import numpy as np

try:  # 实机：custom.action.BidKing.sources.live.perceive.warehouse
    from .....core.geometry import COLS, ROWS, merge_row_ranges
except ImportError:  # 离线：BidKing/ 在 sys.path 上，顶层包导入
    from core.geometry import COLS, ROWS, merge_row_ranges

from .palette import (
    GRAY,
    PALETTE_VERSION,
    QUALITY_NAMES,
    WHITE,
    classify_bgr,
)

PERCEPTION_VERSION = "0b1b2.1"

# 页合并切换行（第 10、18 行）；这些行两侧的接缝单独标记。
PAGE_BOUNDARY_ROWS = tuple(
    start for _page, start, _end in merge_row_ranges() if 0 < start < ROWS
)

# 前景格：房间暗背景 p90 亮度通常 <20；藏品填充/描边明显更高。
FOREGROUND_P90_LUMA = 40.0
FOREGROUND_P99_LUMA = 80.0

# 接缝剖面：沿边两端各让 6px，避开圆角。
EDGE_PAD = 6
EDGE_HALF_WIDTH = 4
EDGE_FILL_BAND = (4, 10)
EDGE_DARK_DROP = 8
EDGE_RIDGE_RISE = 12
EDGE_DARK_MIN = 12.0
EDGE_RIDGE_MIN = 18.0
EDGE_COVERAGE_MIN = 0.60
EDGE_AMBIGUOUS_SCORE = 0.55
EDGE_ALIGN_PX = 3

# 块外沿描边：灰轮廓最暗约 80，彩色/白色更亮。
BORDER_BAND = (1, 4)
BORDER_SIDE_MIN_LUMA = 65.0
BORDER_MIN_SIDES = 3

# 块内图标：实帧样本里平坦块与带图标块分离明显。
# pad=6 可避开 1×1 块的亮边/辉光，避免把灰轮廓误判成有图标。
ICON_PAD = 6
ICON_LOCAL_PAD = 8
ICON_DISTANCE = 40.0
ICON_OUTLIER_MIN = 0.25
ICON_EDGE_MIN = 0.22
ICON_LOCAL_MIN = 0.50
ICON_AMBIGUOUS_SCORE = 0.60

# 白色品质/灰轮廓：不能只看填充亮度，要看亮边。
# 白品质仅品质：亮边约 174、填充约 93；灰轮廓：亮边约 114、填充约 59。
LIGHT_NEUTRAL_BORDER_LUMA = 150.0
LIGHT_NEUTRAL_FILL_LUMA = 80.0

# 流光边缘：已知轮廓+品质的块（含具体物品）有一条高亮流光描边。
# 实测有流光 border max 通道 245..255，无流光 158..184；200 为分界，190..210 为灰区。
GLOW_BORDER_PEAK = 200
GLOW_AMBIGUOUS_LOW = 190
GLOW_AMBIGUOUS_HIGH = 210


@dataclass(frozen=True)
class CellFeature:
    row: int
    col: int
    foreground: bool
    p90_luma: float
    p99_luma: float
    p90_sat: float
    fill_luma: float


@dataclass(frozen=True)
class EdgeScore:
    orientation: str  # "v": (row,col)-(row,col+1); "h": (row,col)-(row+1,col)
    row: int
    col: int
    boundary: bool
    dark_depth: float
    ridge_height: float
    dark_cov: float
    ridge_cov: float
    score: float
    ambiguous: bool
    page_boundary: bool

    def to_dict(self) -> dict:
        return {
            "orientation": self.orientation,
            "row": self.row,
            "col": self.col,
            "boundary": self.boundary,
            "dark_depth": round(self.dark_depth, 2),
            "ridge_height": round(self.ridge_height, 2),
            "dark_cov": round(self.dark_cov, 3),
            "ridge_cov": round(self.ridge_cov, 3),
            "score": round(self.score, 3),
            "ambiguous": self.ambiguous,
            "page_boundary": self.page_boundary,
        }


@dataclass(frozen=True)
class Block:
    block_id: int
    cells: tuple[tuple[int, int], ...]
    bbox: tuple[int, int, int, int]  # r0, c0, r1, c1；闭区间
    state: str  # silhouette / quality_silhouette / item / quality_hint / unknown
    quality: Optional[str]
    fill_bgr: tuple[int, int, int]
    border_bgr: tuple[int, int, int]
    icon_score: float
    confidence: float
    flags: tuple[str, ...]
    features: dict = dc_field(default_factory=dict)

    @property
    def shape(self) -> tuple[int, int]:
        """(列数, 行数)。"""
        r0, c0, r1, c1 = self.bbox
        return c1 - c0 + 1, r1 - r0 + 1

    @property
    def pos(self) -> tuple[int, int]:
        """(列, 行)。"""
        _r0, c0, _r1, _c1 = self.bbox
        return c0, self.bbox[0]

    def to_dict(self) -> dict:
        return {
            "id": self.block_id,
            "bbox": list(self.bbox),
            "shape": list(self.shape),
            "pos": list(self.pos),
            "cells": [list(cell) for cell in self.cells],
            "state": self.state,
            "quality": self.quality,
            "confidence": round(self.confidence, 3),
            "flags": list(self.flags),
            "fill_bgr": list(self.fill_bgr),
            "border_bgr": list(self.border_bgr),
            "icon_score": round(self.icon_score, 3),
            "features": self.features,
        }


@dataclass
class BlockDetection:
    '''
    blocks:识别出的块列表
    cells:10*25的格子状态矩阵
    foreground:10*25的前景格布尔矩阵
    edges:所有相邻前景格的接缝评分
    stats:统计信息
    '''
    blocks: list[Block]
    cells: list[list[str]]
    foreground: list[list[bool]]
    edges: list[EdgeScore]
    stats: dict

    def to_dict(self) -> dict:
        return {
            "perception_version": PERCEPTION_VERSION,
            "palette_version": PALETTE_VERSION,
            "stats": self.stats,
            "blocks": [block.to_dict() for block in self.blocks],
            "cells": self.cells,
            "boundary_edges": [
                edge.to_dict()
                for edge in self.edges
                if edge.boundary or edge.ambiguous
            ],
        }


def _cell_rect(
    row: int, col: int, cell_w: float, cell_h: float
) -> tuple[int, int, int, int]:
    return (
        round(col * cell_w),
        round(row * cell_h),
        round((col + 1) * cell_w),
        round((row + 1) * cell_h),
    )


def _cell_feature(
    gray: np.ndarray,
    hsv: np.ndarray,
    row: int,
    col: int,
    cell_w: float,
    cell_h: float,
) -> CellFeature:
    '''前景格判定'''
    # 计算该方格坐标
    x0, y0, x1, y1 = _cell_rect(row, col, cell_w, cell_h)
    # 去掉外圈2px，避开圆角和块描边
    pad = 2
    x0, y0 = x0 + pad, y0 + pad
    x1, y1 = x1 - pad, y1 - pad
    if x1 <= x0 or y1 <= y0:
        return CellFeature(row, col, False, 0.0, 0.0, 0.0, 0.0)

    patch_gray = gray[y0:y1, x0:x1]
    patch_sat = hsv[y0:y1, x0:x1, 1]
    # 前10%亮度分界线
    p90_luma = float(np.percentile(patch_gray, 90))
    # 前1%亮度分界线
    p99_luma = float(np.percentile(patch_gray, 99))
    p90_sat = float(np.percentile(patch_sat, 90))
    fill_luma = float(np.median(patch_gray))
    # 关键，存在有很亮的部分，就认为该格可能有物品
    foreground = (
        p90_luma >= FOREGROUND_P90_LUMA or p99_luma >= FOREGROUND_P99_LUMA
    )
    return CellFeature(
        row, col, foreground, p90_luma, p99_luma, p90_sat, fill_luma
    )


def _profile_metrics(
    strip: np.ndarray, left_fill: float, right_fill: float
) -> tuple[float, float, float, float, float]:
    """strip: (沿边长度, 9) 的垂直剖面。返回接缝指标。
    输入：9列的窄条亮度矩阵，左填充带亮度，右填充带亮度（中位数）
    输出：(暗缝深度，亮脊高度，暗覆盖率，亮覆盖率，该边的最终得分)
    """
    if strip.size == 0:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    # 对每一列求中位数，得到strip这9列的中位数(axis=0表示沿行方向压缩)
    profile = np.median(strip, axis=0)
    # 对每一行求最暗和最亮的值
    along_min = strip.min(axis=1)
    along_max = strip.max(axis=1)
    # 两侧较暗和较亮的值(用来计算差值)
    fill_min = min(left_fill, right_fill)
    fill_max = max(left_fill, right_fill)

    # 暗缝颜色深度，profile.min为9列中的最小值,可能是暗缝，计算与两侧填充带的差值
    dark_depth = max(0.0, fill_min - float(profile.min()))
    # 计算亮脊高度，profile.max为9列中的最大值，可能是亮脊，计算与两侧填充带的差值
    ridge_height = max(0.0, float(profile.max()) - fill_max)
    # 暗覆盖比例（有多大比例的沿边位置出现这样足够深的暗缝,比例够大认为是真的存在暗缝）
    dark_cov = float(np.mean(along_min < fill_min - EDGE_DARK_DROP))
    ridge_cov = float(np.mean(along_max > fill_max + EDGE_RIDGE_RISE))
    # 计算得分，只要暗沟或亮脊任一特征足够显著且覆盖广，就给出高分
    score = max(
        (ridge_height / EDGE_RIDGE_MIN) * ridge_cov,
        (dark_depth / EDGE_DARK_MIN) * dark_cov,
    )
    return dark_depth, ridge_height, dark_cov, ridge_cov, score


def _score_edge(
    gray: np.ndarray,
    row: int,
    col: int,
    orientation: str,
    cell_w: float,
    cell_h: float,
) -> EdgeScore:
    '''计算两个相邻的前景格接缝得分（是否存在接缝）
    理论：物品接缝处为暗条，而物品边缘存在亮条，因此接缝附件的亮度应该为  左物品亮度-亮边-暗缝-亮边-右物品亮度

    '''
    x0, y0, x1, y1 = _cell_rect(row, col, cell_w, cell_h)
    width, height = gray.shape[1], gray.shape[0]

    # 取接缝附件的亮度值以及左右两侧一条填充带(代表物品亮度)的亮度值
    if orientation == "v":
        # 1.取接缝附件的亮度值
        # 竖边：格子 (row,col) 的右边 == (row,col+1) 的左边
        boundary_pos = x1
        # 沿边缩进6px避开圆角的高度
        lo, hi = y0 + EDGE_PAD, y1 - EDGE_PAD
        if hi - lo < 8:
            lo, hi = y0 + 2, y1 - 2
        # 右侧是一个元组，例如假设boundary_pos为10，edge为2，(8,9,10,11,12)，右侧+1因为切片左闭右开，确保包含到boundary_pos+EDGE这个值
        # 将其中左右边界给xa,xb
        xa, xb = boundary_pos - EDGE_HALF_WIDTH, boundary_pos + EDGE_HALF_WIDTH + 1
        # 边界保护，未防止越界(例如xa可能为负，xb可能超出图像宽度width)
        xa, xb = max(0, xa), min(width, xb)
        #窄条亮度区域，即取lo-hi行，xa-xb列的亮度值（这里一共9列）
        strip = gray[lo:hi, xa:xb]

        #2. 取左右两侧填充带（避开边界）的位置
        left_lo, left_hi = max(0, boundary_pos - EDGE_FILL_BAND[1]), max(
            1, boundary_pos - EDGE_FILL_BAND[0]
        )
        right_lo, right_hi = min(width, boundary_pos + EDGE_FILL_BAND[0]), min(
            width, boundary_pos + EDGE_FILL_BAND[1]
        )
        # 计算填充带亮度值的中位数(避开异常像素对平均值影响)
        left = float(np.median(gray[lo:hi, left_lo:left_hi])) if left_hi > left_lo else 0.0
        right = (
            float(np.median(gray[lo:hi, right_lo:right_hi]))
            if right_hi > right_lo
            else 0.0
        )
        # 页边界格子初始化为false
        page_boundary = False
    else:
        # 横边：格子 (row,col) 的下边 == (row+1,col) 的上边
        boundary_pos = y1
        lo, hi = x0 + EDGE_PAD, x1 - EDGE_PAD
        if hi - lo < 8:
            lo, hi = x0 + 2, x1 - 2
        ya, yb = boundary_pos - EDGE_HALF_WIDTH, boundary_pos + EDGE_HALF_WIDTH + 1
        ya, yb = max(0, ya), min(height, yb)
        strip = gray[ya:yb, lo:hi].T
        top_lo, top_hi = max(0, boundary_pos - EDGE_FILL_BAND[1]), max(
            1, boundary_pos - EDGE_FILL_BAND[0]
        )
        bottom_lo, bottom_hi = min(height, boundary_pos + EDGE_FILL_BAND[0]), min(
            height, boundary_pos + EDGE_FILL_BAND[1]
        )
        left = (
            float(np.median(gray[top_lo:top_hi, lo:hi]))
            if top_hi > top_lo
            else 0.0
        )
        right = (
            float(np.median(gray[bottom_lo:bottom_hi, lo:hi]))
            if bottom_hi > bottom_lo
            else 0.0
        )
        page_boundary = row in tuple(r - 1 for r in PAGE_BOUNDARY_ROWS)

    # 计算该边的各项评价指标
    dark_depth, ridge_height, dark_cov, ridge_cov, score = _profile_metrics(
        strip, left, right
    )
    # 接着拿到指标后来判定是不是真的接缝

    # 计算9列亮度的中位数
    profile = np.median(strip, axis=0) if strip.size else np.zeros(9)
    offset = EDGE_HALF_WIDTH
    # 暗缝亮脊相对格子边界的位置
    # 返回最小值的下标 - 偏移量，即将0 - 8转换为相对中心列的表示-4 - 4
    # 因此表示最亮和最暗的那一列距离中心偏移多少像素
    min_pos = int(np.argmin(profile)) - offset
    max_pos = int(np.argmax(profile)) - offset
    # 如果偏离中心太远，认为是普通纹理（边界不会偏移太远）
    aligned = abs(min_pos) <= EDGE_ALIGN_PX or abs(max_pos) <= EDGE_ALIGN_PX

    # 在局内，块边界的主信号是“亮描边”；纯暗谷可能只是图标边缘。
    # 因此亮脊是主判据；暗谷只在同时有明显的弱亮脊时才作为辅助。
    primary = ridge_height >= EDGE_RIDGE_MIN and ridge_cov >= EDGE_COVERAGE_MIN
    secondary = (
        ridge_height >= 10
        and ridge_cov >= 0.7
        and dark_depth >= 20
        and dark_cov >= 0.7
    )
    # 最终边界判定，没有太偏离中心并且满足上述两个判据之一，认为是边界
    boundary = bool(aligned and (primary or secondary))
    # 针对页边界的情况（拼接的页可能会有暗缝，需要特殊处理，）
    if page_boundary:
        # 拼接缝本身可能是一条暗线；这里只把“弱亮脊”当作灰区。
        ambiguous = bool(not boundary and ridge_height >= 12 and ridge_cov >= 0.5)
    else:
        ambiguous = bool(not boundary and score >= EDGE_AMBIGUOUS_SCORE)
    return EdgeScore(
        orientation=orientation,
        row=row,
        col=col,
        boundary=boundary,
        dark_depth=dark_depth,
        ridge_height=ridge_height,
        dark_cov=dark_cov,
        ridge_cov=ridge_cov,
        score=float(score),
        ambiguous=ambiguous,
        page_boundary=bool(page_boundary),
    )


class _UnionFind:
    '''并查集类，维护一堆不相交的集合
    find(x):找到x所在集合的"代表"
    union(a,b):把a,b所在的两个集合合并成一个
    '''

    # parent是一个字典，键是节点，值是其父节点，根节点的parent指向自己parent[root] == root
    def __init__(self) -> None:
        self.parent: dict[tuple[int, int], tuple[int, int]] = {}

    # 加入新节点，若key不存在，设为default返回；若已经存在，返回原值，不动
    # 新节点node的父节点初始化为自己，自成一个集合
    def add(self, node: tuple[int, int]) -> None:
        self.parent.setdefault(node, node)

    # 找根+路径压缩
    def find(self, node: tuple[int, int]) -> tuple[int, int]:
        root = node
        # 第一趟，从node开始一路向上找到其根
        while self.parent[root] != root:
            root = self.parent[root]
        # 第二趟，路径压缩，将该查找路径上的所有节点的父节点，指向根节点（多层树改为全部挂在根节点下，两层树）
        # 将当前node的父节点改为root，然后调到原来的父节点继续找
        while self.parent[node] != root:
            self.parent[node], node = root, self.parent[node]
        return root

    # 合并两个集合
    # 将右集合的根挂在左集合下面即可
    def union(self, a: tuple[int, int], b: tuple[int, int]) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def _bbox(cells: Iterable[tuple[int, int]]) -> tuple[int, int, int, int]:
    '''返回一个块的左上与右下两个对角点的坐标'''
    rows = [cell[0] for cell in cells]
    cols = [cell[1] for cell in cells]
    return min(rows), min(cols), max(rows), max(cols)


def _fill_holes(
    cells_set: set[tuple[int, int]], bbox: tuple[int, int, int, int]
) -> set[tuple[int, int]]:
    """补上被深色图标遮住的内部格子；只补三面以上被同块包围的洞。"""
    r0, c0, r1, c1 = bbox
    current = set(cells_set)
    changed = True
    while changed:
        changed = False
        for row in range(r0, r1 + 1):
            for col in range(c0, c1 + 1):
                if (row, col) in current:
                    continue
                inside = sum(
                    neighbor in current
                    for neighbor in (
                        (row - 1, col),
                        (row + 1, col),
                        (row, col - 1),
                        (row, col + 1),
                    )
                )
                if inside >= 3:
                    current.add((row, col))
                    changed = True
    return current


def _block_crop(
    canvas: np.ndarray,
    bbox: tuple[int, int, int, int],
    cell_w: float,
    cell_h: float,
) -> np.ndarray:
    r0, c0, r1, c1 = bbox
    x0 = round(c0 * cell_w)
    y0 = round(r0 * cell_h)
    x1 = round((c1 + 1) * cell_w)
    y1 = round((r1 + 1) * cell_h)
    return canvas[y0:y1, x0:x1]


def _bands(crop: np.ndarray) -> dict[str, np.ndarray]:
    '''返回该矩形区域的四条边带'''
    height, width = crop.shape[:2]
    if height < 8 or width < 8:
        return {}
    k0, k1 = BORDER_BAND
    margin = 6
    bands = {
        "top": crop[k0:k1, margin : max(margin, width - margin)],
        "bottom": crop[height - k1 : height - k0, margin : max(margin, width - margin)],
        "left": crop[margin : max(margin, height - margin), k0:k1],
        "right": crop[margin : max(margin, height - margin), width - k1 : width - k0],
    }
    return {name: band for name, band in bands.items() if band.size}


def _band_luma(band: np.ndarray) -> float:
    gray = cv2.cvtColor(band, cv2.COLOR_BGR2GRAY) if band.ndim == 3 else band
    return float(np.percentile(gray, 75))


def _luma(bgr) -> float:
    b, g, r = (float(v) for v in bgr[:3])
    return 0.114 * b + 0.587 * g + 0.299 * r


def _border_color(bands: dict[str, np.ndarray]) -> tuple[int, int, int]:
    pixels = np.concatenate(
        [band.reshape(-1, 3) for band in bands.values()], axis=0
    )
    if pixels.size == 0:
        return (0, 0, 0)
    luma = cv2.cvtColor(pixels.reshape(-1, 1, 3), cv2.COLOR_BGR2GRAY).ravel()
    threshold = float(np.percentile(luma, 75))
    bright = pixels[luma >= threshold]
    if bright.size == 0:
        bright = pixels
    median = np.median(bright, axis=0)
    return tuple(int(round(v)) for v in median)


def _fill_mode(crop: np.ndarray) -> tuple[int, int, int]:
    pad = ICON_PAD
    inner = crop[pad:-pad, pad:-pad] if crop.shape[0] > 2 * pad and crop.shape[1] > 2 * pad else crop
    pixels = inner.reshape(-1, 3)
    if pixels.size == 0:
        return (0, 0, 0)
    quantized = (pixels // 16).astype(np.int32)
    keys = quantized[:, 0] * 4096 + quantized[:, 1] * 64 + quantized[:, 2]
    values, counts = np.unique(keys, return_counts=True)
    dominant = values[int(np.argmax(counts))]
    selected = pixels[keys == dominant]
    median = np.median(selected, axis=0)
    return tuple(int(round(v)) for v in median)


def _icon_features(
    crop: np.ndarray, fill_bgr: tuple[int, int, int]
) -> tuple[float, float, float, float]:
    '''块的图标特征判断
    输入:块像素区域，填充色
    输出:块内像素离散程度（有多少像素偏离填充色），边缘密度（多少边缘像素），局部对比度，综合"像图标"得分
    '''
    pad = ICON_PAD
    inner = crop[pad:-pad, pad:-pad] if crop.shape[0] > 2 * pad and crop.shape[1] > 2 * pad else crop
    if inner.size == 0:
        return 0.0, 0.0, 0.0, 0.0

    lab = cv2.cvtColor(inner, cv2.COLOR_BGR2LAB).astype(np.float32)
    fill_lab = cv2.cvtColor(
        np.uint8([[list(fill_bgr)]]), cv2.COLOR_BGR2LAB
    )[0, 0].astype(np.float32)
    distance = np.linalg.norm(lab - fill_lab, axis=2)
    outlier = float(np.mean(distance > ICON_DISTANCE))

    gray = cv2.cvtColor(inner, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = np.sqrt(gx * gx + gy * gy)
    edge = float(magnitude.mean() / 255.0)

    local_pad = ICON_LOCAL_PAD
    local_inner = (
        crop[local_pad:-local_pad, local_pad:-local_pad]
        if crop.shape[0] > 2 * local_pad and crop.shape[1] > 2 * local_pad
        else inner
    )
    local_gray = cv2.cvtColor(local_inner, cv2.COLOR_BGR2GRAY).astype(np.float32)
    lgx = cv2.Sobel(local_gray, cv2.CV_32F, 1, 0, ksize=3)
    lgy = cv2.Sobel(local_gray, cv2.CV_32F, 0, 1, ksize=3)
    local_magnitude = np.sqrt(lgx * lgx + lgy * lgy)
    if local_magnitude.size:
        kernel = min(9, max(3, (min(local_magnitude.shape[:2]) // 2) * 2 + 1))
        local_mean = cv2.boxFilter(
            local_magnitude, -1, (kernel, kernel), normalize=True
        )
        local = float(local_mean.max() / 255.0)
    else:
        local = 0.0

    score = max(
        outlier / ICON_OUTLIER_MIN,
        edge / ICON_EDGE_MIN,
        local / ICON_LOCAL_MIN,
    )
    return outlier, edge, local, score


def _classify(
    cell_count: int,
    border_name: Optional[str],
    fill_name: Optional[str],
    icon_score: float,
    icon_ambiguous: bool = False,
    light_neutral: bool = False,
    glow: bool = False,
    glow_ambiguous: bool = False,
    border_luma: float = 0.0,
) -> tuple[str, Optional[str], list[str]]:
    '''块分类

    输入: 块格数、边带/填充颜色、图标分数、浅灰中性、流光/流光灰区、边带亮度。
    输出: 块类别（item / silhouette / quality_silhouette / quality_hint / unknown）、
          品质、附加标记。

    视觉语法：
      - 灰色暗块 + 无流光              -> silhouette（只有轮廓）
      - 单格彩色/白 + 无流光           -> quality_hint（只有品质，形状未知）
      - 彩色/白 + 流光                 -> quality_silhouette（轮廓+品质；含 1×1）
      - 有图标 + 流光                  -> item（具体物品）
    '''
    flags: list[str] = []
    icon_present = icon_score >= 1.0
    state = "unknown"
    quality: Optional[str] = None

    def add_flag(name: str) -> None:
        if name not in flags:
            flags.append(name)

    # 白品质：浅灰中性（边≈174/填充≈93），或有图标且边带足够亮（深色图标格）。
    white_quality = light_neutral or (
        border_name == WHITE
        and border_luma >= LIGHT_NEUTRAL_BORDER_LUMA
        and icon_present
    )
    if white_quality:
        quality = WHITE
        if icon_present:
            state = "item"
        elif glow:
            # 1×1 的“轮廓+品质”与多格一样，都是 shape known
            state = "quality_silhouette"
        elif cell_count > 1:
            # 多格彩色/白无流光在视觉语法里不一致，保留形状但标灰区
            state = "quality_silhouette"
            add_flag("ambiguous_glow")
        else:
            state = "quality_hint"
    # 灰色暗块：只有轮廓；无品质
    elif fill_name == GRAY and border_name in (GRAY, WHITE, None):
        state = "silhouette"
    elif icon_present:
        state = "item"
        if border_name in QUALITY_NAMES:
            quality = border_name
        elif fill_name in QUALITY_NAMES:
            quality = fill_name
        elif border_name == WHITE or fill_name == WHITE:
            quality = WHITE
        else:
            add_flag("unknown_color")
    else:
        if border_name in QUALITY_NAMES:
            quality = border_name
        elif fill_name in QUALITY_NAMES:
            quality = fill_name

        if quality is None:
            add_flag("unknown_color")
        elif glow:
            state = "quality_silhouette"
        elif cell_count == 1:
            # 单格无流光 = 仅品质；形状未知，不再默认 ambiguous_1x1
            state = "quality_hint"
        else:
            # 多格无流光不一致；形状仍由块确定
            state = "quality_silhouette"
            add_flag("ambiguous_glow")

    if glow_ambiguous:
        add_flag("ambiguous_glow")
        if cell_count == 1 and not icon_present and state in (
            "quality_hint",
            "quality_silhouette",
        ):
            # 只有流光灰区的 1×1 才保留点击兜底
            add_flag("ambiguous_1x1")
    if icon_ambiguous:
        add_flag("ambiguous_icon")
    return state, quality, flags


def _confidence(
    rectangle: bool,
    side_strength: list[bool],
    border_name: Optional[str],
    fill_name: Optional[str],
    icon_score: float,
    flags: list[str],
) -> float:
    confidence = 0.5
    if rectangle:
        confidence += 0.15
    if any(side_strength):
        confidence += 0.1
    if border_name is not None and border_name == fill_name:
        confidence += 0.1
    if icon_score >= 1.0 or icon_score < ICON_AMBIGUOUS_SCORE:
        confidence += 0.1
    confidence -= 0.15 * min(len(flags), 2)
    return max(0.0, min(1.0, confidence))


def detect_blocks(canvas: np.ndarray) -> BlockDetection:
    """把 10×25 合并画布分成矩形块并分类。

    输出只用于 0b1b2 的 QA；不写 warehouse.jsonl。
    """
    # ---- 0.预处理输入 ----
    # 校验画布-计算方格大小-转换颜色
    if canvas.ndim != 3 or canvas.shape[1] < COLS or canvas.shape[0] < ROWS:
        raise ValueError("canvas 需要是 10×25 的 BGR 画布")
    cell_w = canvas.shape[1] / COLS
    cell_h = cell_w
    # 将彩色图canvas(BGR格式)转换为灰度图(单通道，黑白)
    # gray每个像素是一个0-255的亮度值
    gray = cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY)
    # BGR图转换文HSV颜色空间(Hue色相，Saturation饱和度，Value明度)
    hsv = cv2.cvtColor(canvas, cv2.COLOR_BGR2HSV)

    # ---- 1.前景格判定 ----
    # 先通过每个格子的亮度先筛选出可能是物品的格子
    # 得到foreground布尔矩阵，以供进一步判定块
    foreground = [[False] * COLS for _ in range(ROWS)]
    for row in range(ROWS):
        for col in range(COLS):
            # 逐格进行判定
            feature = _cell_feature(gray, hsv, row, col, cell_w, cell_h)
            foreground[row][col] = feature.foreground

    # ---- 2.前景格接缝打分 ----
    # 得到一个接缝列表edges(包含各接缝的情况信息),以及v_edges和h_edges两个字典，可查询两格之间是否有接缝
    edges: list[EdgeScore] = []
    # 所有相邻前景格的垂直边得分
    v_edges: dict[tuple[int, int], EdgeScore] = {}
    h_edges: dict[tuple[int, int], EdgeScore] = {}
    for row in range(ROWS):
        for col in range(COLS):
            if not foreground[row][col]:
                continue
            # 如果该格是前景格，并且右边也是，则为相邻前景格
            if col + 1 < COLS and foreground[row][col + 1]:
                # 计算接缝得分
                edge = _score_edge(gray, row, col, "v", cell_w, cell_h)
                v_edges[(row, col)] = edge
                edges.append(edge)
            if row + 1 < ROWS and foreground[row + 1][col]:
                edge = _score_edge(gray, row, col, "h", cell_w, cell_h)
                h_edges[(row, col)] = edge
                edges.append(edge)

    # ---- 3.连通分量 ----
    # 得到groups，连通分量，dict类型，键为根节点（块中的某个格），值为该连通分量所有格坐标列表

    # 遍历所有前景格，每个格子作为一个节点加入并查集(初始自成一个集合)
    uf = _UnionFind()
    for row in range(ROWS):
        for col in range(COLS):
            if foreground[row][col]:
                uf.add((row, col))
    
    # 按非边界合并相邻格
    # v_edges和h_edges存放的都是相邻格，只需判断有无边界后直接合并即可
    for (row, col), edge in v_edges.items():
        if not edge.boundary:
            uf.union((row, col), (row, col + 1))
    for (row, col), edge in h_edges.items():
        if not edge.boundary:
            uf.union((row, col), (row + 1, col))
    # 按根分组，遍历并查集里的所有节点，找到根后，将该格的坐标加入该根对应值的列表中
    groups: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for cell in uf.parent:
        groups.setdefault(uf.find(cell), []).append(cell)

    # ---- 4.连通分量的纠错和分类 ----
    # 得到一个块列表，包含块的信息（包括形状，品质等局内性质，也包含置信度等判定信息）
    
    pending: list[dict] = []
    filtered = 0
    filtered_info: list[dict] = []
    # 一次遍历，处理一个块的所有格子
    for cells in groups.values():
        # ---4.1 补洞 ---
        cells_set = set(cells)
        bbox = _bbox(cells_set)
        # 补洞
        cells_set = _fill_holes(cells_set, bbox)
        # 判断是否为矩形
        rectangle = len(cells_set) == (
            (bbox[2] - bbox[0] + 1) * (bbox[3] - bbox[1] + 1)
        )

        # ---4.2 边带提取与描边强度 ---
        # 提取bbox部分的像素区域
        crop = _block_crop(canvas, bbox, cell_w, cell_h)
        bands = _bands(crop)
        # 过滤掉没有边带的块
        if not bands:
            filtered += 1
            filtered_info.append(
                {"bbox": list(bbox), "cells": len(cells_set), "reason": "no_bands"}
            )
            continue
        # 计算边带亮度
        side_luma = [_band_luma(band) for band in bands.values()]
        # 每条边带是否足够亮
        side_strength = [value >= BORDER_SIDE_MIN_LUMA for value in side_luma]

        # --- 4.3过滤与弱边判定 ---
        # 没有亮边的块会被过滤掉（不认为是块），1条以上但不足期望的保留但认定为弱边（weak_border=ture），达到期望条数的保留
        r0, c0, r1, c1 = bbox
        valid_sides = []
        if r0 > 0:
            valid_sides.append("top")
        if r1 < ROWS - 1:
            valid_sides.append("bottom")
        if c0 > 0:
            valid_sides.append("left")
        if c1 < COLS - 1:
            valid_sides.append("right")
        strong_count = sum(side_strength)
        # 至少一条亮边才像真实块；房间暗背景通常四条边都不亮。
        # 页边界/被截断的块可能只剩 1–2 条亮边，保留为 weak_border 而不是丢弃。
        if strong_count < 1:
            filtered += 1
            filtered_info.append(
                {
                    "bbox": list(bbox),
                    "cells": len(cells_set),
                    "reason": "no_border",
                    "side_luma": [round(value, 1) for value in side_luma],
                }
            )
            continue

        # 弱边判定
        expected_sides = min(BORDER_MIN_SIDES, len(valid_sides)) if valid_sides else 1
        weak_border = strong_count < expected_sides

        # --- 4.4 颜色，图标，分类 ---
        # 边框颜色提取
        border_bgr = _border_color(bands)
        # 填充色提取
        fill_bgr = _fill_mode(crop)
        # 边框颜色名
        border_name = classify_bgr(border_bgr)
        # 填充色颜色名
        fill_name = classify_bgr(fill_bgr)
        # 边带/填充亮度与流光特征
        border_luma = _luma(border_bgr)
        fill_luma = _luma(fill_bgr)
        border_peak = max(border_bgr)
        glow = border_peak >= GLOW_BORDER_PEAK
        glow_ambiguous = GLOW_AMBIGUOUS_LOW <= border_peak < GLOW_AMBIGUOUS_HIGH
        neutral = border_name in (GRAY, WHITE, None) and fill_name in (
            GRAY,
            WHITE,
            None,
        )
        light_neutral = (
            neutral
            and border_luma >= LIGHT_NEUTRAL_BORDER_LUMA
            and fill_luma >= LIGHT_NEUTRAL_FILL_LUMA
        )
        # 图标特征（是否是具体物品）
        outlier, edge, local, icon_score = _icon_features(crop, fill_bgr)
        # 灰底块判定（浅灰中性是白品质，不是灰轮廓）
        gray_like = (
            fill_name == GRAY
            and border_name in (GRAY, WHITE, None)
            and not light_neutral
        )
        # 图标判定，条件满足1.图标得分不高但也不低 2.有一个图标特征明显 3.不是灰底块  标记为模糊图标块
        icon_ambiguous = bool(
            ICON_AMBIGUOUS_SCORE <= icon_score < 1.0
            and (outlier >= 0.12 or edge >= 0.15 or local >= 0.40)
            and not gray_like
        )
        # --- 4.5 块分类 ---
        # 得出该块的物品情况（已知轮廓，已知品质，已知品质+轮廓，已知物品
        state, quality, flags = _classify(
            len(cells_set),
            border_name,
            fill_name,
            icon_score,
            icon_ambiguous=icon_ambiguous,
            light_neutral=light_neutral,
            glow=glow,
            glow_ambiguous=glow_ambiguous,
            border_luma=border_luma,
        )

        # --- 4.6 处理不规整、弱边 ---
        if not rectangle:
            flags.append("ambiguous_split")

        # 收集所有弱边，将边的情况收集为("top", "true")类似的形式
        weak = [
            (name, strength)
            for name, strength in zip(bands.keys(), side_strength)
            if not strength
        ]
        # 页边界判定，
        page_side = any(
            (name == "top" and r0 in PAGE_BOUNDARY_ROWS)
            or (name == "bottom" and (r1 + 1) in PAGE_BOUNDARY_ROWS)
            for name, _strength in weak
        )
        # 画布边界判定
        edge_side = any(
            (name == "top" and r0 == 0)
            or (name == "bottom" and r1 == ROWS - 1)
            or (name == "left" and c0 == 0)
            or (name == "right" and c1 == COLS - 1)
            for name, _strength in weak
        )
        # 添加提示
        if page_side:
            flags.append("page_side")
        if edge_side:
            flags.append("partial")
        if weak and not page_side and not edge_side:
            flags.append("open_side")
        if weak_border:
            flags.append("weak_border")
        # 最后，如果弱边且无flags（无原因），则较为可以，将该块降级为unknown
        # 形状/外沿不可靠的块不把假设写进格子状态；保留 quality 供 QA。
        if "ambiguous_split" in flags or "weak_border" in flags:
            state = "unknown"

        # 第 10/18 行是拼接缝；page0/1 没有重叠，块两侧的亮边可能落在
        # 两页视口之外而不可见。跨缝的块不硬拆，但必须显式标记为待复核。
        page_split_rows = [
            row
            for row in PAGE_BOUNDARY_ROWS
            if r0 < row <= r1
            and any(cell[0] < row for cell in cells_set)
            and any(cell[0] >= row for cell in cells_set)
        ]
        if page_split_rows:
            flags.append("ambiguous_page")

        # 该块整体的置信度判定
        confidence = _confidence(
            rectangle,
            side_strength,
            border_name,
            fill_name,
            icon_score,
            flags,
        )
        # 将该块（包含信息）加入到pending列表中
        pending.append(
            {
                "cells": tuple(sorted(cells_set)),
                "bbox": bbox,
                "state": state,
                "quality": quality,
                "fill_bgr": fill_bgr,
                "border_bgr": border_bgr,
                "icon_score": icon_score,
                "confidence": confidence,
                "flags": tuple(flags),
                "features": {
                    "border_name": border_name,
                    "fill_name": fill_name,
                    "border_peak": int(border_peak),
                    "border_luma": round(border_luma, 1),
                    "fill_luma": round(fill_luma, 1),
                    "glow": bool(glow),
                    "glow_ambiguous": bool(glow_ambiguous),
                    "light_neutral": bool(light_neutral),
                    "outlier": round(outlier, 4),
                    "edge": round(edge, 4),
                    "local": round(local, 4),
                    "page_split_rows": page_split_rows,
                },
            }
        )

    # ---- 5.构造block与继承格子状态
    # 得到Block列表（块对象）以及一个cells_matrix[row][col]矩阵，记录每一格的块信息（这个格子什么情况，属于哪个块）

    # 将暂存到普通字典里的块信息排序，实例化为Block对象，填回cells_matrix格子状态矩阵
    # 按每个块的左上角坐标，从左到右，从上到下的顺序排序
    pending.sort(key=lambda item: (item["bbox"][0], item["bbox"][1]))
    blocks: list[Block] = []
    cells_matrix = [["unknown"] * COLS for _ in range(ROWS)]
    for index, item in enumerate(pending, start=1):
        block = Block(
            block_id=index,
            cells=item["cells"],
            bbox=item["bbox"],
            state=item["state"],
            quality=item["quality"],
            fill_bgr=item["fill_bgr"],
            border_bgr=item["border_bgr"],
            icon_score=item["icon_score"],
            confidence=item["confidence"],
            flags=item["flags"],
            features=item["features"],
        )
        blocks.append(block)
        for row, col in block.cells:
            cells_matrix[row][col] = block.state

    # ---- 6.统计输出 ----
    state_counts: dict[str, int] = {}
    quality_counts: dict[str, int] = {}
    flag_counts: dict[str, int] = {}
    covered = 0
    for block in blocks:
        state_counts[block.state] = state_counts.get(block.state, 0) + 1
        if block.quality:
            quality_counts[block.quality] = quality_counts.get(block.quality, 0) + 1
        for flag in block.flags:
            flag_counts[flag] = flag_counts.get(flag, 0) + 1
        covered += len(block.cells)

    unknown_cells = sum(
        1 for row in cells_matrix for state in row if state == "unknown"
    )
    stats = {
        "block_count": len(blocks),
        "state_counts": state_counts,
        "quality_counts": quality_counts,
        "flag_counts": flag_counts,
        "foreground_cells": int(sum(sum(row) for row in foreground)),
        "covered_cells": covered,
        "unknown_cells": unknown_cells,
        "uncovered_cells": ROWS * COLS - covered,
        "filtered_components": filtered,
        "filtered": filtered_info,
    }
    return BlockDetection(
        blocks=blocks,
        cells=cells_matrix,
        foreground=foreground,
        edges=edges,
        stats=stats,
    )


__all__ = [
    "PERCEPTION_VERSION",
    "PAGE_BOUNDARY_ROWS",
    "CellFeature",
    "EdgeScore",
    "Block",
    "BlockDetection",
    "detect_blocks",
]
