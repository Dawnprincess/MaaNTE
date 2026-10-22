# -*- coding: utf-8 -*-
"""模拟器来源（占位）。

Phase 3 会实现：按学到的生成分布造包裹、按对手模型造出价、按成交规则结算，
并以与实机相同的 `Observation` 结构产出。0a 只保留协议占位，避免回放与
实机路径误引用。

注意：模拟器不是「回放」——它生成新对局；回放只是重读已保存的对局。
"""

from __future__ import annotations

from typing import Iterator

from ..contracts import Meta, Observation


class SimSource:
    """尚未实现；Phase 3 提供真实实现。"""

    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError("模拟器来源将在 Phase 3 实现")

    def meta(self) -> Meta:  # pragma: no cover - 占位
        raise NotImplementedError

    def iter_rounds(self) -> Iterator[Observation]:  # pragma: no cover - 占位
        raise NotImplementedError
