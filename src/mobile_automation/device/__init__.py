"""
设备管理层包。

提供设备连接的统一入口，包括 DeviceManager（单例管理器）、
U2Controller（uiautomator2 封装）和 ADBController（ADB fallback 实现）。
所有设备操作优先通过 uiautomator2 执行，ADB 作为后备方案。
"""

from .device_manager import DeviceManager, DeviceInfo
from .u2_controller import U2Controller
from .adb_controller import ADBController

__all__ = [
    "DeviceManager",
    "DeviceInfo",
    "U2Controller",
    "ADBController",
]
