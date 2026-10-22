# -*- coding: utf-8 -*-
"""出价策略注册表（核心层）

与旧 `BidKing/strategies/` 的约定一致，只是把输入类型换成了 `Observation`，
并去掉了对 agent 运行时（`utils.logger`、`perceive`）的依赖，便于回放。

策略约定：decide(observation, params) -> BidDecision
  - observation: 一回合的观测（含界面读数与揭示）
  - params:      该策略自己的参数，不要读别的策略的键

策略的三条边界：
  - 不接触 controller：不截图、不点击、不做任何交互
  - 不持有时间：没有等待、超时处理
  - 不认识 i18n 键名：只吐 reason，文案由编排者映射
"""

from dataclasses import dataclass
from typing import Callable, Optional

from ..contracts import Observation


@dataclass(frozen=True)
class BidDecision:
    """一次出价决策的结果：金额恒为正整数，reason 标识分支。"""

    amount: int
    reason: str


Strategy = Callable[[Observation, dict], BidDecision]

# 注册表，键是策略名称，值是对应的策略函数
STRATEGIES: dict[str, Strategy] = {}

# 默认策略：每轮固定出价 1
DEFAULT_STRATEGY = "fixed"

# reason -> 面向用户的提示键；None 表示该分支无需额外提示
REASON_MESSAGES: dict[str, Optional[str]] = {
    "fixed": None,
    "valuation": None,
    "fixed_default": "bidking.fixed_default",
    "valuation_zero": "bidking.valuation_zero",
    "valuation_last_bid": "bidking.fallback_last_bid",
    "valuation_fallback_one": "bidking.fallback_one",
}


def register(name: str) -> Callable[[Strategy], Strategy]:
    """把一个策略实现注册到指定名字下。"""

    def decorator(fn: Strategy) -> Strategy:
        STRATEGIES[name] = fn
        return fn

    return decorator


def get_strategy(name: str) -> tuple[Strategy, bool]:
    """返回 (策略实现, 是否发生了回落)；名字未知时回落到默认策略。"""
    fn = STRATEGIES.get(name)
    if fn is not None:
        return fn, False
    return STRATEGIES[DEFAULT_STRATEGY], True


def message_for(reason: str) -> Optional[str]:
    """reason 对应的用户提示键；无需提示或 reason 未知时返回 None。"""
    return REASON_MESSAGES.get(reason)


def is_known_reason(reason: str) -> bool:
    return reason in REASON_MESSAGES


def available() -> list[str]:
    """已注册的策略名（用于日志与排错）。"""
    return sorted(STRATEGIES)


# 导入即注册，必须放在 register 定义之后
from . import fixed_price, valuation  # noqa: E402,F401

__all__ = [
    "BidDecision",
    "Strategy",
    "STRATEGIES",
    "DEFAULT_STRATEGY",
    "REASON_MESSAGES",
    "register",
    "get_strategy",
    "message_for",
    "is_known_reason",
    "available",
    "fixed_price",
    "valuation",
]
