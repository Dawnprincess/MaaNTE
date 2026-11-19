# -*- coding: utf-8 -*-
"""
拍卖之王 - 观察窗口（采集 → 感知 → 决策）

这是流程顺序改造的落点：**先观察、后点击出价**。出价按钮在每回合开始时即存在，
不必等别人，也不必等披露动画播完，因此观察窗口从回合一开始就能开启，策略拥有
整段回合时间，而不是面板打开后的那几秒。

本动作只做编排，逐层往下调，自己不判断画面里是什么：

    capture/timing    等到本轮信息到位（有上限，超时就按当前画面继续）
    capture/recorder  采集：把这一刻的画面固定下来（不可逆的一步）
    perceive          感知：把帧解释成 Observation
    core.decide       决策：一次同步的纯计算，不给策略设时限

算出的金额写进会话状态，由 `BidKingInputAmount` 节点里的 place_bid 取走输入；
「确认出价」仍由 Pipeline 的 `BidKingConfirmBid` 点击。

屏幕区域一律来自 layout，不走参数（选项覆盖可能整块替换参数并导致区域丢失）。
"""

import time
import traceback

from maa.agent.agent_server import AgentServer
from maa.context import Context
from maa.custom_action import CustomAction

from .....Common.utils import get_image, load_params
from utils.logger import logger
from utils.maafocus import PrintT

from ....core.contracts import SCHEMA_VERSION, Meta, Observation
from ....core.decide import (
    FALLBACK_AMOUNT,
    REASON_ERROR,
    decide as run_decide,
    resolve,
)
from ....core.policy import (
    DEFAULT_STRATEGY,
    BidDecision,
    is_known_reason,
    message_for,
)
from ....core.session import append_observation, write_meta
from .. import state
from ..capture import recorder, timing
from ..capture.scrollbar import capture_live_pages
from ..layout import (
    SETTLE_ROI,
    WAREHOUSE_SCROLLBAR_TRACK,
    WAREHOUSE_THUMB_TOP,
)
from ..perceive import perceive
from ..state import PendingBid

# 等本轮信息到位：情报卡片列连续静止多久才认为披露动画播完
SETTLE_TIME = 0.8
# 等待上限（秒）。超时不是错误——按当前画面继续，读不到的字段走各自兜底
SETTLE_TIMEOUT = 12.0
# 卡片静止后系统还要更新包裹与顶栏估价，这一段看不见只能等（实测足够的上界）
SETTLE_EXTRA = 5.0


@AgentServer.custom_action("observe_round")
class ObserveRound(CustomAction):
    """观察窗口：等本轮信息到位 → 采集 → 感知 → 决策 → 把金额交给输入步骤"""

    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        try:
            self._run(context, getattr(argv, "custom_action_param", None))
        except Exception as exc:
            logger.error("❌ 观察窗口异常，兜底出 %d: %s", FALLBACK_AMOUNT, exc)
            logger.error("%s", traceback.format_exc())
            PrintT(context, "bidking.failed", str(exc))
            # 异常也要给出一笔出价——放弃本轮的代价高于出一个最低价
            state.set_pending(PendingBid(FALLBACK_AMOUNT, DEFAULT_STRATEGY, REASON_ERROR))
        return CustomAction.RunResult(success=True)

    # ---------- 主流程 ----------

    def _run(self, context: Context, raw_param) -> None:
        # 处理pipeline流程节点传入的参数，对应custom_action_param
        # 将其中的各参数转为dict类型
        param = load_params(raw_param)

        # 设定调用该python文件的节点传入的custom_action_param有strategy,strategy_param等参数
        # 获取策略名称
        strategy_param = param.get("strategy_param")
        # 因为python不做强制类型检查，因此需要额外检查以及处理空的情况，如果不是字典类，设为空字典
        if not isinstance(strategy_param, dict):
            if strategy_param is not None:
                logger.warning(
                    "⚠️ strategy_param 不是字典（%s），按空参数处理",
                    type(strategy_param).__name__,
                )
            strategy_param = {}

        # 读取用户指定策略；未知策略的回落由 core.decide 统一处理
        requested = str(param.get("strategy") or DEFAULT_STRATEGY)
        # _用来占位，接收那个确定不用的返回参数
        _, strategy_name, fell_back = resolve(requested)
        if fell_back:
            logger.warning("⚠️ 未知策略 %r，回落到 %r", requested, DEFAULT_STRATEGY)
            PrintT(context, "bidking.strategy_unknown", requested, DEFAULT_STRATEGY)

        # 新一回合清空last_bid值
        state.begin_round()
        controller = context.tasker.controller
        started = time.time()
        # ---- 1. 等本轮信息到位（采集时机决策）----
        stable = timing.wait_until_stable(
            controller,
            SETTLE_ROI,
            SETTLE_TIME,
            SETTLE_TIMEOUT,
            should_stop=lambda: bool(context.tasker.stopping),
        )
        if stable:
            time.sleep(SETTLE_EXTRA)

        # ---- 2. 采集：三页仓库（不可逆的一步）----
        pages = capture_live_pages(
            controller,
            WAREHOUSE_SCROLLBAR_TRACK,
            WAREHOUSE_THUMB_TOP[3],
            should_stop=lambda: bool(context.tasker.stopping),
        )
        frame = next((page for page in pages if page is not None), None)
        if frame is None:
            # 采集整体失败时至少再试一次单帧，保证感知/出价不被卡死
            frame = get_image(controller)
            pages = [frame] if frame is not None else []
            if frame is None:
                logger.error("❌ 截图失败，本轮无法采集与感知")

        # ---- 3. 感知 ----
        # 截图成功就感知，否则用一个空观测
        observation = perceive(context, frame) if frame is not None else Observation()

        # 新一局的第一回合：清掉上一局的 last_bid 与采集会话。
        # 上一局的结算采集发生在此前，已经写入旧 session；这里只重置指针。
        if observation.round == 1 and recorder.session_dir() is not None:
            logger.info("🆕 新一局开始，重置会话状态与采集会话")
            state.reset()
            recorder.reset()

        observation.last_bid = state.last_bid()

        # ---- 4. 决策：与回放共用同一个运行器，兜底路径也一致 ----
        decision = run_decide(observation, requested, strategy_param)
        observation.decision = decision.amount

        # ---- 5. 落盘：三页仓库帧 + 观测 + 决定，供事后复盘与回放 ----
        self._record(pages, observation, decision, strategy_name, strategy_param)
        append_observation(recorder.session_dir(), observation)

        # ---- 6. 交给输入步骤，并把兜底分支讲给用户听 ----
        state.set_pending(PendingBid(decision.amount, strategy_name, decision.reason))
        self._announce(context, decision, strategy_name)

        logger.info(
            "🎯 本轮出价额: %d（策略=%s, 分支=%s, 观察耗时 %.1fs）",
            decision.amount,
            strategy_name,
            decision.reason,
            time.time() - started,
        )

    # ---------- 各步骤 ----------

    @staticmethod
    def _record(frames, observation, decision, strategy_name, strategy_param) -> None:
        """采集三页原始帧；首轮同时写 session.json（由 core.session 负责格式）。"""
        frames = list(frames or [])
        first = next((frame for frame in frames if frame is not None), None)
        if first is None:
            logger.warning("⚠️ 本轮无画面可存，采集缺失")
            return

        session_dir = recorder.start_session()
        if session_dir is None:
            logger.warning("⚠️ 采集会话不可用，跳过本帧")
            return

        # 当没有session.json时，会写一次元数据（即初始化元数据）
        if not (session_dir / "session.json").exists():
            write_meta(
                session_dir,
                Meta(
                    schema_version=SCHEMA_VERSION,
                    source="live",
                    resolution=[int(first.shape[1]), int(first.shape[0])],
                    strategy=strategy_name,
                    strategy_param=dict(strategy_param),
                ),
            )

        # 追加一条采集事件；三页帧按顶/中/底顺序存为同一事件的 frames 列表
        round_no = observation.round
        tag = f"r{round_no}_warehouse" if round_no else "r_unknown_warehouse"
        recorder.record(
            tag,
            frames,
            {
                "round": round_no,
                "observation": observation.to_dict(),
                "strategy": strategy_name,
                "amount": decision.amount,
                "reason": decision.reason,
            },
        )

    @staticmethod
    def _announce(context: Context, decision: BidDecision, strategy_name: str) -> None:
        key = message_for(decision.reason)
        if key:
            PrintT(context, key, decision.amount)
        elif not is_known_reason(decision.reason):
            # 新策略忘了登记 reason 的信号，不静默
            logger.warning(
                "⚠️ 策略 %s 返回了未登记的 reason=%r（用户看不到该分支的说明）",
                strategy_name,
                decision.reason,
            )
