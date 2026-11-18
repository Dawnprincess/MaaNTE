# -*- coding: utf-8 -*-
"""拍卖之王 - 任务入口的整局重置。"""

from maa.agent.agent_server import AgentServer
from maa.context import Context
from maa.custom_action import CustomAction

from utils.logger import logger

from .. import state
from ..capture import recorder


@AgentServer.custom_action("bidking_reset")
class BidKingReset(CustomAction):
    """清掉上一次运行的残留状态与采集会话"""

    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        state.reset()
        recorder.reset()
        logger.debug("♻️ 拍卖之王会话状态已重置")
        return CustomAction.RunResult(success=True)
