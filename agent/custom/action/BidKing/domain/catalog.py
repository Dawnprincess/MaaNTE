# -*- coding: utf-8 -*-
"""拍卖之王 —— 物品表（核心层，零框架依赖）

物品表是候选集查询的权威来源：给定轮廓、品质、类型，筛选可能的物品。
它只回答「可能是哪几件、各值多少钱」，不做任何推断——推断属于估值层。
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "items.csv"
_SHAPE_RE = re.compile(r"(\d+)\s*[×xX]\s*(\d+)")

QUALITIES = ("白", "绿", "蓝", "紫", "金", "红")


@dataclass(frozen=True)
class CatalogItem:
    """物品大全中的一行。"""

    name: str
    shape: tuple[int, int]
    quality: str
    price: int
    type: str
    image: str  # 「图片」列的数字 = 轮廓编号（55 = 5×5）

    @property
    def area(self) -> int:
        return self.shape[0] * self.shape[1]


class Catalog:
    """物品表查询。构造后只读。"""

    def __init__(self, items: Iterable[CatalogItem]) -> None:
        self._items = list(items)
        self._by_shape: dict[tuple[int, int], list[CatalogItem]] = {}
        self._by_shape_quality: dict[tuple[tuple[int, int], str], list[CatalogItem]] = {}
        self._by_type: dict[str, list[CatalogItem]] = {}
        for item in self._items:
            self._by_shape.setdefault(item.shape, []).append(item)
            self._by_shape_quality.setdefault((item.shape, item.quality), []).append(item)
            self._by_type.setdefault(item.type, []).append(item)

    # ---- 构造 ----

    @classmethod
    def load(cls, path: Optional[Path | str] = None) -> "Catalog":
        """从 CSV 加载；默认读包内 data/items.csv（utf-8-sig）。"""
        csv_path = Path(path) if path is not None else _DEFAULT_PATH
        items: list[CatalogItem] = []
        with open(csv_path, encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                parsed = _parse_row(row)
                if parsed is not None:
                    items.append(parsed)
        return cls(items)

    # ---- 查询 ----

    def __len__(self) -> int:
        return len(self._items)

    @property
    def items(self) -> list[CatalogItem]:
        return list(self._items)

    def candidates(
        self,
        shape: Optional[tuple[int, int]] = None,
        quality: Optional[str] = None,
        item_type: Optional[str] = None,
    ) -> list[CatalogItem]:
        """按已知条件筛选候选物品；条件越少候选越多，全空时返回全表。"""
        if shape is not None and quality is not None:
            pool: Iterable[CatalogItem] = self._by_shape_quality.get((shape, quality), [])
        elif shape is not None:
            pool = self._by_shape.get(shape, [])
        elif quality is not None:
            pool = [i for i in self._items if i.quality == quality]
        elif item_type is not None:
            pool = self._by_type.get(item_type, [])
        else:
            pool = self._items

        result = list(pool)
        if item_type is not None:
            result = [i for i in result if i.type == item_type]
        if quality is not None:
            result = [i for i in result if i.quality == quality]
        if shape is not None:
            result = [i for i in result if i.shape == shape]
        return result

    def is_unique(
        self,
        shape: tuple[int, int],
        quality: Optional[str] = None,
        item_type: Optional[str] = None,
    ) -> bool:
        """给定条件是否只剩一件候选。"""
        return len(self.candidates(shape=shape, quality=quality, item_type=item_type)) == 1


def _parse_row(row: dict) -> Optional[CatalogItem]:
    if not row:
        return None
    size = (row.get("尺寸") or "").strip()
    match = _SHAPE_RE.search(size)
    if not match:
        return None
    shape = (int(match.group(1)), int(match.group(2)))
    price_raw = (row.get("价格") or "").replace(",", "").replace("，", "").strip()
    try:
        price = int(float(price_raw))
    except ValueError:
        return None
    name = (row.get("物品名称") or "").strip()
    quality = (row.get("品质") or "").strip()
    item_type = (row.get("种类") or "").strip()
    image = (row.get("图片") or "").strip()
    if not name or not quality:
        return None
    return CatalogItem(
        name=name,
        shape=shape,
        quality=quality,
        price=price,
        type=item_type,
        image=image,
    )
