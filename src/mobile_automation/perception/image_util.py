"""
图像工具模块。

提供图片压缩、Base64 编解码、缩放和对比度分析等图像处理工具函数。
所有函数为无状态的纯函数，便于单元测试和复用。
"""

import base64
import io
from typing import Optional, Tuple

from PIL import Image, ImageEnhance

from ..logger import get_logger

logger = get_logger(__name__)


def resize_image(
    image: Image.Image,
    max_size: int,
) -> Image.Image:
    """
    将图像按比例缩放到最长边不超过指定像素值。

    使用 LANCZOS 重采样算法保证缩放质量。

    参数
    ----------
    image : Image.Image
        PIL Image 对象。
    max_size : int
        缩放后的最长边像素值。

    返回
    -------
    Image.Image
        缩放后的 PIL Image 对象。
    """
    w, h = image.size
    if max(w, h) <= max_size:
        return image

    if w > h:
        new_w, new_h = max_size, int(h * max_size / w)
    else:
        new_h, new_w = max_size, int(w * max_size / h)

    resized = image.resize((new_w, new_h), Image.LANCZOS)
    logger.debug("图片缩放: %dx%d -> %dx%d", w, h, new_w, new_h)
    return resized


def compress_image(
    image: Image.Image,
    quality: int = 85,
    format: str = "JPEG",
    max_size: Optional[int] = None,
) -> bytes:
    """
    压缩图像并返回编码后的字节数据。

    支持先缩放再压缩，通过调节 quality 参数平衡图片质量与文件大小。

    参数
    ----------
    image : Image.Image
        PIL Image 对象。
    quality : int
        JPEG 压缩质量，1~100，默认 85。
    format : str
        输出图片格式，默认 "JPEG"。
    max_size : Optional[int]
        压缩前的最长边像素限制，为 None 时不缩放。

    返回
    -------
    bytes
        压缩后的图片字节数据。
    """
    if max_size is not None:
        image = resize_image(image, max_size)

    buf = io.BytesIO()
    try:
        if format.upper() == "JPEG" and image.mode in ("RGBA", "P"):
            image = image.convert("RGB")
        image.save(buf, format=format.upper(), quality=quality)
        data = buf.getvalue()
        logger.debug("图片压缩: 格式=%s 质量=%d 大小=%d 字节", format, quality, len(data))
        return data
    except Exception as exc:
        logger.error("图片压缩失败: %s", exc)
        raise


def encode_base64(image_bytes: bytes) -> str:
    """
    将图片字节数据编码为 Base64 字符串。

    参数
    ----------
    image_bytes : bytes
        原始图片字节数据。

    返回
    -------
    str
        Base64 编码的 ASCII 字符串。
    """
    encoded = base64.b64encode(image_bytes).decode("ascii")
    logger.debug("Base64 编码完成，输入 %d 字节 -> 输出 %d 字符", len(image_bytes), len(encoded))
    return encoded


def decode_base64(encoded: str) -> bytes:
    """
    将 Base64 字符串解码为原始图片字节数据。

    参数
    ----------
    encoded : str
        Base64 编码的图片字符串。

    返回
    -------
    bytes
        解码后的原始图片字节数据。

    异常
    ------
    ValueError
        Base64 字符串格式无效时抛出。
    """
    try:
        decoded = base64.b64decode(encoded)
        logger.debug("Base64 解码完成，输入 %d 字符 -> 输出 %d 字节", len(encoded), len(decoded))
        return decoded
    except Exception as exc:
        logger.error("Base64 解码失败: %s", exc)
        raise ValueError(f"Base64 解码失败: {exc}") from exc


def estimate_image_tokens(base64_str: str) -> int:
    """
    估算 Base64 编码的图片在 LLM 上下文中消耗的 Token 数。

    估算逻辑：Base64 原始字节数的一半作为 Token 近似值。

    参数
    ----------
    base64_str : str
        Base64 编码的图片字符串。

    返回
    -------
    int
        估计的 Token 消耗数。
    """
    raw_bytes = len(base64_str) * 3 / 4
    tokens = int(raw_bytes / 2)
    logger.debug("图片 Token 估算: %d Token", tokens)
    return tokens


def analyze_contrast(image: Image.Image) -> float:
    """
    分析图像的整体对比度。

    使用 PIL 的 ImageEnhance 统计对比度指标。返回值越大表示对比度越高，
    可用于判断截图是否过亮或过暗。

    参数
    ----------
    image : Image.Image
        PIL Image 对象。

    返回
    -------
    float
        对比度评分，1.0 表示原始对比度，大于 1.0 表示对比度增强。
    """
    try:
        gray = image.convert("L")
        enhancer = ImageEnhance.Contrast(gray)
        enhanced = enhancer.enhance(1.0)
        import numpy as np
        arr = np.array(enhanced, dtype=np.float32)
        contrast = float(arr.std())
        logger.debug("图像对比度分析完成: std=%.2f", contrast)
        return contrast
    except ImportError:
        logger.warning("numpy 未安装，对比度分析返回 0")
        return 0.0
    except Exception as exc:
        logger.error("对比度分析异常: %s", exc)
        return 0.0
