# -*- coding: utf-8 -*-
"""
拍卖之王 - 对局快照

这是**策略的输入契约**：所有策略都依赖它。因此往这里加字段要过一遍
「策略真的要用吗」——感知层内部可以躺着没人用的 `read_xxx()`，但快照上
多一个字段就是多一份要维护的契约。见 openspec design D5。

字段来源分两类，不要混淆：

  帧解析（来自采集到的画面）  round / valuation / balance / countdown
  自身记录（我做的，我知道）  last_bid

`last_bid` 不来自帧，因此**不参与「可对历史帧重复执行」**——它由出价入口在
回读校验成功后写入会话状态，感知层组装快照时并入。
"""

from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class RoundSnapshot:
    """一轮对局的已知状态；读不到的字段一律为 None，绝不填猜测值"""

    # ---- 帧解析 ----
    round: Optional[int] = None          # 当前回合数（「竞拍第x回合」）
    valuation: Optional[int] = None      # 系统估价（顶栏）
    balance: Optional[int] = None        # 自身资产（顶栏）
    countdown: Optional[int] = None      # 本轮剩余秒数

    # ---- 自身记录 ----
    last_bid: Optional[int] = None       # 上轮自己提交并校验成功的出价额

    def to_dict(self) -> dict:
        """用于写入采集会话，供事后复盘定位「这一轮看到了什么、据此出了多少」"""
        return asdict(self)
