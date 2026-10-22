# -*- coding: utf-8 -*-
"""核心层的最小工具：不依赖框架、不依赖 agent 运行时。"""

from __future__ import annotations

from typing import Optional


def to_positive_int(value) -> Optional[int]:
    """把配置值转成正整数；非法（非数字、0、负数）返回 None。"""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None
