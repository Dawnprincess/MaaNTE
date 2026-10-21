"""
固定价格策略

每轮都出用户配置的固定金额；默认 1，即改造前"每轮出价 1"的行为。
不看快照——固定价格不需要任何对局信息，这也让它成为"策略可以完全不读画面"
的最小样例。

参数（strategy_param）：
  - price: 正整数，缺省 1；非法值回落默认值并写日志
"""

from utils.logger import logger

from ..perceive import RoundSnapshot
from ..utils import to_positive_int
from . import BidDecision, register

DEFAULT_PRICE = 1


@register("fixed")
def decide(snapshot: RoundSnapshot, params: dict) -> BidDecision:
    raw = params.get("price", DEFAULT_PRICE)
    price = to_positive_int(raw)
    if price is None:
        logger.warning("⚠️ 固定价格参数无效（%r），回落到默认值 %d", raw, DEFAULT_PRICE)
        return BidDecision(DEFAULT_PRICE, "fixed_default")
    return BidDecision(price, "fixed")
