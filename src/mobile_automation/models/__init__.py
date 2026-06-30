"""
数据模型包。

定义框架核心数据结构，包括枚举类型、操作指令、感知数据、任务上下文等。
所有模块依赖的数据模型统一在此包中管理。
"""

from .enums import ActionType, StepStatus, TaskStatus, PopupType, PopupStrategy, LLMProvider, LLMRole
from .action import Action, ActionParams
from .perception import UINode, UITree, UISpatialIndex, PerceptualResult, PageChangeResult
from .task import StepRecord, TaskContext

__all__ = [
    "ActionType",
    "StepStatus",
    "TaskStatus",
    "PopupType",
    "PopupStrategy",
    "LLMProvider",
    "LLMRole",
    "Action",
    "ActionParams",
    "UINode",
    "UITree",
    "UISpatialIndex",
    "PerceptualResult",
    "PageChangeResult",
    "StepRecord",
    "TaskContext",
]
