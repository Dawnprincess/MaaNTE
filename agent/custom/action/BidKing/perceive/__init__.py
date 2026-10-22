# -*- coding: utf-8 -*-
"""
拍卖之王 - 感知层

把已保存的帧解释为结构化快照。它不是「采集的一部分」，而是「把采下来的东西
看懂」：采集层只管存，语义在这里才出现。

对历史帧重复执行：`perceive()` 不截图、不点击、不读任务状态，因此提取逻辑
（识别区域、解析规则）变更后，拿旧录像重放即可验证，不必重打对局。
"""

from typing import Optional

from maa.context import Context

from utils.logger import logger

from .fields import (
    parse_countdown,
    parse_round,
    read_balance,
    read_countdown,
    read_round,
    read_valuation,
)
from ..domain.contracts import Observation
from .snapshot import RoundSnapshot

__all__ = [
    "Observation",
    "RoundSnapshot",
    "perceive",
    "read_round",
    "read_countdown",
    "read_balance",
    "read_valuation",
    "parse_round",
    "parse_countdown",
]


def perceive(context: Context, frame) -> Observation:
    """
    从一帧画面提取本轮观测。

    任一字段提取失败（读不到或抛异常）都只让该字段为 `None`，不影响其余字段——
    使用方据此走各自兜底，而不是拿到一个猜测值。

    0a 阶段只填旧的五个字段；揭示事件（public/private）留给下一变更。
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
