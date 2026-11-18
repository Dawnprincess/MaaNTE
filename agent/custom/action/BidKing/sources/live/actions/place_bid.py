# -*- coding: utf-8 -*-
"""
拍卖之王 - 输入步骤

职责边界（改造后大幅收窄）：
  - 本动作：取出观察窗口**已经决定**的出价额 → 清空输入框 → 逐位点数字 → 回读校验
  - 决策在 observe_round（面板**尚未打开**时，画面无遮挡）
  - 点「确认出价」在 Pipeline 的 BidKingConfirmBid 节点
  - 策略只负责算出这个数，见 core/policy/

为什么决策不在这里：出价面板一打开，中部的信息披露区域与右侧仓库就被挡住了。
把「观察和思考」放进面板里，等于每轮都主动把视野缩到最小。所以流程是
「先观察决策、再点开面板」，本动作只做纯机械的输入。

Pipeline 参数（custom_action_param）：
  - debug: 是否打印 OCR 调试信息

屏幕坐标一律来自 .layout，不通过参数传入，避免被前端覆盖时丢失。
假设分辨率：1280×720，坐标直接用
"""

import time
from typing import Optional

from maa.agent.agent_server import AgentServer
from maa.context import Context
from maa.custom_action import CustomAction

from .....Common.utils import click_rect, load_params
from utils.maafocus import PrintT
from utils.logger import logger

from ....core.policy import DEFAULT_STRATEGY
from ....core.util import extract_price
from .. import state
from ..layout import CLEAR_BTN, DIGIT_BUTTONS, INPUT_ROI
from ..state import PendingBid
from ..utils import read_region_text

# 观察窗口没给出金额时（不应发生）的兜底：仍出一笔，不放弃本轮
FALLBACK_AMOUNT = 1


# ============ 公共输入层 ============


def clear_and_type(controller, clear_btn, target: int) -> None:
    """清空输入框后逐位点击数字按钮"""
    click_rect(controller, clear_btn, delay=0.2)

    digits = [int(d) for d in str(target)]
    logger.info("⌨️ 输入数字序列: %s", digits)
    for index, digit in enumerate(digits):
        btn = DIGIT_BUTTONS.get(str(digit))
        if btn is None:
            raise RuntimeError(f"未找到数字 {digit} 的按钮坐标")
        logger.info("  [%d/%d] 点击 %d", index + 1, len(digits), digit)
        click_rect(controller, btn, delay=0.15)


def verify_readback(
    context: Context,
    controller,
    input_roi,
    clear_btn,
    target: int,
    debug: bool,
    retried: bool = False,
) -> Optional[bool]:
    """
    回读输入框并校验；不一致时清空重输一次。

    失败策略（与改造前一致）：
    - 完全读不到 → 不重输（大概率是 OCR 的问题，不是点错）
    - 不一致     → 重输一次；再不一致则停止重试，交由 Pipeline 自愈
    """
    time.sleep(0.2)  # 等最后一位数字上屏
    text = read_region_text(context, controller, input_roi, debug)
    actual = extract_price(text)

    if actual is None:
        logger.warning("⚠️ 回读读不到数字，按已输入内容继续")
        PrintT(context, "bidking.readback_unreadable")
        return None

    if actual == target:
        return True

    logger.warning("⚠️ 回读不一致: 目标 %d, 实际 %d", target, actual)
    PrintT(context, "bidking.readback_mismatch", target, actual)

    if retried:
        logger.warning("⚠️ 已重输过一次，不再重试")
        return False

    clear_and_type(controller, clear_btn, target)
    return verify_readback(
        context, controller, input_roi, clear_btn, target, debug, retried=True
    )


# ============ 自定义动作 ============


@AgentServer.custom_action("place_bid")
class PlaceBid(CustomAction):
    """把观察窗口已决定的出价额打进输入框；确认出价由 Pipeline 点击"""

    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        try:
            param = load_params(getattr(argv, "custom_action_param", None))
            debug = bool(param.get("debug", False))
            controller = context.tasker.controller

            # ---------- 1. 取出观察窗口决定的出价额 ----------
            bid = state.take_pending()
            if bid is None or bid.amount <= 0:
                logger.error("❌ 没有待输入的出价额（观察窗口未产出？），兜底出 %d", FALLBACK_AMOUNT)
                PrintT(context, "bidking.no_pending", FALLBACK_AMOUNT)
                bid = PendingBid(FALLBACK_AMOUNT, DEFAULT_STRATEGY, "no_pending")

            # ---------- 2. 输入 ----------
            clear_and_type(controller, CLEAR_BTN, bid.amount)

            # ---------- 3. 回读校验 ----------
            consistent = verify_readback(
                context, controller, INPUT_ROI, CLEAR_BTN, bid.amount, debug
            )
            if consistent is False:
                logger.warning("⚠️ 回读不一致且重试无效，本次输入作废，交由 Pipeline 自愈")
                PrintT(context, "bidking.readback_mismatch_give_up", bid.amount)
                # 这是输入失败（画面与预期不符），不是策略放弃——面板会被自愈机制收起，
                # 下一拍重新识别到出价按钮后，观察窗口会重新走一遍
                return CustomAction.RunResult(success=False)

            # ---------- 4. 只有校验通过才记为「上轮出价」 ----------
            state.set_last_bid(bid.amount)
            PrintT(context, "bidking.bid_done", bid.strategy, bid.amount)
            return CustomAction.RunResult(success=True)

        except Exception as exc:
            logger.error("❌ PlaceBid 异常: %s", exc)
            import traceback

            logger.error("%s", traceback.format_exc())
            PrintT(context, "bidking.failed", str(exc))
            return CustomAction.RunResult(success=False)
