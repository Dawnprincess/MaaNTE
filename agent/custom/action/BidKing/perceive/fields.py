# -*- coding: utf-8 -*-
"""
拍卖之王 - 字段提取

每个字段一个函数，签名统一为 `read_xxx(context, frame) -> Optional[int]`，
失败一律返回 `None`——**绝不回落到猜测值**。使用方各自走兜底分支，这与既有
「价格解析整串匹配、不做猜测」的判例一致。

关于「纯函数」的确切含义（见 openspec design D4/D12）：
  - MUST NOT 截图、MUST NOT 点击、MUST NOT 读任务状态 —— 因此可以对**历史
    帧**重复执行：提取逻辑改了，重放旧录像即可验证，不必重打对局。
  - `context` 只作为**识别引擎的句柄**传入（`run_recognition_direct`），不是
    状态来源。它是依赖，不是隐藏状态。
  - 唯一的外部依赖是 OCR 引擎本身；给定同一帧，结果应当一致。

识别区域一律从 `..layout` 取，不走参数——理由是区域由游戏界面布局决定、
不是用户可调参数，而选项覆盖可能整块替换参数并导致区域丢失。
"""

import re
from typing import Optional

from maa.context import Context

from ..layout import BALANCE_ROI, COUNTDOWN_ROI, PRICE_ROI, ROUND_ROI
from ..utils import extract_price, ocr_text

# 回合数：整句匹配「竞拍第x回合」。
# 前后允许非数字字符（OCR 可能带出「竞拍」这类固定前缀），但**不允许数字**
# 混进来——这样「共12件藏品」之类的文本不会误命中。
_ROUND_RE = re.compile(r"\D*第\s*(\d+)\s*回合\D*")

# 倒计时：mm:ss（容忍全角冒号与空格）
_COUNTDOWN_RE = re.compile(r"\D*(\d{1,2})\s*[:：]\s*(\d{1,2})\D*")


# ============ 字段读取 ============


def read_round(context: Context, frame, roi=None) -> Optional[int]:
    """当前回合数；读不到返回 None"""
    return parse_round(ocr_text(context, frame, roi or ROUND_ROI))


def read_countdown(context: Context, frame, roi=None) -> Optional[int]:
    """本轮剩余秒数；读不到返回 None"""
    return parse_countdown(ocr_text(context, frame, roi or COUNTDOWN_ROI))


def read_balance(context: Context, frame, roi=None) -> Optional[int]:
    """自身资产；读不到返回 None"""
    return extract_price(ocr_text(context, frame, roi or BALANCE_ROI))


def read_valuation(context: Context, frame, roi=None) -> Optional[int]:
    """系统估价；读不到返回 None"""
    return extract_price(ocr_text(context, frame, roi or PRICE_ROI))


# ============ 文本解析（纯函数，可单独测） ============


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
