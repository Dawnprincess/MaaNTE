# -*- coding: utf-8 -*-
"""
出价策略注册表

新增一种策略只要两步：
  1. 在本目录新建一个模块，用 @register("策略名") 装饰一个 decide 函数
  2. 在文件末尾 import 一次（导入即注册），再到前端任务选项里加一个 case

策略约定：decide(snapshot, params) -> BidDecision
  - snapshot: 感知层产出的对局快照（RoundSnapshot），见 ..perceive
  - params:   该策略自己的参数（前端 strategy_param），不要读别的策略的键
  - 返回 BidDecision(amount, reason)

策略的三条边界（都写在能力契约里）：
  - **不接触 controller**：不截图、不点击、不做任何交互。需要新数据时，正确做法
    是加 snapshot 字段（即感知层的工作），而不是把 controller 要回去
  - **不持有时间**：没有时间预算、没有等待、没有超时处理。「等信息出现」是采集
    时机决策，归采集层（见 capture/timing）
  - **不认识 i18n 键名**：只吐 reason，用户可见文案由编排者按下面的映射表发送

于是策略是一次同步的纯计算：给定同一份快照，结果确定且可离线重放。
"""

from dataclasses import dataclass
from typing import Callable, Optional

from ..perceive import RoundSnapshot


@dataclass(frozen=True)
class BidDecision:
    """
    一次出价决策的结果。

    - `amount` 恒为正整数：策略永不放弃本轮（出 1 严格优于放弃——几乎无代价，
      且保住第 6 轮继续资格，而放弃意味着出价 0 且失去资格）
    - `reason` 标识走的是哪条分支，用于事后复盘与用户提示
    """

    amount: int
    reason: str


# 接收 (快照, 该策略自己的参数)，返回决策
# Callable结构类型，即只要满足传入参数是[RoundSnapshot, dict]，返回BidDecision，都认为是Strategy对象
# 可以是对象，函数，lambda表达式等，这里我们用的函数
Strategy = Callable[[RoundSnapshot, dict], BidDecision]

# 注册表，键是策略名称，值是对应的策略函数
STRATEGIES: dict[str, Strategy] = {}

# 默认策略：等价于改造前"每轮固定出价 1"的行为
DEFAULT_STRATEGY = "fixed"

# reason -> 面向用户的提示键；None 表示该分支无需额外提示。
#
# 集中在这里而不是散落进各策略，是因为这些是**需要对账的产品文案**（五个语言文件、
# 占位符个数），放在一处才好维护；策略本身则只吐数据、不认识 i18n 键名。
# 需要携带出价额的项统一把 `amount` 作为唯一参数。
REASON_MESSAGES: dict[str, Optional[str]] = {
    # 正常路径
    "fixed": None,
    "valuation": None,
    # 兜底分支
    "fixed_default": "bidking.fixed_default",
    "valuation_zero": "bidking.valuation_zero",
    "valuation_last_bid": "bidking.fallback_last_bid",
    "valuation_fallback_one": "bidking.fallback_one",
}


# 在要注册的策略函数顶部调用@register("fixed")
# 相当于decide = register("fixed")(decide)
# 先调用外层register("fixed")，返回decorator函数
# 再调用内层 关键执行STARTEGIES[fixed] = decide,注册到STARTEGIES，然后结果赋回decide
# 实际上在函数decide定义完就会调用运行register(而不是等到运行)
def register(name: str) -> Callable[[Strategy], Strategy]:
    """把一个策略实现注册到指定名字下"""

    def decorator(fn: Strategy) -> Strategy:
        STRATEGIES[name] = fn
        return fn

    return decorator

# 获取策略名称，返回对应的函数对象（python中函数也可以作为对象）
def get_strategy(name: str) -> tuple[Strategy, bool]:
    """返回 (策略实现, 是否发生了回落)；名字未知时回落到默认策略"""
    fn = STRATEGIES.get(name)
    if fn is not None:
        return fn, False
    return STRATEGIES[DEFAULT_STRATEGY], True


def message_for(reason: str) -> Optional[str]:
    """
    reason 对应的用户提示键；无需提示或 reason 未知时返回 None。

    reason 未知是**新策略忘了登记**的信号，不静默——由调用方记日志。
    """
    return REASON_MESSAGES.get(reason)


def is_known_reason(reason: str) -> bool:
    return reason in REASON_MESSAGES


def available() -> list[str]:
    """已注册的策略名（用于日志与排错）"""
    return sorted(STRATEGIES)


# 导入即注册，必须放在 register 定义之后
# 进入具体的策略文件fixed_price,valuation等，执行其中的顶层代码（含import,@register）
from . import fixed_price, valuation  # noqa: E402,F401
