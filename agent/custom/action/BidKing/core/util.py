# -*- coding: utf-8 -*-
"""核心层的最小工具：不依赖框架、不依赖 agent 运行时。"""

from __future__ import annotations

import re
from typing import Optional


def to_positive_int(value) -> Optional[int]:
    """把配置值转成正整数；非法（非数字、0、负数）返回 None。"""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


# 回合数：整句匹配「竞拍第x回合」。
# 前后允许非数字字符（OCR 可能带出「竞拍」这类固定前缀），但**不允许数字**
# 混进来——这样「共12件藏品」之类的文本不会误命中。
_ROUND_RE = re.compile(r"\D*第\s*(\d+)\s*回合\D*")

# 倒计时：mm:ss（容忍全角冒号与空格）
_COUNTDOWN_RE = re.compile(r"\D*(\d{1,2})\s*[:：]\s*(\d{1,2})\D*")


def parse_round(text: Optional[str]) -> Optional[int]:
    """整串匹配「第x回合」句式；不匹配即失败，不截取其中数字"""
    if not text:
        return None
    matched = _ROUND_RE.fullmatch(text.strip())
    if not matched:
        return None
    try:
        return int(matched.group(1))
    except ValueError:
        return None


def parse_countdown(text: Optional[str]) -> Optional[int]:
    """把 `mm:ss` 解析为总秒数；格式不符或秒数越界即失败"""
    if not text:
        return None
    matched = _COUNTDOWN_RE.fullmatch(text.strip())
    if not matched:
        return None
    try:
        minutes = int(matched.group(1))
        seconds = int(matched.group(2))
    except ValueError:
        return None
    if seconds > 59:
        return None
    return minutes * 60 + seconds


# 全角数字与常见全角符号 -> 半角（OCR 可能返回全角）
_FULLWIDTH = {ord("０") + i: ord("0") + i for i in range(10)}
_FULLWIDTH.update({ord("，"): ord(","), ord("．"): ord("."), ord("　"): ord(" ")})

# 价格两端可能出现的噪声字符
_TRIM_CHARS = "¥$￥|:：。. "

# 只接受两种整串写法：
#   1) 千位分隔写法：1,222,418 / 14.346（OCR 把分隔符读成小数点）
#   2) 纯数字：0 / 91 / 839（小额估价游戏不加分隔符）
_THOUSANDS_RE = re.compile(r"\d{1,3}(?:[,.]\d{3})+")
_PLAIN_RE = re.compile(r"\d{1,6}")


def extract_price(text: Optional[str]) -> Optional[int]:
    """
    从 OCR 文本中解析价格；不符合写法时返回 None（不做猜测）。

    整串匹配很关键：`可输入范围0~2,524,741`、`1.23M` 这类文本必须失败，
    否则会把提示文字或紧凑写法读成余额/错误金额。
    """
    if not text:
        return None

    cleaned = text.translate(_FULLWIDTH).strip(_TRIM_CHARS).strip()

    if _THOUSANDS_RE.fullmatch(cleaned):
        return int(cleaned.replace(",", "").replace(".", ""))
    if _PLAIN_RE.fullmatch(cleaned):
        return int(cleaned)
    return None
