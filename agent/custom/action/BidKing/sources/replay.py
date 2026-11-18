# -*- coding: utf-8 -*-
"""回放来源：从已保存的会话重建逐轮观测流。

本模块只在**顶层包**上下文使用（`tools/replay.py` 把 `BidKing/` 加入
`sys.path` 后 `import sources.replay`），因此直接导入 `core.*`。
实机来源不会 import 本模块；`sources/__init__.py` 也不得 import `sources.live`。
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator, Optional, Union

from core.contracts import Meta, Observation, Settlement
from core.session import read_session


class ReplaySource:
    """把一局会话包装成 `ObservationSource`。"""

    def __init__(self, session_dir: Union[Path, str]) -> None:
        self._session = read_session(session_dir)

    def meta(self) -> Meta:
        return self._session.meta

    def iter_rounds(self) -> Iterator[Observation]:
        yield from self._session.rounds

    def settlement(self) -> Optional[Settlement]:
        return self._session.settlement


__all__ = ["ReplaySource"]
