"""
轻量图像分类器存根 —— 为弹窗图像分类提供扩展点。

当前为框架预留接口，后续可集成 MobileNet / ResNet 等轻量模型
对弹窗截图做二次验证。当前实现返回默认的 UNKNOWN 结果。
"""

from typing import Optional

from ..logger import get_logger
from ..models.enums import PopupType

logger = get_logger(__name__)


class PopupClassifier:
    """
    轻量图像分类器存根。

    预留的图像分类接口，用于对弹窗截图做二次验证。
    当前实现返回 UNKNOWN，集成具体模型后可通过 classify 方法返回
    PopupType 和置信度。

    使用方式（后续集成）
    --------
    >>> classifier = PopupClassifier()
    >>> popup_type, confidence = classifier.classify(screenshot_bytes)
    """

    def __init__(self) -> None:
        """初始化 PopupClassifier。"""
        logger.info("PopupClassifier 初始化（存根模式）")

    def classify(self, screenshot_bytes: Optional[bytes] = None) -> tuple[PopupType, float]:
        """
        对弹窗截图进行分类。

        当前存根实现返回 PopupType.UNKNOWN 和置信度 0.0。
        后续集成 MobieNet / ResNet 等模型后可替换实现。

        参数
        ----------
        screenshot_bytes : Optional[bytes]
            弹窗区域的截图字节数据。

        返回
        -------
        tuple[PopupType, float]
            (弹窗类型, 置信度)，当前返回 (UNKNOWN, 0.0)。
        """
        logger.debug("PopupClassifier.classify 被调用（存根）: screenshot_bytes=%s",
                     f"{len(screenshot_bytes)} bytes" if screenshot_bytes else "None")
        return PopupType.UNKNOWN, 0.0

    def is_available(self) -> bool:
        """
        检查分类器是否可用。

        当前存根实现始终返回 False。
        集成具体模型后应返回模型加载状态。

        返回
        -------
        bool
            当前始终返回 False。
        """
        return False
