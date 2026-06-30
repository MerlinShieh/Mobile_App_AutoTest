"""
核心编排层包 —— 任务级状态管理与单步执行引擎。

包含三个核心模块：
- TaskOrchestrator：负责任务生命周期编排、死循环检测。
- StepRunner：负责单步执行的完整闭环（感知 -> 弹窗 -> LLM -> 执行 -> 验证）。
- TaskContext：任务上下文数据，已在 models/task.py 中定义，此处做统一重导出。
"""

from ..models.task import StepRecord, TaskContext
from .orchestrator import TaskOrchestrator
from .step_runner import StepRunner

__all__ = [
    "TaskOrchestrator",
    "StepRunner",
    "TaskContext",
    "StepRecord",
]
