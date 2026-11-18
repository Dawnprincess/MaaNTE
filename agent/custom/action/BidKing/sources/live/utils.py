"""
拍卖之王 - 实机来源的小工具

入口动作（place_bid）与感知层用到的东西放这里：
  - OCR 读取指定区域（含多级兜底提取）
  - 图像裁剪

价格文本解析与配置值转换是纯函数，放在 `core.util`，不要在实机层重复实现。
"""

from typing import Optional

from maa.context import Context
from maa.pipeline import JRecognitionType, JOCR

from ....Common.utils import get_image
from utils.logger import logger


def crop(img, roi):
    """按 [x, y, w, h] 裁剪图像，越界自动收敛"""
    x, y, w, h = [int(v) for v in roi]
    height, width = img.shape[:2]
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(width, x + w), min(height, y + h)
    if x2 <= x1 or y2 <= y1:
        return img
    return img[y1:y2, x1:x2]


def ocr_text(context: Context, img, roi, debug: bool = False) -> Optional[str]:
    """对给定图像做 OCR 并提取文本（沿用项目统一调用方式）"""
    try:
        detail = context.run_recognition_direct(
            JRecognitionType.OCR, JOCR(roi=roi), img
        )
    except Exception as e:
        logger.error(f"❌ OCR 调用异常: {e}")
        return None

    if detail is None:
        logger.warning("⚠️ OCR 返回 None")
        return None

    if debug:
        logger.debug(f"OCR detail 类型={type(detail)}, 内容={detail}")

    best = getattr(detail, "best_result", None)
    if best is not None:
        text = getattr(best, "text", None)
        if text:
            return text.strip()

    all_results = getattr(detail, "all_results", None)
    if all_results:
        joined = " ".join(r.text for r in all_results if getattr(r, "text", None))
        if joined.strip():
            return joined.strip()

    if isinstance(detail, str):
        return detail.strip()

    text = getattr(detail, "text", None)
    if text:
        return text.strip()

    logger.warning(f"⚠️ 无法从 OCR detail 提取文本，类型={type(detail)}")
    return None


def read_region_text(
    context: Context, controller, roi, debug: bool = False
) -> Optional[str]:
    """截图并 OCR 指定区域"""
    img = get_image(controller)
    if img is None:
        logger.error("❌ 截图失败")
        return None
    return ocr_text(context, img, roi, debug)
