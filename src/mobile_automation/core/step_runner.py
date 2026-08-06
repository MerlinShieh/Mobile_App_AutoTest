"""
单步执行引擎 —— StepRunner（薄编排层）。

执行的完整闭环：感知 -> 弹窗检测 -> LLM 决策 -> 元素解析 -> 执行 -> 验证 -> 记录。

v1.4.0 起，原 StepRunner（上帝类，744 行 / 17 方法 / 5 职责）拆分为三个独立流水线模块，
本类只保留流程编排、重试控制与异常恢复：

  - PerceptionPipeline：感知 + 弹窗处理 + 操作前归档。
  - DecisionEngine：LLM 决策 + 响应解析 + 坐标解析 + LLM 交互归档。
  - ExecutionPipeline：执行验证 + 步骤归档。

三者互不引用，仅由本类顺序调用；对外接口（构造参数、run_step / set_archiver /
set_token_budget）保持不变。
"""

from typing import Optional

from ..config import settings
from ..device.device_manager import DeviceManager
from ..exception.error_handler import ErrorHandler
from ..executor.action_executor import ActionExecutor
from ..llm.llm_service import LLMService
from ..llm.token_budget import TokenBudgetManager
from ..logger import get_logger
from ..models.action import Action, ActionParams
from ..models.enums import ActionType, StepStatus
from ..models.perception import PerceptualResult
from ..models.task import StepRecord
from ..perception.screen_capture import ScreenCapture
from ..popup.popup_handler import PopupHandler
from ..reporting.archiver import DataArchiver
from .pipelines.decision_engine import DecisionEngine
from .pipelines.execution_pipeline import ExecutionPipeline
from .pipelines.perception_pipeline import PerceptionPipeline
from .task_context import TaskContext

logger = get_logger(__name__)


class StepRunner:
    """
    单步执行引擎（薄编排层）。

    封装一次操作从感知到执行的完整闭环。
    通过依赖注入接收所有协作者，职责清晰可测试。

    参数
    ----------
    device_manager : DeviceManager
        设备管理器实例。
    perception : ScreenCapture
        截图与 UI 树获取器。
    popup_handler : PopupHandler
        弹窗检测与处理器。
    llm_service : LLMService
        LLM 决策服务。
    action_executor : ActionExecutor
        动作执行器。
    archiver : Optional[DataArchiver]
        数据归档器，为 None 时不归档。
    token_budget : Optional[TokenBudgetManager]
        Token 预算管理器，为 None 时不压缩。
    """

    def __init__(
        self,
        device_manager: DeviceManager,
        perception: ScreenCapture,
        popup_handler: PopupHandler,
        llm_service: LLMService,
        action_executor: ActionExecutor,
        archiver: Optional[DataArchiver] = None,
        token_budget: Optional[TokenBudgetManager] = None,
    ) -> None:
        """
        初始化 StepRunner，内部实例化三个独立流水线。
        """
        self._dm: DeviceManager = device_manager
        self._executor: ActionExecutor = action_executor
        self._error_handler: ErrorHandler = ErrorHandler(device_manager=device_manager)

        # 拆分后的流水线（v1.4.0）
        self._perception_pipeline: PerceptionPipeline = PerceptionPipeline(
            device_manager=device_manager,
            perception=perception,
            popup_handler=popup_handler,
            archiver=archiver,
        )
        self._decision_engine: DecisionEngine = DecisionEngine(
            device_manager=device_manager,
            llm_service=llm_service,
            token_budget=token_budget,
            archiver=archiver,
        )
        self._execution_pipeline: ExecutionPipeline = ExecutionPipeline(
            device_manager=device_manager,
            perception=perception,
            archiver=archiver,
        )
        logger.debug("StepRunner 初始化完成 (pipelines: Perception/Decision/Execution)")

    def set_archiver(self, archiver: DataArchiver) -> None:
        """
        设置数据归档器，同步绑定到各流水线。可在每次任务执行前动态切换。

        参数
        ----------
        archiver : DataArchiver
            数据归档器实例。
        """
        self._perception_pipeline.set_archiver(archiver)
        self._decision_engine.set_archiver(archiver)
        self._execution_pipeline.set_archiver(archiver)
        logger.debug("StepRunner 已绑定归档器: %s", archiver.base_dir)

    def set_token_budget(self, token_budget: TokenBudgetManager) -> None:
        """
        设置 Token 预算管理器，同步绑定到决策引擎。可在每次任务执行前动态切换。

        参数
        ----------
        token_budget : TokenBudgetManager
            Token 预算管理器实例。
        """
        self._decision_engine.set_token_budget(token_budget)
        logger.debug("StepRunner 已绑定 TokenBudget: provider=%s", token_budget.provider)

    def run_step(
        self,
        step_index: int,
        task_context: TaskContext,
        preset_action: Optional[Action] = None,
    ) -> StepRecord:
        """
        执行一步完整的操作闭环。

        执行流程：
          1. 感知当前页面状态 + 弹窗处理（PerceptionPipeline）。
          2. LLM 决策（若无预置 Action）（DecisionEngine）。
          3. 解析 element_id 为实际坐标 + 执行 Action（DecisionEngine + ActionExecutor）。
          4. 二次感知并验证页面变化 / 归档结果（ExecutionPipeline）。

        参数
        ----------
        step_index : int
            当前步骤序号（从 1 开始）。
        task_context : TaskContext
            任务上下文，包含用户目标和历史信息。
        preset_action : Optional[Action]
            预置的操作指令。不为 None 时跳过 LLM 决策步骤。

        返回
        -------
        StepRecord
            本步骤的完整执行记录。
        """
        record: StepRecord = StepRecord(
            step_index=step_index,
            action=preset_action or Action(ActionType.WAIT, ActionParams()),
            status=StepStatus.PENDING,
        )

        for attempt in range(settings.execution.max_retries_per_step):
            try:
                record.status = StepStatus.RUNNING
                logger.info("Step %d 开始执行 (attempt %d/%d)",
                            step_index, attempt + 1, settings.execution.max_retries_per_step)

                # 1. 感知 + 弹窗处理
                perceptual = self._perception_pipeline.perceive_with_popup_handling(step_index, record)
                if record.status == StepStatus.RETRYING:
                    continue

                # 2. LLM 决策（或使用预置 Action）
                if preset_action is None:
                    action: Action = self._decision_engine.decide_action(
                        perceptual, task_context, attempt + 1,
                    )
                    record.action = action
                    logger.info("Step %d LLM 决策完成: type=%s, element_id=%s",
                                step_index, action.action_type.value, action.params.element_id)

                # 3. 解析坐标 + 执行
                self._decision_engine.resolve_action_coordinates(record.action, perceptual)
                self._executor.execute(record.action)

                # 4. 验证页面变化 + 归档
                if self._execution_pipeline.verify_and_finalize(step_index, perceptual, record):
                    break

            except Exception as exc:
                record.retry_count += 1
                record.error_message = str(exc)
                logger.error("Step %d 执行异常: %s", step_index, exc)

                # ErrorHandler 自动恢复：分类异常并尝试恢复动作
                # （设备重连 / LLM 指数退避），恢复成功则不消耗重试计数
                recovered = False
                recovery = "none"
                try:
                    category, recovery = self._error_handler.classify(exc)
                    recovered = bool(self._error_handler.handle(exc, category, recovery))
                except Exception as recovery_exc:
                    logger.warning("ErrorHandler 恢复动作本身异常: %s", recovery_exc)

                if recovered:
                    record.status = StepStatus.RETRYING
                    logger.info("Step %d ErrorHandler 已自动恢复（%s），重新执行", step_index, recovery)
                    continue

                if record.retry_count >= settings.execution.max_retries_per_step:
                    record.status = StepStatus.FAILED
                    logger.error("Step %d 已达最大重试次数，标记为失败", step_index)
                    self._execution_pipeline._register_step_archive(
                        step_index, None, record.action, record.status.value,
                        error=record.error_message,
                    )
                    # 标记失败后立即跳出循环，避免下一轮迭代将状态覆盖为 RUNNING
                    break
                else:
                    record.status = StepStatus.RETRYING

        # max_retries_per_step=0 时上方循环不执行，状态保持 PENDING，
        # 直接标记为 FAILED，避免调用方收到无意义的 PENDING 状态
        if record.status == StepStatus.PENDING:
            record.status = StepStatus.FAILED
            record.error_message = "max_retries_per_step 配置为 0，步骤无法执行"
            logger.error("Step %d %s", step_index, record.error_message)

        # 弹窗持续存在导致 attempt 耗尽（弹窗重试不计入 retry_count）时，
        # 状态会停留在 RETRYING 非终态；此处补齐 FAILED 终态并写明错误，
        # 避免编排层只记 warning、步骤以非终态返回并污染 success_rate 统计
        if record.status == StepStatus.RETRYING:
            record.status = StepStatus.FAILED
            record.error_message = "弹窗处理失败：重试耗尽后弹窗仍存在"
            logger.error("Step %d %s", step_index, record.error_message)
            self._execution_pipeline._register_step_archive(
                step_index, None, record.action, record.status.value,
                error=record.error_message,
            )

        return record

    @staticmethod
    def _parse_llm_response(response: str) -> Action:
        """
        解析 LLM 返回的响应为 Action 对象。

        兼容转发：解析逻辑已迁移至 DecisionEngine.parse_llm_response，
        保留此静态方法以避免破坏既有调用方（含测试）。

        参数
        ----------
        response : str
            LLM 返回的原始文本。

        返回
        -------
        Action
            解析出的操作指令。解析失败时抛出 ValueError。
        """
        return DecisionEngine.parse_llm_response(response)
