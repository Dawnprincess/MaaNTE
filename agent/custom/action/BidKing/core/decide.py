# -*- coding: utf-8 -*-
"""决策运行器（核心层）：策略选择 + 兜底。

实机与回放都调用这里，保证同一条观测得到同一个出价，
包括「未知策略、策略异常、金额非法」这些兜底路径。
"""

from __future__ import annotations

import logging
from typing import Optional

from .contracts import DecisionContext, Observation
from .policy import DEFAULT_STRATEGY, BidDecision, Strategy, get_strategy

logger = logging.getLogger(__name__)

# 任何一步出问题时使用的兜底出价；放弃本轮的代价高于出一个最低价
FALLBACK_AMOUNT = 1

# 兜底分支的 reason，与 policy.REASON_MESSAGES 对应（这里不登记文案，
# 由编排层决定是否需要提示）
REASON_ERROR = "observe_error"


def resolve(name: Optional[str]) -> tuple[Strategy, str, bool]:
    """返回 (策略实现, 实际策略名, 是否发生回落)。"""
    requested = str(name or DEFAULT_STRATEGY)
    strategy, fell_back = get_strategy(requested)
    return strategy, (DEFAULT_STRATEGY if fell_back else requested), fell_back


def decide(
    context: Observation | DecisionContext,
    strategy_name: Optional[str] = None,
    strategy_param: Optional[dict] = None,
) -> BidDecision:
    """给定观测/决策上下文与策略，返回一次出价决策。

    兼容旧调用：只传 Observation 时自动包成 DecisionContext（warehouse=None），
    回放与旧测试无需改动；实机观察窗口传带 warehouse 的 DecisionContext。
    绝不抛异常、绝不返回非法金额。
    """
    if not isinstance(context, DecisionContext):
        context = DecisionContext(observation=context)
    strategy, effective_name, _ = resolve(strategy_name)
    params = strategy_param if isinstance(strategy_param, dict) else {}

    try:
        decision = strategy(context, params)
    except Exception as exc:  # noqa: BLE001 - 策略异常不得中断出价
        logger.error("❌ 策略 %s 计算异常，兜底出 %d: %s", effective_name, FALLBACK_AMOUNT, exc)
        return BidDecision(FALLBACK_AMOUNT, REASON_ERROR)

    if not isinstance(decision, BidDecision) or decision.amount <= 0:
        logger.error(
            "❌ 策略 %s 返回了无效结果（%r），兜底出 %d",
            effective_name,
            decision,
            FALLBACK_AMOUNT,
        )
        return BidDecision(FALLBACK_AMOUNT, REASON_ERROR)

    return decision
