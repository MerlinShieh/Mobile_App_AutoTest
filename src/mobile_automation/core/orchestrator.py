"""
任务编排器 —— TaskOrchestrator。

负责任务的完整生命周期管理，包括：
  - 任务创建与状态管理
  - 步骤循环驱动（调用 StepRunner 逐步执行）
  - 死循环检测（连续相同操作超过阈值时中止）
  - 超时检测（任务总耗时超过限制时失败）
  - Token 预算全局管理

执行循环：
  while not done:
    1. 检查超时
    2. StepRunner.run_step()
    3. 记录步骤
    4. 死循环检测
    5. 更新状态
"""

import uuid
from typing import Optional

from ..config import settings
from ..llm.token_budget import TokenBudgetManager
from ..logger import get_logger
from ..models.action import Action
from ..models.enums import ActionType, StepStatus, TaskStatus
from ..models.task import TaskContext
from ..reporting.archiver import DataArchiver
from ..reporting.report_generator import ReportGenerator
from .step_runner import StepRunner

logger = get_logger(__name__)


class TaskOrchestrator:
    """
    任务编排器。

    管理单个任务的完整生命周期，从创建到完成/失败/中止。
    通过 StepRunner 驱动每一步的执行，并监控死循环和超时。

    参数
    ----------
    step_runner : StepRunner
        单步执行引擎实例。
    token_budget : TokenBudgetManager
        Token 预算管理器实例。
    """

    def __init__(
        self,
        step_runner: StepRunner,
        token_budget: TokenBudgetManager,
    ) -> None:
        """
        初始化 TaskOrchestrator。

        参数
        ----------
        step_runner : StepRunner
            单步执行引擎实例。
        token_budget : TokenBudgetManager
            Token 预算管理器实例。
        """
        self._step_runner: StepRunner = step_runner
        self._token_budget: TokenBudgetManager = token_budget
        self._last_actions: list[str] = []
        self._same_action_count: int = 0
        logger.debug("TaskOrchestrator 初始化完成")

    def execute_task(
        self,
        user_goal: str,
        max_steps: Optional[int] = None,
    ) -> TaskContext:
        """
        执行一个完整的自动化任务。

        流程：
          1. 创建 TaskContext，初始化死循环检测状态。
          2. 创建 DataArchiver 用于记录每一步的截图、XML 和 LLM 交互。
          3. 循环执行每一步，直到任务完成、失败或中止。
          4. 完成后生成 Markdown 流程报告。
          5. 返回最终的 TaskContext。

        参数
        ----------
        user_goal : str
            用户输入的原始任务描述。
        max_steps : Optional[int]
            任务允许的最大步数，为 None 时从配置读取。

        返回
        -------
        TaskContext
            包含所有步骤记录和最终状态的任务上下文。
        """
        context: TaskContext = TaskContext(
            task_id=str(uuid.uuid4())[:8],
            user_goal=user_goal,
            max_steps=max_steps or settings.execution.max_steps_per_task,
        )

        self._last_actions = []
        self._same_action_count = 0

        # 重置 Token 预算，绑定到 StepRunner
        self._token_budget.reset()
        self._step_runner.set_token_budget(self._token_budget)

        archiver: DataArchiver = DataArchiver(task_id=context.task_id)
        self._step_runner.set_archiver(archiver)

        logger.info("任务 %s 开始执行: user_goal=%s, max_steps=%d",
                     context.task_id, user_goal, context.max_steps)

        while not context.is_completed() and context.current_step < context.max_steps:
            if self._check_timeout(context):
                context.status = TaskStatus.FAILED
                logger.warning("任务 %s 超时，已执行 %d 步", context.task_id, context.current_step)
                break

            step_index: int = context.current_step + 1
            logger.info("任务 %s 执行步骤 %d/%d", context.task_id, step_index, context.max_steps)

            try:
                record = self._step_runner.run_step(step_index, context)
                context.add_step(record)

                # ---- 特殊动作处理（在 is_success 分支之前） ----
                if record.action.action_type == ActionType.TERMINATE:
                    context.status = TaskStatus.COMPLETED
                    logger.info("任务 %s 收到 terminate 信号，用户目标已达成，终止执行",
                                context.task_id)
                    break

                if record.action.action_type == ActionType.VERIFY:
                    matched = record.action.params.match
                    if matched:
                        context.status = TaskStatus.COMPLETED
                        logger.info("任务 %s 验证通过: 信息匹配（match=true）",
                                    context.task_id)
                    else:
                        record.status = StepStatus.FAILED
                        context.status = TaskStatus.FAILED
                        logger.warning("任务 %s 验证失败: 信息不匹配（match=false），reason=%s",
                                       context.task_id, record.action.reason)
                    break

                if record.is_success():
                    context.page_history.append(record.page_summary)
                    logger.debug("任务 %s 步骤 %d 成功", context.task_id, step_index)
                else:
                    logger.warning("任务 %s 步骤 %d 失败: %s",
                                   context.task_id, step_index, record.error_message)
                    if record.retry_count >= settings.execution.max_retries_per_step:
                        context.status = TaskStatus.FAILED
                        logger.error("任务 %s 因步骤 %d 失败次数过多而终止", context.task_id, step_index)
                        break

                if self._detect_loop(record.action):
                    context.status = TaskStatus.ABORTED
                    logger.warning("任务 %s 因检测到死循环而中止", context.task_id)
                    break

            except Exception as exc:
                logger.error("任务 %s 步骤 %d 发生未预期异常: %s", context.task_id, step_index, exc)
                context.status = TaskStatus.FAILED
                break

        if context.status == TaskStatus.RUNNING:
            context.status = TaskStatus.COMPLETED
            logger.info("任务 %s 正常完成，共执行 %d 步", context.task_id, context.current_step)

        archiver.save_task_meta({
            "task_id": context.task_id,
            "user_goal": context.user_goal,
            "status": context.status.value,
            "steps": len(context.steps),
            "success_rate": context.get_success_rate(),
            "total_tokens": context.total_tokens_used,
            "created_at": str(context.created_at),
        })

        report_generator = ReportGenerator(context, archiver)
        report_path = report_generator.generate()
        logger.info("任务 %s 报告已生成: %s", context.task_id, report_path)

        logger.info("任务 %s 结束: status=%s, steps=%d, tokens=%d",
                     context.task_id, context.status.value, context.current_step, context.total_tokens_used)
        return context

    def _check_timeout(self, context: TaskContext) -> bool:
        """
        检查任务是否已超时。

        参数
        ----------
        context : TaskContext
            当前任务上下文。

        返回
        -------
        bool
            True 表示任务已超时。
        """
        max_duration: int = settings.execution.max_total_duration_seconds
        if context.is_timeout(max_duration_seconds=max_duration):
            logger.warning("任务 %s 超时: 已执行 %ds，限制 %ds",
                           context.task_id, max_duration, max_duration)
            return True
        return False

    def _detect_loop(self, action: Action) -> bool:
        """
        检测是否陷入死循环。

        当连续相同操作的次数超过配置阈值时判定为死循环。
        相同操作的定义：action_type + element_id + direction。
        element_id 为 None 时使用 direction 区分（如 scroll:up vs scroll:down），
        均有值时三者联合判定。

        参数
        ----------
        action : Action
            当前步骤的操作指令。

        返回
        -------
        bool
            True 表示检测到死循环。
        """
        action_key: str = "{}:{}:{}".format(
            action.action_type.value,
            action.params.element_id or "",
            action.params.direction or "",
        )
        self._last_actions.append(action_key)

        if len(self._last_actions) > settings.loop_detection.max_history_size:
            self._last_actions.pop(0)

        max_same: int = settings.loop_detection.max_same_actions
        if len(self._last_actions) >= max_same:
            recent: list[str] = self._last_actions[-max_same:]
            if len(set(recent)) == 1:
                self._same_action_count += 1
                if self._same_action_count >= max_same:
                    logger.warning("检测到死循环: 连续 %d 次相同操作 %s",
                                   self._same_action_count, action_key)
                    return True
            else:
                self._same_action_count = 0

        return False
