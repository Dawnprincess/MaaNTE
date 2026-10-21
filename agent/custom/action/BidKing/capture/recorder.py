# -*- coding: utf-8 -*-
"""
拍卖之王 - 采集层（存盘）

职责边界（见 openspec/changes/bidking-observe-and-collect design D2）：
  - 只做「把不可能重来的东西存下来」：全屏原图 + 时刻标签 + 时间戳
  - 不裁剪、不识别、不依据画面内容决定是否保存
  - 不认识任何游戏语义：标签与额外元数据一律由调用方给出，本模块不解释它们
  - 采集是旁路：任何失败都只写日志，绝不抛出、绝不影响出价

产物结构：
    debug/bidking/<YYYYmmdd_HHMMSS>/
    ├─ session.json   开始时间、分辨率、任务选项、策略名等（由调用方提供）
    ├─ events.jsonl   每行一个采集事件，只追加
    └─ frames/        <seq>_<tag>_<index>.png

事件形如：
    {"seq":1,"tag":"r1_observe","frames":["0001_r1_observe_0.png"],
     "ts":1759212345.678,"mono":1234.5, ...调用方提供的额外字段}

`frames` 是**列表**：当前每个时刻恒为一个元素，但后续需要滚动截取完整
仓库时同一时刻会产生多帧——使用方按列表长度读取即可，格式不变。
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Sequence

import cv2

from utils.logger import logger

_SUBDIR = ("debug", "bidking")
_FRAME_DIRNAME = "frames"
_EVENT_FILENAME = "events.jsonl"
_SESSION_FILENAME = "session.json"


class _Session:
    """一次任务运行的采集会话"""

    def __init__(self, root: Path) -> None:
        self.root = _make_session_dir(root)
        (self.root / _FRAME_DIRNAME).mkdir(parents=True, exist_ok=True)
        self.frames_dir = self.root / _FRAME_DIRNAME
        self.events_path = self.root / _EVENT_FILENAME
        self.seq = 0

    def write_meta(self, meta: dict) -> None:
        payload = {"started_at": datetime.now().isoformat(timespec="seconds")}
        #将meta和payload里面相同的键合并
        #meta有独有的键，加入，有相同的，覆盖。其他冲突的情况按meta为主
        payload.update(meta)
        #写session.json
        path = self.root / _SESSION_FILENAME
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def next_seq(self) -> int:
        self.seq += 1
        return self.seq


_session: Optional[_Session] = None
_disabled = False


# ============ 对外接口 ============


def start_session(meta: Optional[dict] = None) -> None:
    """
    开启一次采集会话（可选）。不调用时首次 `record()` 会自动以空元数据开启。

    meta 由调用方决定放什么（分辨率、任务选项、策略名等），本模块原样写入。
    """
    global _session, _disabled
    if _session is not None or _disabled:
        return

    # 存放路径
    record_root = _record_root()
    if record_root is None:
        _disabled = True
        return

    #初始化一个session，主要包含相关文件路径
    try:
        _session = _Session(record_root)
    except Exception as exc:
        _disabled = True
        logger.warning("⚠️ 采集会话目录创建失败，本次运行不再采集: %s", exc)
        return

    if meta:
        try:
            _session.write_meta(meta)
        except Exception as exc:
            logger.warning("⚠️ 采集会话元数据写入失败: %s", exc)

    logger.info("📼 采集会话已开启: %s", _session.root)


def record(tag: str, frames: Sequence[Any], extra: Optional[dict] = None) -> None:
    """
    记录一次采集：把该时刻的若干帧落盘并追加一条事件。

    - `tag`：时刻标签（如 `r1_observe`），用于事后定位这是对局的哪个阶段
    - `frames`：该时刻的帧（BGR 图像数组），当前恒为 1 个元素，格式支持多个
    - `extra`：原样并入事件的附加字段（如 `{"round": 1}`），本模块不解释

    采集失败不影响调用方——本函数不抛异常。
    """
    if _disabled:
        return

    try:
        # 如果observe没有调用start_session，第一次record时_session还是None，这里可以保证有一个空会话（按需初始化）
        _ensure_session()
        if _session is None:
            return

        saved = _save_frames(_session, tag, frames)
        if not saved:
            logger.warning("⚠️ 本帧采集失败，跳过该时刻: tag=%s", tag)
            return

        _append_event(_session, tag, saved, extra or {})
    except Exception as exc:
        logger.warning("⚠️ 采集失败（不影响出价）: %s", exc)


def reset() -> None:
    """结束当前会话（新一轮任务开始时调用）"""
    global _session, _disabled
    if _session is not None:
        logger.info("📼 采集会话结束: %s（共 %d 次采集）", _session.root, _session.seq)
    _session = None
    _disabled = False


def session_dir() -> Optional[Path]:
    """当前会话目录；未开启时返回 None"""
    return _session.root if _session is not None else None


# ============ 内部实现 ============


def _ensure_session() -> None:
    if _session is None and not _disabled:
        start_session()


def _record_root() -> Optional[Path]:
    """定位采集根目录（`<app_root>/debug/bidking`）"""
    app_root = _find_app_root()
    if app_root is None:
        logger.warning("⚠️ 未找到应用根目录，本次运行不采集")
        return None
    try:
        #拼接完整的存放路径，后续想修改存放位置，修改SUBDIR即可
        root = app_root.joinpath(*_SUBDIR)
        root.mkdir(parents=True, exist_ok=True)
        return root
    except Exception as exc:
        logger.warning("⚠️ 采集根目录不可用 (%s): %s", root, exc)
        return None


def _find_app_root() -> Optional[Path]:
    """
    向上寻找应用根目录。

    开发布局下根目录含 `agent/` + `assets/`，打包布局（install-mxu）下含
    `agent/` + `resource/`；`agent/` 自身不含这两个同级目录，因此不会误命中。
    """
    # __file__是当前模块文件的路径，resolve将其变为绝对路径并解析符号链接（包括..、相对路径等）
    here = Path(__file__).resolve()
    # 逐级查找父目录，看是否是项目根目录
    # 判断条件1.有agent/ 2.有assets/或resource/
    # 本例中，依次检查BidKing,action,custom,agent和MaaNte，发现MaaNte符合条件，返回
    for parent in here.parents:
        if not (parent / "agent").is_dir():
            continue
        if (parent / "assets").is_dir() or (parent / "resource").is_dir():
            return parent
    return None


def _make_session_dir(base: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # 候选目录路径，乐观认为可用
    candidate = base / stamp
    # 如果发现撞名，就加后缀，循环到不撞为止
    suffix = 1
    while candidate.exists():
        candidate = base / f"{stamp}_{suffix}"
        suffix += 1
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def _save_frames(session: _Session, tag: str, frames: Sequence[Any]) -> list:
    """落盘该时刻的全部帧，返回文件名列表（全部失败时为空）"""
    seq = session.next_seq()
    safe_tag = _safe_tag(tag)
    saved = []

    for index, frame in enumerate(frames or []):
        data = _encode_png(frame)
        if data is None:
            logger.warning("⚠️ 第 %d 帧编码失败: tag=%s", index, tag)
            continue
        name = f"{seq:04d}_{safe_tag}_{index}.png"
        try:
            (session.frames_dir / name).write_bytes(data)
        except Exception as exc:
            logger.warning("⚠️ 第 %d 帧写入失败 (%s): %s", index, name, exc)
            continue
        saved.append(name)

    return saved


def _encode_png(frame) -> Optional[bytes]:
    """把 BGR 图像编码为 PNG 字节；用 imencode + write_bytes 以兼容非 ASCII 路径"""
    if frame is None or not hasattr(frame, "shape") or frame.size == 0:
        return None
    try:
        ok, buffer = cv2.imencode(".png", frame)
        if not ok:
            return None
        return buffer.tobytes()
    except Exception:
        return None


def _append_event(session: _Session, tag: str, saved: list, extra: dict) -> None:
    event = {
        "seq": session.seq,
        "tag": tag,
        "frames": saved,
        "ts": time.time(),
        "mono": time.monotonic(),
    }
    event.update(extra)

    line = json.dumps(event, ensure_ascii=False)
    with open(session.events_path, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _safe_tag(tag: str) -> str:
    """标签进文件名前做最小净化，避免路径分隔符等"""
    text = str(tag or "event").strip()
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in text)
    return cleaned[:64] or "event"
