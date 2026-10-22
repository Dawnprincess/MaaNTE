# -*- coding: utf-8 -*-
"""保底出价策略：每轮按系统估价出价。

兜底阶梯（与 bidking-bidding 能力契约一致）：
  - 估价读到     → 直接采用
  - 估价为 0     → 出 1
  - 估价读不到   → 沿用自身记录的上轮出价
  - 上轮记录也无 → 出 1

只消费 `Observation`：不截图、不 OCR、不等待。
"""

import logging

from ..contracts import Observation
from . import BidDecision, register

logger = logging.getLogger(__name__)

# 估价与上轮记录都不可用时的最小出价（保证仍能参与后续轮次）
FALLBACK_PRICE = 1


@register("valuation")
def decide(observation: Observation, params: dict) -> BidDecision:
    price = observation.valuation

    if price is None:
        logger.warning(
            "⚠️ 估价不可读（round=%s balance=%s countdown=%s），走兜底",
            observation.round,
            observation.balance,
            observation.countdown,
        )
        if observation.last_bid:
            return BidDecision(observation.last_bid, "valuation_last_bid")
        return BidDecision(FALLBACK_PRICE, "valuation_fallback_one")

    if price <= 0:
        return BidDecision(FALLBACK_PRICE, "valuation_zero")

    return BidDecision(price, "valuation")
