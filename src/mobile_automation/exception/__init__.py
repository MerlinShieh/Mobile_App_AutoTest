"""
异常处理包。

定义框架的自定义异常体系和重试策略。
所有模块抛出的业务异常应继承自 MobileAutomationError。
"""

from .exceptions import (
    MobileAutomationError,
    DeviceConnectionError,
    PerceptionError,
    LLMServiceError,
    ActionExecutionError,
    LoopDetectedError,
    TimeoutError,
)
from .retry_policy import retry

__all__ = [
    "MobileAutomationError",
    "DeviceConnectionError",
    "PerceptionError",
    "LLMServiceError",
    "ActionExecutionError",
    "LoopDetectedError",
    "TimeoutError",
    "retry",
]
