#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""分层守卫：core / replay / 实时纯感知不得依赖框架。

检查：

1. `core/**`：禁止导入 `maa` / `custom` / `utils` / `sources`，也禁止跳出
   `core` 的三级及以上相对导入。
2. `sources/replay.py`：禁止导入 `maa` / `custom` / `utils` / `sources.live`。
3. `sources/__init__.py`：禁止导入 `sources.live`。
4. `sources/live/perceive/__init__.py` 与 `warehouse/**`：纯感知库，禁止
   `maa` / `custom` / `utils` 以及 `..fields`/`..observation`/`..actions`，
   保证离线 CLI/测试 import warehouse 时不加载框架。

运行时检查两个子进程：
  - 导入 `core` + `sources.replay`，断言没有 `maa/custom/utils/sources.live`；
  - 导入 `sources.live.perceive.warehouse`，断言没有 `maa/custom/utils`，
    也没有加载 `fields`/`observation`。

用法：python agent/custom/action/BidKing/tools/check_layering.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

BIDKING_DIR = Path(__file__).resolve().parents[1]
CORE_DIR = BIDKING_DIR / "core"
SOURCES_DIR = BIDKING_DIR / "sources"
REPLAY_PATH = SOURCES_DIR / "replay.py"
SOURCES_INIT = SOURCES_DIR / "__init__.py"
PERCEIVE_DIR = SOURCES_DIR / "live" / "perceive"
PERCEIVE_INIT = PERCEIVE_DIR / "__init__.py"
WAREHOUSE_DIR = PERCEIVE_DIR / "warehouse"

_TOP_LEVEL = re.compile(r"^\s*(?:from|import)\s+(maa|custom|utils)\b")
_SOURCES_IMPORT = re.compile(r"^\s*(?:from|import)\s+sources\b")
_RELATIVE_OUT = re.compile(r"^\s*from\s+\.{3,}[A-Za-z_]")
_LIVE_IMPORT = re.compile(
    r"^\s*(?:from|import)\s+(?:sources\.)?live\b|^\s*from\s+\.{1,2}live\b"
)
_LIVE_SIBLING = re.compile(r"^\s*from\s+\.{2,}(?:fields|observation|actions)\b")
_BANNED_MODULES = ("maa", "custom", "utils", "sources.live")
_PURE_BANNED_MODULES = ("maa", "custom", "utils")


def _iter_import_lines(path: Path):
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        yield lineno, line


def _scan_core() -> list[str]:
    problems: list[str] = []
    for path in sorted(CORE_DIR.rglob("*.py")):
        for lineno, line in _iter_import_lines(path):
            if _TOP_LEVEL.match(line) or _SOURCES_IMPORT.match(line):
                problems.append(f"{path.relative_to(BIDKING_DIR)}:{lineno}: {line.strip()}")
            elif _RELATIVE_OUT.match(line):
                problems.append(f"{path.relative_to(BIDKING_DIR)}:{lineno}: {line.strip()}")
    return problems


def _scan_replay() -> list[str]:
    problems: list[str] = []
    if not REPLAY_PATH.exists():
        return [f"缺少 {REPLAY_PATH.relative_to(BIDKING_DIR)}"]
    for lineno, line in _iter_import_lines(REPLAY_PATH):
        if _TOP_LEVEL.match(line) or _LIVE_IMPORT.match(line):
            problems.append(
                f"{REPLAY_PATH.relative_to(BIDKING_DIR)}:{lineno}: {line.strip()}"
            )
    return problems


def _scan_sources_init() -> list[str]:
    problems: list[str] = []
    if not SOURCES_INIT.exists():
        return [f"缺少 {SOURCES_INIT.relative_to(BIDKING_DIR)}"]
    for lineno, line in _iter_import_lines(SOURCES_INIT):
        if _LIVE_IMPORT.match(line):
            problems.append(
                f"{SOURCES_INIT.relative_to(BIDKING_DIR)}:{lineno}: {line.strip()}"
            )
    return problems


def _scan_perceive_init() -> list[str]:
    problems: list[str] = []
    if not PERCEIVE_INIT.exists():
        return [f"缺少 {PERCEIVE_INIT.relative_to(BIDKING_DIR)}"]
    for lineno, line in _iter_import_lines(PERCEIVE_INIT):
        if _TOP_LEVEL.match(line):
            problems.append(
                f"{PERCEIVE_INIT.relative_to(BIDKING_DIR)}:{lineno}: {line.strip()}"
            )
    return problems


def _scan_warehouse() -> list[str]:
    problems: list[str] = []
    if not WAREHOUSE_DIR.is_dir():
        return [f"缺少 {WAREHOUSE_DIR.relative_to(BIDKING_DIR)}"]
    for path in sorted(WAREHOUSE_DIR.rglob("*.py")):
        for lineno, line in _iter_import_lines(path):
            if (
                _TOP_LEVEL.match(line)
                or _SOURCES_IMPORT.match(line)
                or _LIVE_SIBLING.match(line)
            ):
                problems.append(
                    f"{path.relative_to(BIDKING_DIR)}:{lineno}: {line.strip()}"
                )
    return problems


def runtime_check_replay() -> int:
    code = (
        "import sys; "
        f"sys.path.insert(0, {str(BIDKING_DIR)!r}); "
        "import core.contracts, core.catalog, core.session, core.decide, sources.replay; "
        f"bad = [m for m in {_BANNED_MODULES!r} if m in sys.modules]; "
        "print('replay runtime import:', 'OK' if not bad else 'LEAKED ' + ','.join(bad)); "
        "sys.exit(1 if bad else 0)"
    )
    # 不捕获输出：子进程直接继承 stdout，避免依赖管道
    return subprocess.run([sys.executable, "-c", code], cwd=str(BIDKING_DIR)).returncode


def runtime_check_warehouse() -> int:
    code = (
        "import sys; "
        f"sys.path.insert(0, {str(BIDKING_DIR)!r}); "
        "import sources.live.perceive.warehouse; "
        f"bad = [m for m in {_PURE_BANNED_MODULES!r} if m in sys.modules]; "
        "loaded = [m for m in ('sources.live.perceive.fields', "
        "'sources.live.perceive.observation') if m in sys.modules]; "
        "print('warehouse runtime import:', "
        "'OK' if not bad and not loaded else 'LEAKED ' + ','.join(bad + loaded)); "
        "sys.exit(1 if bad or loaded else 0)"
    )
    return subprocess.run([sys.executable, "-c", code], cwd=str(BIDKING_DIR)).returncode


def main() -> int:
    problems = (
        _scan_core()
        + _scan_replay()
        + _scan_sources_init()
        + _scan_perceive_init()
        + _scan_warehouse()
    )
    if problems:
        print("静态检查失败：出现禁止的导入")
        for problem in problems:
            print("  " + problem)
    else:
        print("静态检查: OK（core/replay/warehouse 分层无违规导入）")

    replay_code = runtime_check_replay()
    warehouse_code = runtime_check_warehouse()
    if replay_code != 0:
        print("运行时检查失败：导入 core/replay 时加载了被禁止的模块")
    if warehouse_code != 0:
        print("运行时检查失败：导入 warehouse 时加载了 Maa/utils/字段感知")
    if replay_code == 0 and warehouse_code == 0:
        print("运行时检查: OK")

    return 0 if not problems and replay_code == 0 and warehouse_code == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
