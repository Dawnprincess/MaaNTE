#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""离线仓库感知 CLI（0b1b1：仅三页合并/预览）。

用法：
    .venv/Scripts/python.exe agent/custom/action/BidKing/tools/perceive_session.py <会话目录> [--scale 0.5] [--include-settlement]

读取会话的 events.jsonl 中 `r{n}_warehouse` 事件，加载三页帧，按绝对行合并为
10×25 预览，写入 `<会话>/preview/r{n}_warehouse.png`。加 `--include-settlement`
时也合并 `settlement` 三页，写入 `preview/settlement_warehouse.png`。
每页按滑条 thumb 检测实际滚动行（可为小数），避免页内半行偏移。
不做格子分类、不写状态。

只依赖 core.geometry / perception / OpenCV / numpy，不加载 MaaFramework。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import cv2

BIDKING_DIR = Path(__file__).resolve().parents[1]
if str(BIDKING_DIR) not in sys.path:
    sys.path.insert(0, str(BIDKING_DIR))

from core.geometry import (  # noqa: E402
    SETTLEMENT_SCROLLBAR_TRACK,
    SETTLEMENT_THUMB_TOP,
    SETTLEMENT_VIEW,
    WAREHOUSE_SCROLLBAR_TRACK,
    WAREHOUSE_THUMB_TOP,
    WAREHOUSE_VIEW,
)
from perception import (  # noqa: E402
    build_canvas,
    detect_page_offsets,
    load_events,
    load_page_frames,
    render_preview,
    save_preview,
)
from perception.frames import page_coverage  # noqa: E402

_ROUND_RE = re.compile(r"r(\d+)_warehouse")


def _round_of(event: dict) -> int | None:
    round_no = event.get("round")
    if isinstance(round_no, int):
        return round_no
    matched = _ROUND_RE.fullmatch(str(event.get("tag", "")))
    return int(matched.group(1)) if matched else None


def _label_of(event: dict) -> str | None:
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


def _parse_offsets(text: str | None) -> list[float] | None:
    if not text:
        return None
    values = [part.strip() for part in text.split(",") if part.strip()]
    if len(values) != 3:
        raise ValueError("--page-offsets 需要 3 个逗号分隔的数字")
    return [float(value) for value in values]


def perceive_session(
    session_dir: Path,
    preview_dir: Path,
    scale: float,
    include_settlement: bool = False,
    page_offsets: list[float] | None = None,
) -> int:
    if not session_dir.is_dir():
        print(f"会话目录不存在: {session_dir}")
        return 2

    events = [
        event for event in load_events(session_dir) if _is_selected(event, include_settlement)
    ]
    if not events:
        print("没有可处理的 warehouse/settlement 事件（0b1a 采集缺失？）")
        return 1

    preview_dir.mkdir(parents=True, exist_ok=True)
    saved = 0
    for event in events:
        label = _label_of(event)
        frames = event.get("frames") or []
        if label is None or len(frames) != 3:
            print(f"跳过异常事件: label={label} frames={len(frames)} tag={event.get('tag')}")
            continue

        settlement = str(event.get("tag", "")) == "settlement"
        view = SETTLEMENT_VIEW if settlement else WAREHOUSE_VIEW
        track = SETTLEMENT_SCROLLBAR_TRACK if settlement else WAREHOUSE_SCROLLBAR_TRACK
        thumb_h = SETTLEMENT_THUMB_TOP[3] if settlement else WAREHOUSE_THUMB_TOP[3]

        pages = load_page_frames(session_dir, event)
        offsets = page_offsets or detect_page_offsets(pages, view, track, thumb_h)
        canvas = build_canvas(pages, view=view, page_offsets=offsets)
        preview = render_preview(canvas, view=view, page_offsets=offsets)
        if scale != 1.0:
            preview = cv2.resize(
                preview,
                (max(1, round(preview.shape[1] * scale)), max(1, round(preview.shape[0] * scale))),
                interpolation=cv2.INTER_AREA,
            )
        path = preview_dir / f"{label}_warehouse.png"
        if save_preview(path, preview):
            saved += 1
            coverage = page_coverage(pages)
            offsets_text = "/".join(f"{offset:.2f}" for offset in offsets)
            print(
                f"{label}: frames={sum(p is not None for p in pages)}/3 "
                f"coverage={coverage} offsets={offsets_text} -> {path}"
            )
        else:
            print(f"{label}: 预览保存失败")

    print(f"\n完成: {saved}/{len(events)} 个事件，预览目录: {preview_dir}")
    return 0 if saved else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="离线合并 BidKing 仓库三页帧并生成预览")
    parser.add_argument("session_dir", help="会话目录，例如 data/bidking/live/20261119_155726")
    parser.add_argument("--preview-dir", help="预览输出目录，默认 <会话>/preview")
    parser.add_argument("--scale", type=float, default=1.0, help="预览缩放比例，默认 1.0")
    parser.add_argument(
        "--include-settlement",
        action="store_true",
        help="同时合并结算画面三页，输出 preview/settlement_warehouse.png",
    )
    parser.add_argument(
        "--page-offsets",
        help="手动指定三页滚动行（逗号分隔，如 0,9.9,14.9）；默认从滑条检测",
    )
    parser.add_argument(
        "--preview-only",
        action="store_true",
        help="0b1b1 仅生成预览（当前默认行为，保留参数供后续阶段）",
    )
    args = parser.parse_args(argv)

    session_dir = Path(args.session_dir)
    preview_dir = Path(args.preview_dir) if args.preview_dir else session_dir / "preview"
    try:
        page_offsets = _parse_offsets(args.page_offsets)
    except ValueError as exc:
        parser.error(str(exc))
    return perceive_session(
        session_dir, preview_dir, args.scale, args.include_settlement, page_offsets
    )


if __name__ == "__main__":
    raise SystemExit(main())
