"""
截图获取与处理模块 —— ScreenCapture。

负责从设备获取屏幕截图，提供 uiautomator2 优先、ADB fallback
的双通道截图策略，支持缩放、压缩和 Base64 编码。
"""

import io
import time
from typing import Optional

from PIL import Image

from ..config import settings
from ..device.device_manager import DeviceManager
from ..logger import get_logger
from .image_util import compress_image, encode_base64

logger = get_logger(__name__)


class ScreenCapture:
    """
    截图获取与处理组件。

    优先使用 uiautomator2 截图（JPEG 格式），若 u2 不可用则
    fallback 到 ADB screencap（PNG 格式）。截图后自动进行缩放
    和 JPEG 压缩以降低 Token 消耗。

    参数
    ----------
    device_manager : DeviceManager
        设备管理器实例，通过依赖注入传入。
    """

    def __init__(self, device_manager: DeviceManager) -> None:
        self._dm = device_manager
        logger.debug("ScreenCapture 初始化完成")

    def capture(self, max_size: Optional[int] = None) -> bytes:
        """
        截取当前设备屏幕并返回经过缩放压缩的图片字节数据。

        截图策略：优先使用 uiautomator2 截图（JPEG），
        若失败则 fallback 到 ADB screencap（PNG 转 JPEG）。

        参数
        ----------
        max_size : Optional[int]
            缩放后的最长边像素值。为 None 时使用配置中的
            execution.screenshot_max_size。

        返回
        -------
        bytes
            经过缩放和 JPEG 压缩的图片字节数据。
        """
        if max_size is None:
            max_size = settings.execution.screenshot_max_size

        quality = settings.execution.screenshot_quality
        raw_bytes: Optional[bytes] = None
        source: str = ""

        try:
            u2 = self._dm.get_u2()
            raw_bytes = u2.screenshot(quality=quality)
            source = "uiautomator2"
        except Exception as exc:
            logger.warning("uiautomator2 截图失败，尝试 ADB fallback: %s", exc)

        if raw_bytes is None:
            try:
                adb = self._dm.get_adb()
                raw_bytes = adb.screenshot()
                source = "ADB"
            except Exception as exc:
                logger.error("ADB 截图也失败: %s", exc)
                raise RuntimeError("所有截图方式均失败") from exc

        logger.debug("原始截图获取成功，来源: %s，大小: %d 字节", source, len(raw_bytes))

        try:
            img = Image.open(io.BytesIO(raw_bytes))
            compressed = compress_image(img, quality=quality, max_size=max_size)
            logger.debug("截图处理后大小: %d 字节", len(compressed))
            return compressed
        except Exception as exc:
            logger.error("截图后处理失败: %s", exc)
            return raw_bytes if raw_bytes else b""

    def capture_base64(self, max_size: Optional[int] = None) -> str:
        """
        截取屏幕并返回 Base64 编码的图片字符串。

        参数
        ----------
        max_size : Optional[int]
            缩放后的最长边像素值。

        返回
        -------
        str
            Base64 编码的 JPEG 图片字符串。
        """
        image_bytes = self.capture(max_size=max_size)
        return encode_base64(image_bytes)

    def capture_with_ui_tree(self, max_size: Optional[int] = None) -> "PerceptualResult":
        """
        同时获取截图和 UI 树，打包为 PerceptualResult 返回。

        这是感知层的核心接口，一次调用同时完成视觉通道和结构通道的感知。

        参数
        ----------
        max_size : Optional[int]
            截图缩放后的最长边像素值。

        返回
        -------
        PerceptualResult
            包含 Base64 截图、UI 树结构和时间戳的完整感知结果。
        """
        from ..models.perception import PerceptualResult
        from .ui_tree import UITreeExtractor

        screenshot_b64 = self.capture_base64(max_size)
        extractor = UITreeExtractor(self._dm)
        ui_tree = extractor.extract()
        result = PerceptualResult(
            screenshot_base64=screenshot_b64,
            screenshot_format="jpeg",
            ui_tree=ui_tree,
            timestamp_ms=int(time.time() * 1000),
        )
        logger.debug("capture_with_ui_tree 完成，截图 %d 字符，UI 树 %d 节点",
                     len(screenshot_b64), len(ui_tree.local_index))
        return result
