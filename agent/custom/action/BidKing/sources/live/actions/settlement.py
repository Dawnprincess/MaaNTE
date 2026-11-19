# -*- coding: utf-8 -*-
"""拍卖之王 - 结算包裹三页采集。

结算画面在 `BidKingSkip` 点击跳过动画后出现；本动作只负责：
  等结算区域稳定 → 滑条回顶 → 截三页 → 写入当前 session。
不点击退出，退出由 Pipeline 的 `BidKingExit` 负责。

采集失败只写日志并正常返回，保证 88 秒倒计时内仍能退出。
"""

import traceback

from maa.agent.agent_server import AgentServer
from maa.context import Context
from maa.custom_action import CustomAction

from utils.logger import logger

from ..capture import recorder, timing
from ..capture.scrollbar import capture_live_pages
from ..layout import (
    SETTLEMENT_SCROLLBAR_TRACK,
    SETTLEMENT_THUMB_TOP,
    SETTLEMENT_VIEW,
)

# 结算画面稳定的判定参数
SETTLE_TIME = 0.3
SETTLE_TIMEOUT = 2.0


@AgentServer.custom_action("capture_settlement")
class CaptureSettlement(CustomAction):
    """跳过结算动画后截取三页完整包裹，然后交回 Pipeline 退出。"""

    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        try:
            self._capture(context)
        except Exception as exc:
            logger.error("❌ 结算采集异常（不影响退出）: %s", exc)
            logger.error("%s", traceback.format_exc())
        return CustomAction.RunResult(success=True)

    @staticmethod
    def _capture(context: Context) -> None:
        session_dir = recorder.session_dir()
        if session_dir is None:
            logger.warning("⚠️ 没有活动会话，跳过结算采集")
            return

        controller = context.tasker.controller
        timing.wait_until_stable(
            controller,
            SETTLEMENT_VIEW,
            SETTLE_TIME,
            SETTLE_TIMEOUT,
            interval=0.1,
            should_stop=lambda: bool(context.tasker.stopping),
        )

        pages = capture_live_pages(
            controller,
            SETTLEMENT_SCROLLBAR_TRACK,
            SETTLEMENT_THUMB_TOP[3],
            should_stop=lambda: bool(context.tasker.stopping),
        )
        saved = sum(1 for page in pages if page is not None)
        if saved == 0:
            logger.warning("⚠️ 结算采集无可用帧，继续退出")
            return

        recorder.record("settlement", pages, {"kind": "settlement"})
        logger.info("📸 结算包裹已采集 %d 页", saved)


__all__ = ["CaptureSettlement"]
