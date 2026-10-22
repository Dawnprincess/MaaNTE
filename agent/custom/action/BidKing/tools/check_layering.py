#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""分层守卫：`domain/` 不得依赖自动化框架或 agent 运行时。

两层检查：

1. 静态：扫描 `domain/**.py` 的 import 行，禁止 `maa`、`custom`、`utils`、
   `perceive`、`capture`，以及跳出 `domain` 的相对导入（三个及以上点）。
2. 运行时：在子进程里以顶层包方式导入 `domain`（与回放相同的导入方式），
   断言 `maa` / `custom` / `utils` 没有被加载。

用法：python agent/custom/action/BidKing/tools/check_layering.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

BIDKING_DIR = Path(__file__).resolve().parents[1]
DOMAIN_DIR = BIDKING_DIR / "domain"

_TOP_LEVEL = re.compile(r"^\s*(?:from|import)\s+(maa|custom|utils|perceive|capture)\b")
_RELATIVE_OUT = re.compile(r"^\s*from\s+(?:\.{2}(?:perceive|capture|utils)\b|\.{3,}[A-Za-z_])")
_BANNED_MODULES = ("maa", "custom", "utils")


def static_scan() -> list[str]:
    problems: list[str] = []
    for path in sorted(DOMAIN_DIR.rglob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _TOP_LEVEL.match(line) or _RELATIVE_OUT.match(line):
                problems.append(f"{path.relative_to(BIDKING_DIR)}:{lineno}: {line.strip()}")
    return problems


def runtime_check() -> int:
    code = (
        "import sys; "
        f"sys.path.insert(0, {str(BIDKING_DIR)!r}); "
        "import domain.contracts, domain.catalog, domain.session, domain.decide; "
        f"bad = [m for m in {_BANNED_MODULES!r} if m in sys.modules]; "
        "print('runtime import:', 'OK' if not bad else 'LEAKED ' + ','.join(bad)); "
        "sys.exit(1 if bad else 0)"
    )
    # 不捕获输出：子进程直接继承 stdout，避免依赖管道
    return subprocess.run([sys.executable, "-c", code], cwd=str(BIDKING_DIR)).returncode


def main() -> int:
    problems = static_scan()
    if problems:
        print("静态检查失败：domain/ 出现禁止的导入")
        for problem in problems:
            print("  " + problem)
    else:
        print("静态检查: OK（domain/ 无框架/agent 运行时导入）")

    code = runtime_check()
    if code != 0:
        print("运行时检查失败：导入 domain 时加载了被禁止的模块")
    else:
        print("运行时检查: OK")

    return 0 if not problems and code == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
