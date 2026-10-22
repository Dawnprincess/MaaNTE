# -*- coding: utf-8 -*-
"""观测来源协议（核心层）。

实机、回放、模拟器都按这个协议产出同一种逐轮观测流；消费方（估值/出价）
不需要知道数据从哪来。
"""

from __future__ import annotations

from typing import Iterator, Protocol

from ..contracts import Meta, Observation


class ObservationSource(Protocol):
    """一局对局的观测来源。"""

    def meta(self) -> Meta:
        """本局元数据（场地、角色、仪器、策略等）。"""
        ...

    def iter_rounds(self) -> Iterator[Observation]:
        """按顺序产出逐轮观测。"""
        ...


__all__ = ["ObservationSource"]
