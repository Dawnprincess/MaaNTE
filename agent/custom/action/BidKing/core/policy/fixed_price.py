# -*- coding: utf-8 -*-
"""固定价格策略：每轮出用户配置的固定金额；默认 1。

参数（strategy_param）：
  - price: 正整数，缺省 1；非法值回落默认值并写日志
"""

import logging

from ..contracts import DecisionContext
from ..util import to_positive_int
from . import BidDecision, register

logger = logging.getLogger(__name__)

DEFAULT_PRICE = 1


@register("fixed")
def decide(context: DecisionContext, params: dict) -> BidDecision:
    raw = params.get("price", DEFAULT_PRICE)
    price = to_positive_int(raw)
    if price is None:
        logger.warning("⚠️ 固定价格参数无效（%r），回落到默认值 %d", raw, DEFAULT_PRICE)
        return BidDecision(DEFAULT_PRICE, "fixed_default")
    return BidDecision(price, "fixed")
