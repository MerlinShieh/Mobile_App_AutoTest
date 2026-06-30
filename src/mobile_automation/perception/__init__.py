"""
感知层包。

提供屏幕截图获取、UI 树解析（三份本地数据）、页面变化检测和
图像工具等屏幕感知能力。所有组件通过依赖注入接收 DeviceManager。
"""

from .image_util import (
    compress_image,
    encode_base64,
    decode_base64,
    resize_image,
    estimate_image_tokens,
    analyze_contrast,
)
from .page_diff import PageChangeDetector
from .screen_capture import ScreenCapture
from .ui_tree import UITreeExtractor

__all__ = [
    "ScreenCapture",
    "UITreeExtractor",
    "PageChangeDetector",
    "compress_image",
    "encode_base64",
    "decode_base64",
    "resize_image",
    "estimate_image_tokens",
    "analyze_contrast",
]
