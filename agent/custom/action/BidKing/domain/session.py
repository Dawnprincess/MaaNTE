# -*- coding: utf-8 -*-
"""拍卖之王 —— 会话读写（核心层）

会话目录布局（见 openspec design D4）：

    <session>/
      session.json        元数据（实机由采集层写，模拟由本模块写）
      observations.jsonl  逐轮观测，只追加
      settlement.json     结算真值（可选）

读取必须是**宽容**的：目录不存在、行损坏、文件缺失都不能让回放崩掉，
只记录告警并尽量读出已有内容。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional, Union

from .contracts import Meta, Observation, Session, Settlement

logger = logging.getLogger(__name__)

META_FILENAME = "session.json"
OBSERVATIONS_FILENAME = "observations.jsonl"
SETTLEMENT_FILENAME = "settlement.json"


def append_observation(
    session_dir: Optional[Union[Path, str]], observation: Observation
) -> bool:
    """把一轮观测追加到 observations.jsonl；失败只记日志，不抛出。"""
    if session_dir is None:
        return False
    try:
        root = Path(session_dir)
        root.mkdir(parents=True, exist_ok=True)
        line = json.dumps(observation.to_dict(), ensure_ascii=False)
        with open(root / OBSERVATIONS_FILENAME, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        return True
    except Exception as exc:  # noqa: BLE001 - 采集失败不得中断出价
        logger.warning("⚠️ 观测写入失败（不影响出价）: %s", exc)
        return False


def write_meta(session_dir: Union[Path, str], meta: Meta) -> bool:
    """写 session.json（实机由采集层负责，这里供模拟器与会话修复使用）。"""
    try:
        root = Path(session_dir)
        root.mkdir(parents=True, exist_ok=True)
        (root / META_FILENAME).write_text(
            json.dumps(meta.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("⚠️ 元数据写入失败: %s", exc)
        return False


def write_settlement(session_dir: Union[Path, str], settlement: Settlement) -> bool:
    """写 settlement.json（结算真值）。"""
    try:
        root = Path(session_dir)
        root.mkdir(parents=True, exist_ok=True)
        (root / SETTLEMENT_FILENAME).write_text(
            json.dumps(settlement.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("⚠️ 结算写入失败: %s", exc)
        return False


def read_session(session_dir: Union[Path, str]) -> Session:
    """读出一个会话；坏行跳过并告警，缺失文件按空处理。"""
    root = Path(session_dir)
    meta = _read_meta(root)
    rounds = _read_observations(root)
    settlement = _read_settlement(root)
    return Session(meta=meta, rounds=rounds, settlement=settlement)


def _read_meta(root: Path) -> Meta:
    path = root / META_FILENAME
    if not path.exists():
        logger.warning("⚠️ 缺少 %s，按空元数据处理: %s", META_FILENAME, root)
        return Meta()
    try:
        return Meta.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception as exc:  # noqa: BLE001
        logger.warning("⚠️ 元数据无法解析，按空处理: %s", exc)
        return Meta()


def _read_observations(root: Path) -> list[Observation]:
    path = root / OBSERVATIONS_FILENAME
    if not path.exists():
        logger.warning("⚠️ 缺少 %s，回放将没有逐轮观测: %s", OBSERVATIONS_FILENAME, root)
        return []

    rounds: list[Observation] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rounds.append(Observation.from_dict(json.loads(line)))
        except Exception as exc:  # noqa: BLE001
            logger.warning("⚠️ 跳过第 %d 行损坏观测: %s", lineno, exc)
    return rounds


def _read_settlement(root: Path) -> Optional[Settlement]:
    path = root / SETTLEMENT_FILENAME
    if not path.exists():
        return None
    try:
        return Settlement.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception as exc:  # noqa: BLE001
        logger.warning("⚠️ 结算记录无法解析，按缺失处理: %s", exc)
        return None
