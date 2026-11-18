# -*- coding: utf-8 -*-
"""观测来源协议。

实机、回放、模拟器都按这个协议产出同一种逐轮观测流；消费方（估值/出价）
不需要知道数据从哪来。

本模块 MUST NOT import `sources.live`：回放只加载核心与 `sources.replay`，
不应把 Maa / 截图 / OCR 带进离线进程。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, Optional, Protocol

if TYPE_CHECKING:  # 仅用于类型标注，运行时不得导入 core
    from core.contracts import Meta, Observation, Settlement


class ObservationSource(Protocol):
    """一局对局的观测来源。"""

    def meta(self) -> "Meta":
        """本局元数据（场地、角色、仪器、策略等）。"""
        ...

    def iter_rounds(self) -> Iterator["Observation"]:
        """按顺序产出逐轮观测。"""
        ...

    def settlement(self) -> Optional["Settlement"]:
        """结算真值；尚未抓取时返回 None。"""
        ...


__all__ = ["ObservationSource"]
