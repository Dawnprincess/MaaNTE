import json
import time
from typing import Any

from maa.agent.agent_server import AgentServer
from maa.context import Context
from maa.custom_action import CustomAction
from maa.pipeline import JOCR, JRecognitionType

from .Common.logger import get_logger
from .Navi import LocalRouteNavigation
from .Navi.resource_paths import resource_base_path
from .MapTeleport.teleport_to_point import run_map_teleport_flow

logger = get_logger(__name__)

# ---------------- 常量 ----------------
ROUTE_FILE = "wallet"           # 路线文件名
VK_F = 0x46                     # F 键的 Windows 虚拟键码

# OCR 参数
OCR_ROI = (734, 263, 316, 254)                  # 拾取提示文字的 ROI（1280×720 基准）
POSITIVES = ["团三郎", "咕比", "劲爽", "再来一口", "馈赠", "一箱", "猎人", "心猎骑士"]   # 正期望词表
NEGATIVES = ["售货机", "坐下", "驾驶", "乘坐", "搭乘", "安魂曲"]                    # 负期望词表
OCR_THRESHOLD = 0.5                              # OCR 命中阈值

# 拾取节奏
PRESS_DELAY = 0.5               # F 键模式下，相邻两次按 F 之间的间隔
WAIT_AFTER_ROUND1 = 1.5         # 第一轮结束到第二轮开始之间的等待
WAIT_AFTER_ALT_CLICK = 1.5      # alt_click 模式下，相邻两次点击间隔

# 寻路后等待
WAIT_AFTER_NAVIGATE = 1.5       # 寻路成功后到第一次识别之间的等待

# 传送等待
WAIT_WORLD_TIMEOUT = 40.0       # 传送后等待回到大世界的最长时间
WAIT_WORLD_INTERVAL = 1.0       # InWorld 轮询间隔

# 寻路参数
NAV_MAX_DURATION = 30           # 每个路径点的寻路超时（秒）
NAV_TOLERANCE = 2               # 到达判定的距离阈值


# ============================================================
# 资源读取
# ============================================================
def _load_routes() -> list[dict]:
    routes_dir = resource_base_path().parent / "routes"
    file_path = routes_dir / f"{ROUTE_FILE}.json"
    with file_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    routes = data.get("routes") if isinstance(data, dict) else None
    return routes if isinstance(routes, list) else []


def _load_teleport_name(teleport_id: str) -> str:
    points_file = resource_base_path() / "map_teleport" / "teleport_points.json"
    try:
        with points_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return teleport_id
    for p in data.get("teleport_points", []):
        if p.get("id") == teleport_id:
            return p.get("name", teleport_id)
    return teleport_id


# ============================================================
# 通用工具
# ============================================================
def _box_to_xywh(box: Any):
    if box is None:
        return None
    if isinstance(box, (list, tuple)) and len(box) >= 4:
        return int(box[0]), int(box[1]), int(box[2]), int(box[3])
    if all(hasattr(box, a) for a in ("x", "y", "w", "h")):
        return int(box.x), int(box.y), int(box.w), int(box.h)
    return None


def _wait_in_world(context: Context, timeout: float) -> bool:
    controller = context.tasker.controller
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if context.tasker.stopping:
            return False
        frame = controller.post_screencap().wait().get()
        if frame is None:
            time.sleep(WAIT_WORLD_INTERVAL)
            continue
        try:
            result = context.run_recognition("InWorld", frame)
        except Exception:
            time.sleep(WAIT_WORLD_INTERVAL)
            continue
        if result and getattr(result, "hit", False):
            return True
        time.sleep(WAIT_WORLD_INTERVAL)
    return False


# ============================================================
# OCR
# ============================================================
def _ocr_raw(context: Context, frame, expected: list[str]):
    try:
        return context.run_recognition_direct(
            JRecognitionType.OCR,
            JOCR(expected=list(expected), roi=tuple(OCR_ROI), threshold=OCR_THRESHOLD),
            frame,
        )
    except Exception:
        return None


def _ocr_hit(context: Context, frame, expected: list[str]) -> bool:
    detail = _ocr_raw(context, frame, expected)
    return bool(detail is not None and getattr(detail, "hit", False))


def _ocr_all_hits(context: Context, frame, expected: list[str]) -> list[dict]:
    detail = _ocr_raw(context, frame, expected)
    if detail is None or not getattr(detail, "hit", False):
        return []
    hits = []
    seen = set()
    for item in (getattr(detail, "filtered_results", None) or []):
        text = getattr(item, "text", "") or ""
        if not any(p in text for p in expected):
            continue
        box = _box_to_xywh(getattr(item, "box", None))
        if box is None or box in seen:
            continue
        seen.add(box)
        hits.append({"box": box, "text": text})
    return hits


# ============================================================
# 按键 / alt_click
# ============================================================
def _press_f(context: Context) -> None:
    node = "__PickWalletPressF"
    try:
        context.run_action(
            node,
            pipeline_override={
                node: {
                    "action": {"type": "ClickKey", "param": {"key": [VK_F]}},
                    "pre_delay": 0, "post_delay": 0, "rate_limit": 0,
                }
            },
        )
    except Exception:
        pass


def _alt_click_box(context: Context, box: list[int]) -> None:
    try:
        context.run_action("__AltClickAltKeyDownAction")
        context.run_action(
            "__AltClickMouseClickAction",
            pipeline_override={
                "__AltClickMouseClickAction": {
                    "action": {"param": {"target": list(box)}}
                },
            },
        )
        context.run_action("__AltClickAltKeyUpAction")
    except Exception:
        pass


# ============================================================
# 拾取流程
# ============================================================
def _do_pick_round(context: Context, round_name: str) -> bool:
    controller = context.tasker.controller
    frame = controller.post_screencap().wait().get()
    if frame is None:
        return False
    has_negative = _ocr_hit(context, frame, NEGATIVES)
    pos_hits = _ocr_all_hits(context, frame, POSITIVES)

    logger.info(f"{round_name}识别，正期望{len(pos_hits)}个，负期望{int(has_negative)}个")

    if not pos_hits:
        logger.info("无正期望，该点位结束")
        return False

    if has_negative:
        logger.info("alt_click模式，依次点击拾取")
        target_count = len(pos_hits)
        for _ in range(target_count):
            if context.tasker.stopping:
                return False
            frame = controller.post_screencap().wait().get()
            if frame is None:
                break
            hits = _ocr_all_hits(context, frame, POSITIVES)
            if not hits:
                logger.info("未识别到正期望，提前结束 alt_click")
                break
            _alt_click_box(context, hits[0]["box"])
            time.sleep(WAIT_AFTER_ALT_CLICK)
        return False

    logger.info(f"F键模式，按下{len(pos_hits)}次")
    for _ in range(len(pos_hits)):
        _press_f(context)
        time.sleep(PRESS_DELAY)
    return True


def _pick_wallet(context: Context) -> None:
    if not _do_pick_round(context, "第一轮"):
        return
    time.sleep(WAIT_AFTER_ROUND1)
    _do_pick_round(context, "第二轮")


# ============================================================
# 传送
# ============================================================
def _do_teleport(context: Context, tp_id: str) -> bool:
    try:
        ok = run_map_teleport_flow(context, tp_id)
        return bool(ok)
    except Exception as exc:
        logger.error(f"传送异常: {type(exc).__name__}: {exc}")
        return False


# ============================================================
# 寻路（开启跳跃，透传超时）
# ============================================================
def _do_navigate(context: Context, route_name: str, p_idx: int) -> bool:
    try:
        with LocalRouteNavigation(
            context,
            ROUTE_FILE,
            tolerance=NAV_TOLERANCE,
            angle_backend="auto",
            position_backend="coordinate",
            frame_interval=0.1,
            max_duration=NAV_MAX_DURATION,
            periodic_jump=True,  # 【开启周期性跳跃】
        ) as navi:
            ok = navi.run_route(route_name=route_name, segment_index=p_idx)
        return bool(ok)
    except Exception as exc:
        logger.error(f"navigate 异常: {type(exc).__name__}: {exc}")
        return False


# ============================================================
# 回溯 / 跳点目标查找
# ============================================================
def _find_backtrack_target(segments: list[dict], current_p: int) -> int:
    """向前找（含当前点）最近的传送点"""
    for p in range(current_p, 0, -1):
        if segments[p - 1].get("need_teleport", False):
            return p
    return 1


def _find_forward_teleport_target(segments: list[dict], current_p: int) -> int | None:
    """向后找（不含当前点）最近的传送点"""
    total = len(segments)
    for p in range(current_p + 1, total + 1):
        if segments[p - 1].get("need_teleport", False):
            return p
    return None


# ============================================================
# 主循环
# ============================================================
@AgentServer.custom_action("pick_wallet_run_all")
class PickWalletRunAll(CustomAction):
    def __init__(self):
        super().__init__()

    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        # 使用 attach 字段绕过 Maa 的字段校验，杜绝 UI 覆盖丢失的问题。
        start_route = int(context.get_node_data("PickWalletCfg_StartRoute")["attach"]["val"])
        limit_count = bool(context.get_node_data("PickWalletCfg_LimitCount")["attach"]["val"])
        enable_backtrack = bool(context.get_node_data("PickWalletCfg_EnableBacktrack")["attach"]["val"])
        
        if limit_count:
            route_count = int(context.get_node_data("PickWalletCfg_RouteCount")["attach"]["val"])
        else:
            route_count = 1

        # ---- 读取路线 ----
        try:
            routes = _load_routes()
        except Exception as exc:
            logger.error(f"读取 wallet.json 失败: {exc}")
            return CustomAction.RunResult(success=False)

        if not routes:
            logger.error("wallet.json 中没有任何路线")
            return CustomAction.RunResult(success=False)

        route_start_globals = []
        acc = 0
        for route in routes:
            route_start_globals.append(acc + 1)
            acc += len(route.get("segments", []))
        total_segments = acc

        logger.info(f"[PickWallet] 已加载 {len(routes)} 条路线，共 {total_segments} 个点位")
        if limit_count:
            logger.info(f"[PickWallet] 限制条件：从 R{start_route} 开始，往后执行 {route_count} 条路线")
        else:
            logger.info(f"[PickWallet] 执行条件：从 R{start_route} 开始，一直跑到最后一条路线")
        logger.info(f"[PickWallet] 寻路失败回溯功能：{'开启' if enable_backtrack else '关闭'}")

        # 超出范围直接抛出异常崩溃
        if start_route > len(routes):
            raise ValueError(f"start_route={start_route} 非法（超出总路线数 {len(routes)}）")

        processed_routes = 0  # 记录本次任务已开始处理的路线数量

        # ---- 遍历路线 ----
        for r_idx in range(start_route, len(routes) + 1):
            if context.tasker.stopping:
                return CustomAction.RunResult(success=True)

            # 检查“限制执行路线数量”开关
            if limit_count and processed_routes >= route_count:
                logger.info(f"[PickWallet] 已达到设定的执行路线总数 ({route_count})，任务结束。")
                break

            route = routes[r_idx - 1]
            segments = route.get("segments", [])
            if not segments:
                continue
            
            processed_routes += 1  # 只要开始处理（非空路线），计数就 +1

            route_name = route.get("name", "")
            route_start_global = route_start_globals[r_idx - 1]
            backtracked = False
            retry_target_p = None
            p_idx = 1

            while p_idx <= len(segments):
                if context.tasker.stopping:
                    return CustomAction.RunResult(success=True)

                seg = segments[p_idx - 1]
                need_tp = bool(seg.get("need_teleport", False))
                tp_id = seg.get("teleport_point_id", "") if need_tp else ""
                global_idx = route_start_global + p_idx - 1

                logger.info(f"第{r_idx}路线第{p_idx}点位，总第{global_idx}点位")

                # ---------- 传送 ----------
                if need_tp:
                    tp_name = _load_teleport_name(tp_id)
                    logger.info(f"准备使用地图传送，{tp_name}")

                    if not _do_teleport(context, tp_id):
                        if context.tasker.stopping:
                            return CustomAction.RunResult(success=True)
                        logger.error(f"R{r_idx}P{p_idx} 传送失败，任务结束")
                        return CustomAction.RunResult(success=False)

                    if not _wait_in_world(context, WAIT_WORLD_TIMEOUT):
                        if context.tasker.stopping:
                            return CustomAction.RunResult(success=True)
                        return CustomAction.RunResult(success=False)

                    logger.info("传送完成，开始寻路")
                else:
                    logger.info("开始寻路")

                # ---------- 寻路 ----------
                navigate_ok = _do_navigate(context, route_name, p_idx)

                if not navigate_ok:
                    if context.tasker.stopping:
                        return CustomAction.RunResult(success=True)

                    # 1. 如果开启了回溯，且本路线未回溯过，执行向前回溯
                    if enable_backtrack and not backtracked:
                        target_p = _find_backtrack_target(segments, p_idx)
                        backtracked = True
                        target_global = route_start_global + target_p - 1
                        logger.info(f"寻路超时，回溯到当前路线第{target_p}点位，总第{target_global}点位")
                        retry_target_p = p_idx
                        p_idx = target_p
                        continue

                    # 2. 其他情况（未开启回溯，或已回溯过，或向前回溯失败），进入向后跳点逻辑
                    retry_target_p = None  # 强制清空追赶状态
                    forward_tp = _find_forward_teleport_target(segments, p_idx)
                    
                    if forward_tp is not None:
                        target_global = route_start_global + forward_tp - 1
                        logger.info(f"寻路超时，放弃中间点位，跳至下一个传送点：第{forward_tp}点位，总第{target_global}点位")
                        p_idx = forward_tp
                        continue
                    else:
                        logger.warning("后续无可用传送点，放弃当前路线剩余点位")
                        break

                # ---------- 寻路成功，判断是否拾取 ----------
                should_pickup = (retry_target_p is None) or (p_idx >= retry_target_p)
                if should_pickup:
                    time.sleep(WAIT_AFTER_NAVIGATE)
                    _pick_wallet(context)
                    if retry_target_p is not None and p_idx >= retry_target_p:
                        retry_target_p = None

                p_idx += 1

        return CustomAction.RunResult(success=True)