#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""回放 CLI：把一局已保存的会话重新跑一遍出价决策。

用法（在仓库任意目录）：

    .venv/Scripts/python.exe agent/custom/action/BidKing/tools/replay.py <会话目录>

为什么手工改 sys.path：回放只依赖 `domain/`，不能走 `custom.action` 包导入——
那会触发 `custom/action/__init__.py` 里的全部动作注册（包括加载 MaaFramework），
从而让回放继承实机的管理员依赖。把 BidKing 目录放到 sys.path 首位后，
`domain` 作为顶层包导入，进程里不会出现框架。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BIDKING_DIR = Path(__file__).resolve().parents[1]
if str(BIDKING_DIR) not in sys.path:
    sys.path.insert(0, str(BIDKING_DIR))

from domain.contracts import Observation  # noqa: E402
from domain.decide import decide  # noqa: E402
from domain.session import read_session  # noqa: E402


def _fmt(value) -> str:
    return "-" if value is None else str(value)


def replay(session_dir: Path) -> int:
    session = read_session(session_dir)
    meta = session.meta
    strategy = meta.strategy or "fixed"
    params = meta.strategy_param or {}

    print(f"会话: {session_dir}")
    print(
        "元数据: source=%s venue=%s field=%s character=%s strategy=%s"
        % (
            meta.source,
            _fmt(meta.venue),
            _fmt(meta.field),
            _fmt(meta.character),
            strategy,
        )
    )
    if meta.instruments:
        print("仪器: " + "、".join(meta.instruments))
    print()

    if not session.rounds:
        print("没有可回放的逐轮观测（observations.jsonl 缺失或为空）")
        return 1

    header = f"{'回合':<4} {'估价':>10} {'上轮出价':>10} {'实机':>10} {'回放':>10} {'一致':>6}"
    print(header)
    print("-" * len(header))

    mismatches = 0
    skipped = 0
    for observation in session.rounds:
        decision = decide(observation, strategy, params)
        live = observation.decision
        if live is None:
            skipped += 1
            mark = "n/a"
        elif live == decision.amount:
            mark = "OK"
        else:
            mark = "FAIL"
            mismatches += 1
        print(
            f"{_fmt(observation.round):<4} {_fmt(observation.valuation):>10} "
            f"{_fmt(observation.last_bid):>10} {_fmt(live):>10} {decision.amount:>10} {mark:>6}"
        )

    print()
    if mismatches:
        print(f"FAIL：{mismatches} 轮不一致")
        return 1
    if skipped == len(session.rounds):
        print("没有可比对的决策（会话里没有记录 decision）")
        return 1
    print(f"PASS：{len(session.rounds) - skipped} 轮一致（跳过 {skipped} 轮）")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="回放一局 BidKing 会话，复算每轮出价")
    parser.add_argument("session_dir", help="会话目录，例如 data/bidking/live/20261022_101500")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = parser.parse_args(argv)

    session_dir = Path(args.session_dir)
    if not session_dir.exists():
        print(f"会话目录不存在: {session_dir}")
        return 2

    if not args.json:
        return replay(session_dir)

    session = read_session(session_dir)
    strategy = session.meta.strategy or "fixed"
    params = session.meta.strategy_param or {}
    rows = []
    for observation in session.rounds:
        decision = decide(observation, strategy, params)
        rows.append(
            {
                "round": observation.round,
                "valuation": observation.valuation,
                "last_bid": observation.last_bid,
                "live": observation.decision,
                "replay": decision.amount,
                "match": observation.decision is None
                or observation.decision == decision.amount,
            }
        )
    ok = all(row["match"] for row in rows) and bool(rows)
    print(json.dumps({"ok": ok, "rows": rows}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
