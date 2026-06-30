"""
消息组装器 —— 按多模态格式构建 LLM 请求消息。

负责将系统 prompt、当前截图、结构化摘要和历史步骤摘要组装为
LLM 所需的多模态消息格式。支持分层上下文管理：
历史步骤仅保留文本摘要，当前步骤使用截图 + 结构化摘要。
"""

from typing import Optional

from ..logger import get_logger
from ..prompts.system_prompt import SYSTEM_PROMPT
from .base import LLMMessage

logger = get_logger(__name__)


class MessageBuilder:
    """
    消息组装器。

    提供静态方法将系统 prompt、用户截图、UI 结构化摘要和历史上下文
    组装为 LLMMessage 列表。当前步骤使用截图 + 结构化摘要的双通道输入，
    历史步骤仅保留文本形式的压缩摘要以节约 Token。

    使用方式
    --------
    >>> messages = MessageBuilder.build_decision_message(
    ...     screenshot_base64="...",
    ...     structured_summary="...",
    ...     user_goal="打开设置",
    ...     history=["步骤 1: 已回到桌面"],
    ...     step_index=2,
    ... )
    """

    @staticmethod
    def build_decision_message(
        screenshot_base64: str,
        structured_summary: str,
        user_goal: str,
        history: Optional[list[str]] = None,
        step_index: int = 1,
    ) -> list[LLMMessage]:
        """
        构建步骤决策所需的多模态消息列表。

        消息结构：
        1. system 角色：框架级系统指令（SYSTEM_PROMPT）
        2. user 角色（可选）：历史步骤摘要文本
        3. user 角色：当前步骤的截图 + 结构化摘要 + 用户目标

        参数
        ----------
        screenshot_base64 : str
            当前屏幕截图的 Base64 编码字符串（JPEG 格式）。
        structured_summary : str
            当前页面 UI 树的结构化摘要文本。
        user_goal : str
            用户输入的最终任务目标描述。
        history : Optional[list[str]]
            已完成步骤的页面摘要列表，用于提供上下文。
        step_index : int
            当前步骤编号，从 1 开始。

        返回
        -------
        list[LLMMessage]
            组装完成的 LLM 消息列表。
        """
        messages: list[LLMMessage] = [LLMMessage(role="system", content=SYSTEM_PROMPT)]

        if history:
            history_text = "\n".join([f"步骤 {i + 1}: {h}" for i, h in enumerate(history)])
            messages.append(
                LLMMessage(role="user", content=f"## 历史步骤摘要\n{history_text}")
            )
            logger.debug("MessageBuilder 添加历史上下文: %d 条", len(history))

        user_content: list[dict] = [
            {
                "type": "text",
                "text": f"## 当前步骤 #{step_index}\n用户目标: {user_goal}",
            },
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{screenshot_base64}"},
            },
            {
                "type": "text",
                "text": f"## 当前页面元素\n{structured_summary}\n\n请输出下一步操作（JSON 格式）。",
            },
        ]
        messages.append(LLMMessage(role="user", content=user_content))

        logger.debug(
            "MessageBuilder 构建完成: step=%d, 消息数=%d, 有历史=%s",
            step_index, len(messages), "是" if history else "否",
        )
        return messages

    @staticmethod
    def build_summary_message(page_content: str) -> list[LLMMessage]:
        """
        构建历史摘要压缩所需的消息列表。

        使用 SUMMARY_PROMPT 作为 system 指令，要求模型将
        完整的页面描述压缩为简洁摘要。

        参数
        ----------
        page_content : str
            需要压缩的页面描述文本。

        返回
        -------
        list[LLMMessage]
            用于摘要压缩的 LLM 消息列表。
        """
        from ..prompts.summary_prompt import SUMMARY_PROMPT

        messages = [
            LLMMessage(role="system", content=SUMMARY_PROMPT),
            LLMMessage(role="user", content=page_content),
        ]
        logger.debug("MessageBuilder 构建摘要消息: 输入 %d 字符", len(page_content))
        return messages
