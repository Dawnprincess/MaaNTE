# -*- coding: utf-8 -*-
"""
拍卖之王 - 采集时机（等到画面稳定）

只做一件事：对**调用方指定**的区域连续截图比较像素差异，连续静止够久就认为
「可以采了」。本模块**不知道 `roi` 是什么**——它只是像素，语义由调用方决定。

为什么它属于采集层而不是策略（见 design D12）：
「等信息出现」是一次采集时机决策，不是一次计算。披露动画何时播完由游戏决定，
它的失败模式是「等不到」，所以超时兜底落在这里；而策略是同步纯函数，没有
「算到一半」这种可被计时器打断的状态。

宁可「多等」也不要「误判稳定」——误判会读到旧值，多等的代价只是等待变长。
"""

import time
from typing import Callable, Optional

import numpy as np

from ...Common.utils import get_image
from utils.logger import logger

from ..utils import crop

# 单像素差异超过该值算「变了」（0-255）
CHANGE_THRESHOLD = 10
# 变化像素占比低于该值算「没变」（容忍鼠标指针之类的零星噪声）
CHANGE_RATIO = 0.001
# 两次截图的间隔
SETTLE_INTERVAL = 0.2


def wait_until_stable(
    controller,
    roi,
    settle_time: float,
    timeout: float,
    interval: float = SETTLE_INTERVAL,
    should_stop: Optional[Callable[[], bool]] = None,
) -> bool:
    """
    等 `roi` 区域连续静止 `settle_time` 秒。

    返回 True 表示等到了稳定；False 表示超时——**超时不是错误**，调用方照常
    继续（用当前画面采集与提取，读不到的字段按「未知」处理）。

    `should_stop` 用于长循环中响应任务停止信号；返回 True 时立即结束等待。
    """
    start = time.time()
    prev = None
    stable_since = None

    while time.time() - start < timeout:
        if should_stop is not None and should_stop():
            return False

        img = get_image(controller)
        if img is None:
            logger.warning("⚠️ 截图失败，跳过稳定等待")
            return False

        cur = crop(img, roi)
        if prev is not None and cur.shape == prev.shape:
            if _is_quiet(cur, prev):
                if stable_since is None:
                    stable_since = time.time()
                elif time.time() - stable_since >= settle_time:
                    logger.info("🖼️ 画面已稳定（等待 %.1fs）", time.time() - start)
                    return True
            else:
                stable_since = None

        prev = cur
        time.sleep(interval)

    logger.warning("⚠️ 等待画面稳定超时（%.1fs），按当前画面继续", timeout)
    return False


def _is_quiet(cur, prev) -> bool:
    """两帧的差异是否小到可认为「没变」"""
    try:
        diff = np.abs(cur.astype(np.int16) - prev.astype(np.int16))
        changed = float(np.count_nonzero(diff > CHANGE_THRESHOLD)) / diff.size
    except Exception:
        return False
    return changed <= CHANGE_RATIO
