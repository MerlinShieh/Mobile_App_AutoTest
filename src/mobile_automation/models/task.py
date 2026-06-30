"""
任务与步骤上下文数据模型。

定义任务生命周期中使用的数据结构，包括单步执行记录（StepRecord）
和任务级上下文（TaskContext），在 Orchestrator 中维护。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .enums import TaskStatus, StepStatus
from .action import Action
from ..logger import get_logger

logger = get_logger(__name__)


@dataclass
class StepRecord:
    """
    单步执行记录。

    记录一次操作从开始到结束的完整信息，包括操作内容、状态变更、
    执行耗时、错误信息、重试次数和 Token 消耗等。

    参数
    ----------
    step_index : int
        当前步骤在任务中的序号，从 1 开始。
    action : Action
        本步骤执行的操作指令。
    status : StepStatus
        步骤当前状态。
    started_at : Optional[datetime]
        步骤开始执行的时间。
    finished_at : Optional[datetime]
        步骤执行完成的时间。
    error_message : str
        执行失败时的错误描述。
    retry_count : int
        本步骤已重试的次数。
    screenshot_path : str
        本步骤截图的本地存储路径。
    page_summary : str
        执行后页面的结构化摘要文本。
    llm_response : str
        LLM 返回的原始响应文本。
    token_used : int
        本步骤消耗的 Token 数量。
    """
    step_index: int
    action: Action
    status: StepStatus
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error_message: str = ""
    retry_count: int = 0
    screenshot_path: str = ""
    page_summary: str = ""
    llm_response: str = ""
    token_used: int = 0

    def duration_ms(self) -> int:
        """
        计算本步骤的执行耗时。

        需要 started_at 和 finished_at 均不为空。

        返回
        -------
        int
            执行耗时（毫秒），无法计算时返回 0。
        """
        if self.started_at and self.finished_at:
            return int((self.finished_at - self.started_at).total_seconds() * 1000)
        return 0

    def is_success(self) -> bool:
        """
        快捷判断本步骤是否执行成功。

        返回
        -------
        bool
            状态是否为 SUCCESS。
        """
        return self.status == StepStatus.SUCCESS


@dataclass
class TaskContext:
    """
    任务级上下文，在 TaskOrchestrator 中维护整个任务的生命周期状态。

    记录用户目标、执行进度、步骤历史、Token 消耗、设备信息和时间等。

    参数
    ----------
    task_id : str
        任务唯一标识符。
    user_goal : str
        用户输入的原始任务描述。
    status : TaskStatus
        任务当前状态。
    current_step : int
        当前已完成的步骤序号。
    max_steps : int
        任务允许的最大执行步数。
    steps : list[StepRecord]
        已执行的所有步骤记录。
    page_history : list[str]
        历史页面的结构化摘要列表，用于 LLM 上下文。
    total_tokens_used : int
        已消耗的总 Token 数。
    estimated_remaining : int
        估算的剩余可用 Token 数。
    max_context_tokens : int
        当前 LLM 的最大上下文窗口大小。
    device_id : str
        执行任务的设备序列号。
    llm_provider : str
        正在使用的 LLM 提供商名称。
    created_at : datetime
        任务创建时间。
    """
    task_id: str
    user_goal: str
    status: TaskStatus = TaskStatus.RUNNING
    current_step: int = 0
    max_steps: int = 30
    steps: list[StepRecord] = field(default_factory=list)
    page_history: list[str] = field(default_factory=list)
    total_tokens_used: int = 0
    estimated_remaining: int = 0
    max_context_tokens: int = 32000
    device_id: str = ""
    llm_provider: str = "qwen"
    created_at: datetime = field(default_factory=datetime.now)

    def add_step(self, record: StepRecord) -> None:
        """
        添加一条步骤记录到任务历史中。

        自动更新 current_step 和 total_tokens_used。

        参数
        ----------
        record : StepRecord
            要添加的步骤记录。
        """
        self.steps.append(record)
        self.current_step = record.step_index
        self.total_tokens_used += record.token_used
        logger.debug("任务 %s 步骤 %d 完成，当前 Token 消耗: %d",
                      self.task_id, record.step_index, self.total_tokens_used)

    def is_completed(self) -> bool:
        """
        判断任务是否已经终止（完成 / 失败 / 中止）。

        返回
        -------
        bool
            任务是否已终止。
        """
        return self.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.ABORTED)

    def is_timeout(self, max_duration_seconds: int = 300) -> bool:
        """
        判断任务是否已超时。

        参数
        ----------
        max_duration_seconds : int
            最大允许持续时间（秒），默认 300 秒（5 分钟）。

        返回
        -------
        bool
            是否已超时。
        """
        elapsed = (datetime.now() - self.created_at).total_seconds()
        return elapsed > max_duration_seconds

    def get_last_step(self) -> Optional[StepRecord]:
        """
        获取最后一条步骤记录。

        返回
        -------
        Optional[StepRecord]
            最后一步的记录，无步骤时返回 None。
        """
        return self.steps[-1] if self.steps else None

    def get_success_rate(self) -> float:
        """
        计算当前任务的步骤成功率。

        返回
        -------
        float
            成功步骤占比，0.0~1.0。无步骤时返回 0.0。
        """
        if not self.steps:
            return 0.0
        successes = sum(1 for s in self.steps if s.is_success())
        return successes / len(self.steps)
