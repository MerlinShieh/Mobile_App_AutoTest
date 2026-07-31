"""
单步执行引擎 —— StepRunner。

执行的完整闭环：感知 -> 弹窗检测 -> LLM 决策 -> 元素解析 -> 执行 -> 验证 -> 记录。

各步骤详述：
  1. 感知：调用 ScreenCapture 获取当前截图和 UI 树（双通道感知）。
  2. 弹窗检测：PopupHandler 检测是否有弹窗干扰，有则自动处理。
  3. LLM 决策：调用 LLMService 分析截图和结构化摘要，输出下一步 Action。
  4. 元素解析：将 LLM 返回的 element_id 从本地索引解析为 resource-id / 坐标。
  5. 执行：ActionExecutor 执行 Action。
  6. 验证：PageChangeDetector 检验操作后页面是否发生变化。
  7. 记录：将执行结果写入 StepRecord，返回给 Orchestrator。
"""

import base64
import json
import re
import time
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
from ..models.perception import PerceptualResult, UITree

from ..models.task import StepRecord
from ..perception.page_diff import PageChangeDetector
from ..perception.screen_capture import ScreenCapture
from ..perception.ui_tree import UITreeExtractor
from ..popup.popup_handler import PopupHandler
from ..prompts.decision_prompt import DecisionPromptBuilder
from ..reporting.archiver import DataArchiver, StepArchiveData
from .task_context import TaskContext

logger = get_logger(__name__)


class StepRunner:
    """
    单步执行引擎。

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
        初始化 StepRunner。

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
        self._dm: DeviceManager = device_manager
        self._perception: ScreenCapture = perception
        self._popup_handler: PopupHandler = popup_handler
        self._llm: LLMService = llm_service
        self._executor: ActionExecutor = action_executor
        self._archiver: Optional[DataArchiver] = archiver
        self._token_budget: Optional[TokenBudgetManager] = token_budget
        self._page_diff: PageChangeDetector = PageChangeDetector()
        self._decision_builder: DecisionPromptBuilder = DecisionPromptBuilder()
        self._error_handler: ErrorHandler = ErrorHandler(device_manager=device_manager)
        logger.debug("StepRunner 初始化完成")

    def set_archiver(self, archiver: DataArchiver) -> None:
        """
        设置数据归档器。可在每次任务执行前动态切换。

        参数
        ----------
        archiver : DataArchiver
            数据归档器实例。
        """
        self._archiver = archiver
        logger.debug("StepRunner 已绑定归档器: %s", archiver.base_dir)

    def set_token_budget(self, token_budget: TokenBudgetManager) -> None:
        """
        设置 Token 预算管理器。可在每次任务执行前动态切换。

        参数
        ----------
        token_budget : TokenBudgetManager
            Token 预算管理器实例。
        """
        self._token_budget = token_budget
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
          1. 感知当前页面状态 + 弹窗处理。
          2. LLM 决策（若无预置 Action）。
          3. 解析 element_id 为实际坐标 + 执行 Action。
          4. 二次感知并验证页面变化 / 归档结果。

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
                perceptual = self._perceive_with_popup_handling(step_index, record)
                if record.status == StepStatus.RETRYING:
                    continue

                # 2. LLM 决策（或使用预置 Action）
                if preset_action is None:
                    action: Action = self._decide_action(perceptual, task_context, attempt + 1)
                    record.action = action
                    logger.info("Step %d LLM 决策完成: type=%s, element_id=%s",
                                step_index, action.action_type.value, action.params.element_id)

                # 3. 解析坐标 + 执行
                self._resolve_action_coordinates(record.action, perceptual)
                self._executor.execute(record.action)

                # 4. 验证页面变化 + 归档
                if self._verify_and_finalize(step_index, perceptual, record):
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
                    self._register_step_archive(
                        step_index, None, record.action, record.status.value,
                        error=record.error_message,
                    )
                else:
                    record.status = StepStatus.RETRYING

        return record

    def _perceive_with_popup_handling(
        self,
        step_index: int,
        record: StepRecord,
    ) -> PerceptualResult:
        """
        感知当前页面并处理弹窗。

        1. 调用 ScreenCapture 获取截图和 UI 树。
        2. 归档操作前的截图和 XML。
        3. 检测弹窗，有则处理后设置 record.status = RETRYING。

        返回
        -------
        PerceptualResult
            感知结果。
        """
        perceptual: PerceptualResult = self._perception.capture_with_ui_tree()

        self._archive_screenshot(step_index, perceptual, after=False)
        if perceptual.ui_tree:
            self._archive_xml_and_summary(step_index, perceptual.ui_tree)

        popup_result = self._popup_handler.detect(perceptual.ui_tree)
        if popup_result and popup_result.detected:
            handled = self._popup_handler.handle(popup_result)
            if handled:
                logger.info("Step %d 弹窗已处理，重新感知并重试", step_index)
            else:
                logger.warning("Step %d 弹窗处理未完成，重新感知", step_index)
            record.status = StepStatus.RETRYING

        return perceptual

    def _verify_and_finalize(
        self,
        step_index: int,
        perceptual: PerceptualResult,
        record: StepRecord,
    ) -> bool:
        """
        验证操作执行后的页面变化并归档结果。

        对滑动操作先等待页面稳定，然后：
        - 非变更操作（screenshot / wait / terminate / verify）：直接标记成功。
        - 其他操作：二次感知并与操作前对比，判断页面是否变化。
        无论成功或失败均会执行归档。

        参数
        ----------
        step_index : int
            步骤序号。
        perceptual : PerceptualResult
            操作前的感知结果。
        record : StepRecord
            当前步骤记录，会被修改。

        返回
        -------
        bool
            True 表示步骤已完成（应退出重试循环），False 表示需重试。
        """
        if record.action.action_type in (
            ActionType.SWIPE, ActionType.SWIPE_POINT, ActionType.SCROLL,
        ):
            time.sleep(settings.execution.page_stable_poll_ms / 1000.0)

        self._dm.health_check()

        # 非变更操作：跳过验证，直接成功
        if record.action.action_type in (
            ActionType.SCREENSHOT, ActionType.WAIT, ActionType.TERMINATE, ActionType.VERIFY,
        ):
            record.page_summary = (
                perceptual.ui_tree.structured_summary
                if perceptual.ui_tree else ""
            )
            record.status = StepStatus.SUCCESS
            logger.info("Step %d 执行成功 (动作=%s 无需验证页面变化)",
                        step_index, record.action.action_type.value)
            self._archive_screenshot(step_index, perceptual, after=True)
            self._register_step_archive(
                step_index, perceptual, record.action, record.status.value,
            )
            return True

        # 二次感知 + 页面变化对比
        new_perceptual: PerceptualResult = self._perception.capture_with_ui_tree()
        self._archive_screenshot(step_index, new_perceptual, after=True)
        change_result = self._page_diff.compare(
            new_perceptual.ui_tree, new_perceptual.screenshot_base64,
        )

        if change_result.has_changed:
            record.page_summary = (
                new_perceptual.ui_tree.structured_summary
                if new_perceptual.ui_tree else ""
            )
            record.status = StepStatus.SUCCESS
            logger.info("Step %d 执行成功", step_index)
            self._register_step_archive(
                step_index, perceptual, record.action, record.status.value,
            )
            return True

        record.retry_count += 1
        if record.retry_count >= settings.execution.max_retries_per_step:
            record.status = StepStatus.FAILED
            record.error_message = "操作后页面未发生变化"
            logger.warning("Step %d 失败: 操作后页面未变化", step_index)
            self._register_step_archive(
                step_index, perceptual, record.action, record.status.value,
                error=record.error_message,
            )
            return True

        record.status = StepStatus.RETRYING
        logger.info("Step %d 页面未变化，重试 (attempt %d/%d)",
                    step_index, record.retry_count, settings.execution.max_retries_per_step)
        return False

    def _decide_action(self, perceptual: PerceptualResult, task_context: TaskContext, attempt: int = 1) -> Action:
        """
        调用 LLM 决策下一步操作。

        将截图、结构化摘要、历史上下文组装为消息列表，
        调用 LLMService.chat 获取 JSON 格式的 Action。
        在组装消息前自动检查 Token 预算并执行压缩。

        参数
        ----------
        perceptual : PerceptualResult
            当前感知结果（截图 + UI 树）。
        task_context : TaskContext
            任务上下文（用户目标 + 历史步摘要）。
        attempt : int
            当前步骤的尝试次数序号（从 1 开始）。

        返回
        -------
        Action
            LLM 决策出的操作指令。

        异常
        ------
        json.JSONDecodeError
            LLM 输出无法解析为有效 JSON 时抛出。
        KeyError
            JSON 结构中缺少必要字段时抛出。
        """
        structured_summary: str = perceptual.ui_tree.structured_summary if perceptual.ui_tree else ""

        # ---- Token 预算检查与压缩策略决策 ----
        compression_strategy: str = "none"
        enable_reasoning: bool = settings.models.enable_reasoning
        if self._token_budget is not None and task_context.page_history:
            # 预估本次消息的 Token 消耗
            preview_msgs = self._decision_builder.build(
                user_goal=task_context.user_goal,
                screenshot=perceptual.screenshot_base64[:100],
                structured_summary=structured_summary[:200],
                history=task_context.page_history,
                step_index=task_context.current_step + 1,
                compression_strategy="none",
                enable_reasoning=enable_reasoning,
            )
            estimated = self._token_budget.estimate_messages_tokens(preview_msgs)

            if self._token_budget.needs_compression(estimated):
                compression_strategy = self._token_budget.get_compression_strategy(preview_msgs)
                logger.info("Step %d 触发 Token 压缩: 策略=%s, 估算=%d, 已用=%d",
                            task_context.current_step + 1, compression_strategy,
                            estimated, self._token_budget.total_used)

        messages = self._decision_builder.build(
            user_goal=task_context.user_goal,
            screenshot=perceptual.screenshot_base64,
            structured_summary=structured_summary,
            history=task_context.page_history,
            step_index=task_context.current_step + 1,
            compression_strategy=compression_strategy,
            enable_reasoning=enable_reasoning,
        )

        response: str = self._llm.chat(messages)
        logger.debug("Step %d LLM 原始响应: %s", task_context.current_step + 1, response[:200])

        self._archive_llm_interaction(
            task_context.current_step + 1,
            [{"role": m.role, "content": m.content} for m in messages],
            response,
            attempt=attempt,
        )

        # ---- 记录 Token 消耗 ----
        if self._token_budget is not None:
            actual_tokens = self._token_budget.estimate_messages_tokens(messages)
            self._token_budget.record_usage(actual_tokens)

        action: Action = self._parse_llm_response(response)
        return action

    def _resolve_action_coordinates(self, action: Action, perceptual: PerceptualResult) -> None:
        """
        解析 Action 中的 element_id 为实际执行坐标。

        从 UI 树的本地索引中查找 element_id 对应的节点，
        将其中心坐标和 resource-id 填入 Action.params。

        当 SCROLL/SWIPE 未指定 element_id 时，自动查找
        屏幕上的可滚动容器并以其中心作为滑动起点。

        参数
        ----------
        action : Action
            待解析的 Action，会修改其 params。
        perceptual : PerceptualResult
            感知结果，包含 UI 树。
        """
        if not perceptual.ui_tree:
            return

        # ---- 1. element_id 已指定：正常解析 ----
        if action.params.element_id:
            node = perceptual.ui_tree.get_by_element_id(action.params.element_id)
            if node is None:
                logger.warning("element_id %s 在本地索引中未找到", action.params.element_id)
                raise ValueError(f"element_id {action.params.element_id} 在本地索引中未找到")
            cx, cy = node.center()
            action.params.x = cx
            action.params.y = cy
            action.params.ui_element = node.resource_id or node.text
            logger.debug("element_id %s 解析为坐标 (%d, %d), ui_element=%s",
                         action.params.element_id, cx, cy, action.params.ui_element)
            return

        # ---- 2. SCROLL/SWIPE 未指定 element_id：自动寻找可滚动容器 ----
        if action.action_type in (ActionType.SCROLL, ActionType.SWIPE):
            self._resolve_scrollable_container(action, perceptual)

    def _resolve_scrollable_container(self, action: Action, perceptual: PerceptualResult) -> None:
        """自动找到屏幕上的可滚动容器并设置为滑动/滚动的起点。"""
        scrollable_nodes = [
            n for n in perceptual.ui_tree.local_index.values()
            if n.scrollable and n.area() > 0
        ]
        if not scrollable_nodes:
            return

        screen_w, screen_h = self._dm.get_screen_size()
        screen_area = screen_w * screen_h

        candidates = [
            n for n in scrollable_nodes
            if n.area() < screen_area * 0.95 and n.area() > screen_area * 0.02
        ]
        if not candidates:
            return

        # 横屏模式优先选择左侧容器（菜单通常在左侧）
        if screen_w > screen_h:
            left_nodes = [
                n for n in candidates
                if (n.bounds[0] + n.bounds[2]) // 2 < screen_w * 0.5
            ]
            target = max(left_nodes, key=lambda n: n.area()) if left_nodes else max(candidates, key=lambda n: n.area())
        else:
            target = max(candidates, key=lambda n: n.area())

        cx, cy = target.center()
        action.params.x = cx
        action.params.y = cy
        action.params.ui_element = target.resource_id or target.text or ""
        logger.info("自动定位可滚动容器 %s (%s) 作为滑动起点 (%d, %d)",
                    target.element_id, action.params.ui_element, cx, cy)

    @staticmethod
    def _sanitize_json_strings(text: str) -> str:
        """
        转义 JSON 字符串值内部的未转义控制字符（\\n、\\r、\\t）。

        使用正则替换替代逐字符循环，避免 O(n) 字符复制开销。
        仅处理双引号字符串内部的控制字符，JSON 结构中的换行不受影响。
        """
        def _escape_ctrl(m: re.Match) -> str:
            ch = m.group(0)
            if ch == "\n":
                return "\\n"
            if ch == "\r":
                return "\\r"
            if ch == "\t":
                return "\\t"
            return ch

        return re.sub(
            r'(?<=")(?:[^"\\]|\\.)*?(?=")',
            lambda m: re.sub(r'[\n\r\t]', _escape_ctrl, m.group(0)),
            text,
        )

    @staticmethod
    def _parse_llm_response(response: str) -> Action:
        """
        解析 LLM 返回的响应为 Action 对象。

        支持以下格式（按优先级）：
        1. <answer>...</answer> 标签包裹的 JSON（CoT 格式）
        2. markdown 代码块包裹的 JSON（```json ... ```）
        3. 裸 JSON

        同时提取 <think> 标签中的推理过程用于日志记录。
        自动修复 LLM 常见输出问题：字符串值内未转义的控制字符。

        参数
        ----------
        response : str
            LLM 返回的原始文本。

        返回
        -------
        Action
            解析出的操作指令。解析失败时抛出 ValueError。
        """
        try:
            # 提取思维链推理（用于日志）
            think_match = re.search(r"<think>(.*?)</think>", response, re.DOTALL)
            if think_match:
                reasoning = think_match.group(1).strip()
                logger.debug("LLM 思维链推理: %s", reasoning[:200])

            # 提取 JSON 文本：优先 <answer> 标签 > markdown 代码块 > 原始文本
            answer_match = re.search(r"<answer>(.*?)</answer>", response, re.DOTALL)
            if answer_match:
                json_text = answer_match.group(1).strip()
            else:
                json_match = re.search(r"```(?:json)?\s*({.*?})\s*```", response, re.DOTALL)
                json_text = json_match.group(1) if json_match else response

            # 首次尝试直接解析
            try:
                data = json.loads(json_text)
            except json.JSONDecodeError:
                # 修复常见 LLM 毛病：字符串值内未转义的控制字符
                sanitized = StepRunner._sanitize_json_strings(json_text)
                data = json.loads(sanitized)

            params_dict: dict = data.get("params", {})
            return Action(
                action_type=ActionType(data.get("action_type", "wait")),
                params=ActionParams(
                    element_id=params_dict.get("element_id"),
                    x=params_dict.get("x"),
                    y=params_dict.get("y"),
                    text=params_dict.get("text"),
                    direction=params_dict.get("direction"),
                    duration_ms=params_dict.get("duration_ms", 1500),
                    package_name=params_dict.get("package_name"),
                    match=params_dict.get("match", False),
                ),
                reason=data.get("reason", ""),
            )
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.error("LLM 响应解析失败: %s\n原始响应: %s", exc, response)
            raise ValueError(f"LLM 响应解析失败: {exc}") from exc

    def _archive_screenshot(self, step_index: int, perceptual: PerceptualResult, after: bool) -> None:
        """
        将截图通过归档器保存到本地文件。

        参数
        ----------
        step_index : int
            步骤序号。
        perceptual : PerceptualResult
            包含 Base64 截图的感知结果。
        after : bool
            是否为操作后的截图。
        """
        if self._archiver is None:
            return
        try:
            raw = base64.b64decode(perceptual.screenshot_base64)
            self._archiver.save_screenshot(step_index, raw, after=after)
        except Exception as exc:
            logger.warning("截图归档失败: %s", exc)

    def _archive_xml_and_summary(self, step_index: int, ui_tree: UITree) -> None:
        """
        将原始 XML 和结构化摘要通过归档器保存到本地文件。

        参数
        ----------
        step_index : int
            步骤序号。
        ui_tree : UITree
            包含 XML 和摘要的 UI 树数据。
        """
        if self._archiver is None:
            return
        try:
            if ui_tree.raw_xml:
                self._archiver.save_raw_xml(step_index, ui_tree.raw_xml)
            if ui_tree.structured_summary:
                self._archiver.save_structured_summary(step_index, ui_tree.structured_summary)
        except Exception as exc:
            logger.warning("XML/摘要归档失败: %s", exc)

    def _archive_llm_interaction(
        self,
        step_index: int,
        messages: list[dict],
        response: str,
        attempt: int = 1,
    ) -> None:
        """
        将 LLM 请求消息和响应通过归档器保存到本地文件。

        参数
        ----------
        step_index : int
            步骤序号。
        messages : list[dict]
            发送给 LLM 的消息列表。
        response : str
            LLM 返回的响应文本。
        """
        if self._archiver is None:
            return
        try:
            self._archiver.save_llm_request(step_index, messages, attempt=attempt)
            self._archiver.save_llm_response(step_index, response, attempt=attempt)
        except Exception as exc:
            logger.warning("LLM 交互归档失败: %s", exc)

    def _register_step_archive(
        self,
        step_index: int,
        perceptual: Optional[PerceptualResult],
        action: Action,
        status: str,
        error: str = "",
    ) -> None:
        """
        注册步骤的归档数据摘要。

        参数
        ----------
        step_index : int
            步骤序号。
        perceptual : Optional[PerceptualResult]
            操作前的感知结果。
        action : Action
            执行的操作指令。
        status : str
            步骤状态。
        error : str
            错误信息。
        """
        if self._archiver is None:
            return
        try:
            step_dir = self._archiver.base_dir / f"step_{step_index:02d}"
            archive = StepArchiveData(
                step_index=step_index,
                step_dir=step_dir,
                screenshot_path=step_dir / "screenshot.png",
                screenshot_after_path=step_dir / "screenshot_after.png"
                if (step_dir / "screenshot_after.png").exists() else None,
                xml_path=step_dir / "xml_raw.xml"
                if (step_dir / "xml_raw.xml").exists() else None,
                summary_path=step_dir / "summary.txt"
                if (step_dir / "summary.txt").exists() else None,
                llm_request_path=step_dir / "llm_request.json"
                if (step_dir / "llm_request.json").exists() else None,
                llm_response_path=step_dir / "llm_response.json"
                if (step_dir / "llm_response.json").exists() else None,
                action_type=action.action_type.value,
                action_detail=self._format_action_detail(action),
                status=status,
                error_message=error,
                reason=action.reason,
            )
            self._archiver.register_step_archive(archive)
        except Exception as exc:
            logger.warning("步骤归档注册失败: %s", exc)

    @staticmethod
    def _format_action_detail(action: Action) -> str:
        """格式化操作详情为字符串。"""
        parts = [f"type={action.action_type.value}"]
        if action.params.element_id:
            parts.append(f"element={action.params.element_id}")
        if action.params.text:
            parts.append(f"text={action.params.text}")
        if action.params.package_name:
            parts.append(f"package={action.params.package_name}")
        if action.params.direction:
            parts.append(f"direction={action.params.direction}")
        if action.params.x is not None:
            parts.append(f"coord=({action.params.x},{action.params.y})")
        return " | ".join(parts)
