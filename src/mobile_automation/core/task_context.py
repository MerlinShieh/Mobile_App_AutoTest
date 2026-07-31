"""
任务上下文 —— 对 models/task.py 中 TaskContext 和 StepRecord 的统一重导出。

核心编排层通过此模块引用任务上下文数据类型，
避免 core 包直接依赖 models.task 的内部细节，降低耦合。
"""

from ..logger import get_logger
from ..models.task import StepRecord, TaskContext

logger = get_logger(__name__)

logger.debug("core.task_context 已加载（重导出 models.task）")

__all__ = [
    "TaskContext",
    "StepRecord",
]
