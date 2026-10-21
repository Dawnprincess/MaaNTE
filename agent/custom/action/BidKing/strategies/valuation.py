"""
保底出价策略

每轮按系统根据当轮情报披露算出的最低估价出价。估价由感知层从采集到的画面读出，
本策略只消费快照——不截图、不 OCR、不等待。「等信息到位」是采集层的采集时机
决策（见 ..capture.timing 与 design D12）。

兜底阶梯（与 bidking-bidding 能力契约一致）：
  - 估价读到     → 直接采用
  - 估价为 0     → 出 1（画面已稳定后仍为 0，说明本轮确实没有估值）
  - 估价读不到   → 沿用自身记录的上轮出价
  - 上轮记录也无 → 出 1

**不再依赖面板内的「上轮出价」按钮**：观察与决策发生在出价面板关闭时，该按钮
并不存在；而且自己输入并回读校验过的值本就不需要回屏幕再读一遍。天黑场（只公布
排名，不公布具体出价）因此也不受影响。

本策略目前不读 strategy_param（形参保留以符合策略接口）。
"""

from utils.logger import logger

from ..perceive import RoundSnapshot
from . import BidDecision, register

# 估价与上轮记录都不可用时的最小出价（保证仍能参与后续轮次）
FALLBACK_PRICE = 1


@register("valuation")
def decide(snapshot: RoundSnapshot, params: dict) -> BidDecision:
    price = snapshot.valuation

    if price is None:
        logger.warning(
            "⚠️ 估价不可读（快照: round=%s balance=%s countdown=%s），走兜底",
            snapshot.round,
            snapshot.balance,
            snapshot.countdown,
        )
        if snapshot.last_bid:
            return BidDecision(snapshot.last_bid, "valuation_last_bid")
        return BidDecision(FALLBACK_PRICE, "valuation_fallback_one")

    if price <= 0:
        return BidDecision(FALLBACK_PRICE, "valuation_zero")

    return BidDecision(price, "valuation")
