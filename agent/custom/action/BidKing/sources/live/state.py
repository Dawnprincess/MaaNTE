# -*- coding: utf-8 -*-
"""
拍卖之王 - 会话级状态（跨节点传递）

流程拆成「观察决策」与「输入」两个自定义动作后，它们之间需要传递：

  observe_round 算出的待输入出价   ->  place_bid 取走
  place_bid 校验成功后记录的本轮出价 ->  下一轮 observe_round 作为 last_bid

用模块级全局变量是项目既有惯例；`bidking_reset` 动作挂在任务入口
（BidKingEntrance），保证两次任务运行之间不串味——否则第二次运行的第一轮
会拿到上一次跑最后一轮的出价当作「上轮出价」。
"""

from dataclasses import dataclass
from typing import Optional

from utils.logger import logger


@dataclass(frozen=True)
class PendingBid:
    """观察窗口得出的、等待输入面板的一笔出价"""

    amount: int
    strategy: str
    reason: str

# 模块级变量，自某个文件调用import state后，就始终存在，直到进程退出销毁
_pending: Optional[PendingBid] = None
_last_bid: Optional[int] = None


def set_pending(bid: PendingBid) -> None:
    global _pending
    _pending = bid


def take_pending() -> Optional[PendingBid]:
    """取出并清空——避免同一笔出价被消费两次"""
    global _pending
    bid, _pending = _pending, None
    return bid


def begin_round() -> None:
    """新一轮开始：丢掉上一轮残留的待输入出价（last_bid 保留，它本就跨轮）"""
    # global用来解决就近原则，防止python认为_pending是一个函数局部变量，而实际上我们需要用的是这个模块级变量
    global _pending
    _pending = None


def set_last_bid(amount: int) -> None:
    """记录本轮已提交的出价；只应在回读校验成功后调用"""
    global _last_bid
    _last_bid = amount
    logger.debug("📝 记录本轮出价 %d 为上轮出价", amount)


def last_bid() -> Optional[int]:
    return _last_bid


def reset() -> None:
    """整局重置（任务入口调用）"""
    global _pending, _last_bid
    _pending = None
    _last_bid = None
