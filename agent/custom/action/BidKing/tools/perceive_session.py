#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""离线仓库感知 CLI（0b1b1 合并/预览；0b1b2 块级分割/分类）。

用法：

    .venv/Scripts/python.exe agent/custom/action/BidKing/tools/perceive_session.py \
        <会话目录> [--scale 0.5] [--include-settlement] [--blocks]

这是**调试入口**，不是独立的感知层：它把 BidKing/ 加到 sys.path 后调用
`sources.live.perceive.warehouse`（实时观察窗口/定盘预览用的同一份纯 CV 实现），
不会加载 MaaFramework。

加 `--blocks` 时对局内仓库做块级分割/分类，额外写入
`preview/r{n}_blocks.png` 和 `preview/r{n}_blocks.json`；结算画面不做块分类
（结算渲染不同，留 0b1c）。不写 warehouse.jsonl。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BIDKING_DIR = Path(__file__).resolve().parents[1]
if str(BIDKING_DIR) not in sys.path:
    sys.path.insert(0, str(BIDKING_DIR))

from sources.live.perceive.warehouse.session import (  # noqa: E402
    generate_session_previews,
)


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
    blocks: bool = False,
    debug_edges: bool = False,
) -> int:
    if not session_dir.is_dir():
        print(f"会话目录不存在: {session_dir}")
        return 2

    results = generate_session_previews(
        session_dir,
        preview_dir=preview_dir,
        scale=scale,
        include_settlement=include_settlement,
        page_offsets=page_offsets,
        blocks=blocks,
        debug_edges=debug_edges,
    )
    if not results:
        print("没有可处理的 warehouse/settlement 事件（0b1a 采集缺失？）")
        return 1

    for result in results:
        offsets_text = "/".join(f"{offset:.2f}" for offset in result.offsets)
        print(
            f"{result.label}: frames={result.frames}/3 "
            f"coverage={result.coverage} offsets={offsets_text} "
            f"-> {result.preview_path}"
        )
        if blocks:
            if result.is_settlement:
                print(f"{result.label}: settlement 不做 0b1b2 块分类（留 0b1c）")
            elif result.block_stats is not None:
                stats = result.block_stats
                print(
                    f"{result.label}: blocks={stats.get('block_count', 0)} "
                    f"states={stats.get('state_counts', {})} "
                    f"flags={stats.get('flag_counts', {})} "
                    f"unknown_cells={stats.get('unknown_cells')} "
                    f"filtered={stats.get('filtered_components', 0)} "
                    f"-> {result.block_path}"
                )

    print(f"\n完成: {len(results)} 个事件，预览目录: {preview_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="离线合并 BidKing 仓库三页帧并生成预览/块分类"
    )
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
        help="手动指定三页滚动行（逗号分隔，如 0,9.9,14.9）；默认从格子相位检测",
    )
    parser.add_argument(
        "--blocks",
        action="store_true",
        help="0b1b2：对局内仓库做块级分割/分类，输出 preview/r{n}_blocks.png/.json",
    )
    parser.add_argument(
        "--debug-edges",
        action="store_true",
        help="在块预览上画出判定为块边界的接缝线（隐含 --blocks）",
    )
    parser.add_argument(
        "--preview-only",
        action="store_true",
        help="兼容旧参数；默认仍生成三页合并预览",
    )
    args = parser.parse_args(argv)

    session_dir = Path(args.session_dir)
    preview_dir = Path(args.preview_dir) if args.preview_dir else session_dir / "preview"
    try:
        page_offsets = _parse_offsets(args.page_offsets)
    except ValueError as exc:
        parser.error(str(exc))
    return perceive_session(
        session_dir,
        preview_dir,
        args.scale,
        args.include_settlement,
        page_offsets,
        blocks=args.blocks or args.debug_edges,
        debug_edges=args.debug_edges,
    )


if __name__ == "__main__":
    raise SystemExit(main())
