"""
执行层包 —— 将 Action 指令转换为具体的设备操作。

包含动作分发器（ActionExecutor）以及点击、输入、滑动、等待
四类子执行器。每个执行器接收 Action 对象，通过 DeviceManager
调用 uiautomator2 或 ADB 完成操作。
"""

from .action_executor import ActionExecutor
from .click_executor import ClickExecutor
from .type_executor import TypeExecutor
from .swipe_executor import SwipeExecutor
from .wait_executor import WaitExecutor

__all__ = [
    "ActionExecutor",
    "ClickExecutor",
    "TypeExecutor",
    "SwipeExecutor",
    "WaitExecutor",
]
