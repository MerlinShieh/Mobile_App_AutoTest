"""决策引擎 —— DecisionEngine。

负责单步执行中的 LLM 决策环节：
  1. Token 预算检查与压缩策略决策。
  2. 组装多模态消息并调用 LLMService。
  3. 解析 LLM 响应为 Action（含 CoT / markdown 代码块 / 裸 JSON 三种格式）。
  4. 解析 element_id 为实际坐标；SCROLL/SWIPE 自动定位可滚动容器。
  5. 归档 LLM 请求与响应。

原为 StepRunner 的内部方法（_decide_action / _parse_llm_response /
_sanitize_json_strings / _resolve_action_coordinates /
_resolve_scrollable_container / _archive_llm_interaction），
拆分后独立成模块。
"""

import json
import re
from typing import Optional

from ...logger import get_logger
from ...config import settings
from ...device.device_manager import DeviceManager
from ...llm.base import LLMMessage
from ...llm.llm_service import LLMService
from ...llm.token_budget import TokenBudgetManager
from ...models.action import Action, ActionParams
from ...models.enums import ActionType
from ...models.perception import PerceptualResult, UITree
from ...models.task import TaskContext
from ...prompts.decision_prompt import DecisionPromptBuilder
from ...reporting.archiver import DataArchiver

logger = get_logger(__name__)

_RETRY_JSON_PROMPT: str = (
    "你上次的输出不是合法 JSON，请严格输出合法 JSON，不要包含多余文本。"
    "请重新给出完整决策，使用 <answer> 标签包裹 JSON 操作指令，"
    "不要引用或重复上次的非法输出。"
)
"""LLM 响应 JSON 解析失败时的引擎内自动重试修正提示。"""


class DecisionEngine:
    """LLM 决策 + 响应解析 + 坐标解析引擎。"""

    def __init__(
        self,
        device_manager: DeviceManager,
        llm_service: LLMService,
        token_budget: Optional[TokenBudgetManager] = None,
        archiver: Optional[DataArchiver] = None,
        decision_builder: Optional[DecisionPromptBuilder] = None,
    ) -> None:
        self._dm: DeviceManager = device_manager
        self._llm: LLMService = llm_service
        self._token_budget: Optional[TokenBudgetManager] = token_budget
        self._archiver: Optional[DataArchiver] = archiver
        self._decision_builder: DecisionPromptBuilder = (
            decision_builder or DecisionPromptBuilder()
        )
        logger.debug("DecisionEngine 初始化完成")

    def set_token_budget(self, token_budget: TokenBudgetManager) -> None:
        """绑定 Token 预算管理器（每次任务执行前由编排层调用）。"""
        self._token_budget = token_budget
        logger.debug("DecisionEngine 已绑定 TokenBudget: provider=%s", token_budget.provider)

    def set_archiver(self, archiver: DataArchiver) -> None:
        """切换归档器（每次任务执行前由编排层调用）。"""
        self._archiver = archiver

    def decide_action(
        self,
        perceptual: PerceptualResult,
        task_context: TaskContext,
        attempt: int = 1,
    ) -> Action:
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

        step_index: int = task_context.current_step + 1
        response: str = self._chat_and_archive(messages, step_index, attempt)

        try:
            action: Action = self.parse_llm_response(response)
        except ValueError as exc:
            # ---- 解析失败：引擎内自动重新请求 1 次（仅解析失败触发，网络/超时等异常不在此捕获） ----
            logger.warning(
                "Step %d LLM 响应 JSON 解析失败，触发引擎内自动重试 1 次: %s\n原始响应片段: %s",
                step_index, exc, response[:200],
            )
            retry_messages: list[LLMMessage] = messages + [
                LLMMessage(role="user", content=_RETRY_JSON_PROMPT)
            ]
            logger.info("Step %d 自动重试 LLM 请求（追加修正提示）", step_index)
            response = self._chat_and_archive(retry_messages, step_index, attempt + 1)
            logger.info("Step %d LLM 重试响应片段: %s", step_index, response[:200])
            # 第 2 次解析仍失败则按原逻辑抛异常，保持既有步骤重试兜底
            action = self.parse_llm_response(response)

        return action

    def _chat_and_archive(
        self,
        messages: list[LLMMessage],
        step_index: int,
        attempt: int,
    ) -> str:
        """
        调用 LLM 并归档本次请求/响应，同时记录 Token 消耗。

        每次真实 chat 调用都会独立记录 Token 消耗（估算），
        保证重试请求正常计入、不重复不遗漏。

        参数
        ----------
        messages : list[LLMMessage]
            发送给 LLM 的消息列表。
        step_index : int
            当前步骤序号（从 1 开始）。
        attempt : int
            本步骤的第几次 LLM 调用序号（用于归档文件区分）。

        返回
        -------
        str
            LLM 返回的原始响应文本。
        """
        response: str = self._llm.chat(messages)
        logger.debug("Step %d LLM 原始响应: %s", step_index, response[:200])

        self._archive_llm_interaction(
            step_index,
            [{"role": m.role, "content": m.content} for m in messages],
            response,
            attempt=attempt,
        )

        # 每次真实调用后记录 Token 消耗，重试请求同样计入
        if self._token_budget is not None:
            actual_tokens = self._token_budget.estimate_messages_tokens(messages)
            self._token_budget.record_usage(actual_tokens)

        return response

    def resolve_action_coordinates(self, action: Action, perceptual: PerceptualResult) -> None:
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
        if not perceptual.ui_tree:
            return
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
    def parse_llm_response(response: str) -> Action:
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
                sanitized = DecisionEngine._sanitize_json_strings(json_text)
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
