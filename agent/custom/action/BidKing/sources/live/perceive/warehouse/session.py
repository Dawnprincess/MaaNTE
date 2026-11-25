# -*- coding: utf-8 -*-
"""已保存会话的感知与预览生成（实时定盘/离线 QA 共用）。

输入是 `events.jsonl` + `frames/`，输出是 `<session>/preview/` 下的合并图、
块状态调试图和 blocks JSON。纯 cv2/numpy，不依赖 MaaFramework，也不改会话原始数据。

实时流程里由定盘动作（capture_settlement）在结算帧落盘后自动调用；
离线调试由 `tools/perceive_session.py` 调用同一函数。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import cv2

try:  # 实机：custom.action.BidKing.sources.live.perceive.warehouse
    from .....core.geometry import (
        SETTLEMENT_SCROLLBAR_TRACK,
        SETTLEMENT_THUMB_TOP,
        SETTLEMENT_VIEW,
        WAREHOUSE_SCROLLBAR_TRACK,
        WAREHOUSE_THUMB_TOP,
        WAREHOUSE_VIEW,
    )
except ImportError:  # 离线：BidKing/ 在 sys.path 上，顶层包导入
    from core.geometry import (
        SETTLEMENT_SCROLLBAR_TRACK,
        SETTLEMENT_THUMB_TOP,
        SETTLEMENT_VIEW,
        WAREHOUSE_SCROLLBAR_TRACK,
        WAREHOUSE_THUMB_TOP,
        WAREHOUSE_VIEW,
    )

from .blocks import detect_blocks
from .frames import (
    build_canvas,
    detect_page_offsets,
    load_events,
    load_page_frames,
    page_coverage,
)
from .preview import render_blocks_preview, render_preview, save_preview

_ROUND_RE = re.compile(r"r(\d+)_warehouse")


@dataclass
class PreviewResult:
    label: str
    is_settlement: bool
    preview_path: Path
    frames: int
    coverage: list[tuple[int, int, int]]
    offsets: list[float]
    block_path: Optional[Path] = None
    json_path: Optional[Path] = None
    block_stats: Optional[dict] = None


def _round_of(event: dict) -> Optional[int]:
    round_no = event.get("round")
    if isinstance(round_no, int):
        return round_no
    matched = _ROUND_RE.fullmatch(str(event.get("tag", "")))
    return int(matched.group(1)) if matched else None


def _label_of(event: dict) -> Optional[str]:
    round_no = _round_of(event)
    if round_no is not None:
        return f"r{round_no}"
    if str(event.get("tag", "")) == "settlement":
        return "settlement"
    return None


def _is_selected(event: dict, include_settlement: bool) -> bool:
    tag = str(event.get("tag", ""))
    if tag.endswith("_warehouse"):
        return True
    return include_settlement and tag == "settlement"


def _resize(image, scale: float):
    if scale == 1.0:
        return image
    return cv2.resize(
        image,
        (
            max(1, round(image.shape[1] * scale)),
            max(1, round(image.shape[0] * scale)),
        ),
        interpolation=cv2.INTER_AREA,
    )


def generate_session_previews(
    session_dir: Path | str,
    preview_dir: Path | str | None = None,
    scale: float = 1.0,
    include_settlement: bool = False,
    page_offsets: Sequence[float] | None = None,
    blocks: bool = False,
    debug_edges: bool = False,
) -> list[PreviewResult]:
    """读取一个会话，生成合并图/块状态图/JSON；返回每个事件的生成结果。

    失败的事件跳过，不抛异常；调用方（实机定盘/CLI）只应根据返回列表判断是否
    有产物。不写 `warehouse.jsonl`。
    """
    session_dir = Path(session_dir)
    if not session_dir.is_dir():
        return []
    events = [
        event
        for event in load_events(session_dir)
        if _is_selected(event, include_settlement)
    ]
    if not events:
        return []

    preview_dir = (
        Path(preview_dir) if preview_dir is not None else session_dir / "preview"
    )
    preview_dir.mkdir(parents=True, exist_ok=True)

    results: list[PreviewResult] = []
    for event in events:
        label = _label_of(event)
        frames = event.get("frames") or []
        if label is None or len(frames) != 3:
            continue

        settlement = str(event.get("tag", "")) == "settlement"
        view = SETTLEMENT_VIEW if settlement else WAREHOUSE_VIEW
        track = (
            SETTLEMENT_SCROLLBAR_TRACK if settlement else WAREHOUSE_SCROLLBAR_TRACK
        )
        thumb_h = SETTLEMENT_THUMB_TOP[3] if settlement else WAREHOUSE_THUMB_TOP[3]

        pages = load_page_frames(session_dir, event)
        offsets = (
            list(page_offsets)
            if page_offsets is not None
            else detect_page_offsets(pages, view, track, thumb_h)
        )
        canvas = build_canvas(pages, view=view, page_offsets=offsets)
        preview = _resize(render_preview(canvas, view=view, page_offsets=offsets), scale)
        preview_path = preview_dir / f"{label}_warehouse.png"
        if not save_preview(preview_path, preview):
            continue

        result = PreviewResult(
            label=label,
            is_settlement=settlement,
            preview_path=preview_path,
            frames=sum(page is not None for page in pages),
            coverage=page_coverage(pages),
            offsets=offsets,
        )

        if blocks and not settlement:
            detection = detect_blocks(canvas)
            block_preview = _resize(
                render_blocks_preview(
                    canvas,
                    detection,
                    debug_edges=debug_edges,
                    page_offsets=offsets,
                ),
                scale,
            )
            block_path = preview_dir / f"{label}_blocks.png"
            if save_preview(block_path, block_preview):
                result.block_path = block_path
            json_path = preview_dir / f"{label}_blocks.json"
            try:
                json_path.write_text(
                    json.dumps(detection.to_dict(), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                result.json_path = json_path
            except OSError:
                pass
            result.block_stats = detection.stats

        results.append(result)

    return results


__all__ = ["PreviewResult", "generate_session_previews"]
