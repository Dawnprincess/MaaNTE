# -*- coding: utf-8 -*-
"""出价策略注册表（核心层）

策略约定：decide(observation, params) -> BidDecision
  - observation: 一回合的观测（含界面读数与揭示）
  - params:      该策略自己的参数，不要读别的策略的键

策略的三条边界：
  - 不接触 controller：不截图、不点击、不做任何交互
  - 不持有时间：没有等待、超时处理
  - 不认识 i18n 键名：只吐 reason，文案由编排者映射

命名说明：
  - `fixed_price`：固定出价。
  - `lower_bound`：按系统保底估价出价（旧名 `valuation`）。
  - `valuation`：仅为兼容已保存任务配置而保留的同义别名；Phase 1 引入
    真正的估值器后会统一改名并移除别名。
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

# reason -> 面向用户的提示键；None 表示该分支无需额外提示。
# `lower_bound_*` 暂时复用现有 `bidking.valuation_*` 文案键；Phase 1 统一改名。
REASON_MESSAGES: dict[str, Optional[str]] = {
    "fixed": None,
    "lower_bound": None,
    "fixed_default": "bidking.fixed_default",
    "lower_bound_zero": "bidking.valuation_zero",
    "lower_bound_last_bid": "bidking.fallback_last_bid",
    "lower_bound_fallback_one": "bidking.fallback_one",
    # 兼容旧会话中记录的 reason
    "valuation": None,
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
from . import fixed_price, lower_bound  # noqa: E402,F401

# 兼容别名：已保存的任务配置可能仍写着 `valuation`
STRATEGIES.setdefault("valuation", STRATEGIES["lower_bound"])

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
    "lower_bound",
]
