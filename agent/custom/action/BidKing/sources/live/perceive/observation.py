# -*- coding: utf-8 -*-
"""实时感知：把一帧界面读数组成 Observation。

字段提取的纯函数在 `fields.py`；本模块只做编排与异常隔离。
任一字段失败只让该字段为 None，不影响其余字段，也不中断出价。

观察窗口的顺序是：capture -> warehouse/round.perceive_round -> 本模块的
`perceive` -> core.decide；本模块只负责界面层观测，不负责仓库块判定。
"""

from __future__ import annotations

from typing import Optional

from maa.context import Context

from utils.logger import logger

from ....core.contracts import Observation
from ....core.util import parse_countdown, parse_round

from .fields import (
    read_balance,
    read_countdown,
    read_round,
    read_valuation,
)


def perceive(context: Context, frame) -> Observation:
    """从一帧画面提取本轮观测。

    任一字段提取失败（读不到或抛异常）都只让该字段为 `None`；使用方据此走
    各自兜底，而不是拿到一个猜测值。
    """
    return Observation(
        round=_safe(read_round, context, frame, "round"),
        valuation=_safe(read_valuation, context, frame, "valuation"),
        balance=_safe(read_balance, context, frame, "balance"),
        countdown=_safe(read_countdown, context, frame, "countdown"),
    )


def _safe(reader, context: Context, frame, name: str) -> Optional[int]:
    try:
        return reader(context, frame)
    except Exception as exc:  # noqa: BLE001 - 提取异常不得中断出价
        logger.warning("⚠️ 字段 %s 提取异常，按「不可读」处理: %s", name, exc)
        return None


__all__ = [
    "Observation",
    "perceive",
    "read_round",
    "read_countdown",
    "read_balance",
    "read_valuation",
    "parse_round",
    "parse_countdown",
]
