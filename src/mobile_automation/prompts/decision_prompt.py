"""
步骤决策 Prompt 构建器 —— 组装 LLM 决策所需的多模态消息。

DecisionPromptBuilder 根据用户目标、截图、结构化摘要和历史上下文
生成 LLM 决策消息列表。支持 Token 压缩策略：
- "none": 不压缩，发送全部历史
- "compress_history": 只发送最近 N 条历史摘要
- "drop_images": 只发送当前截图，历史仅保留文本摘要
- "full_summary": 用 LLM 压缩历史
"""

from typing import Optional

from ..llm.base import LLMMessage
from ..logger import get_logger
from .system_prompt import SYSTEM_PROMPT

logger = get_logger(__name__)


MAX_HISTORY_COMPRESSED: int = 5
"""compress_history 策略下保留的最近历史摘要条数"""


class DecisionPromptBuilder:
    """
    步骤决策 Prompt 构建器。

    封装 LLM 决策调用所需的消息组装逻辑，将系统 prompt、
    用户目标、截图、结构化摘要和历史步骤组装为 LLMMessage 列表。

    使用方式
    --------
    >>> builder = DecisionPromptBuilder()
    >>> messages = builder.build(
    ...     user_goal="打开设置",
    ...     screenshot="base64_string",
    ...     structured_summary="#1 可点 设置",
    ...     history=["步骤 1: 回到桌面"],
    ...     step_index=2,
    ... )
    """

    def build(
        self,
        user_goal: str,
        screenshot: str,
        structured_summary: str,
        history: Optional[list[str]] = None,
        step_index: int = 1,
        compression_strategy: str = "none",
    ) -> list[LLMMessage]:
        """
        构建完整的步骤决策消息列表。

        消息结构：
        1. system 角色：系统指令（SYSTEM_PROMPT）
        2. user 角色（可选）：历史步骤摘要（根据压缩策略裁剪）
        3. user 角色：当前步骤信息（目标 + 截图 + 结构化摘要）

        参数
        ----------
        user_goal : str
            用户输入的最终任务目标描述。
        screenshot : str
            当前屏幕截图的 Base64 编码字符串。
        structured_summary : str
            当前页面 UI 树的结构化摘要文本。
        history : Optional[list[str]]
            已完成步骤的页面摘要列表。
        step_index : int
            当前步骤序号，从 1 开始。
        compression_strategy : str
            Token 压缩策略: "none" / "compress_history" / "drop_images" / "full_summary"。

        返回
        -------
        list[LLMMessage]
            组装完成的 LLM 决策消息列表。
        """
        messages: list[LLMMessage] = [LLMMessage(role="system", content=SYSTEM_PROMPT)]

        # 根据压缩策略处理历史上下文
        processed_history = self._apply_history_compression(history, compression_strategy)
        if processed_history:
            history_text = "\n".join([f"步骤 {i + 1}: {h}" for i, h in enumerate(processed_history)])
            messages.append(
                LLMMessage(role="user", content=f"## 历史步骤摘要\n{history_text}")
            )
            logger.debug("DecisionPromptBuilder 添加历史上下文: %d 条 (策略=%s)",
                         len(processed_history), compression_strategy)

        # 根据压缩策略构建当前步骤内容
        user_content: list[dict] = [
            {
                "type": "text",
                "text": f"## 当前步骤 #{step_index}\n用户目标: {user_goal}",
            },
        ]

        if compression_strategy != "drop_images":
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{screenshot}"},
            })

        user_content.append({
            "type": "text",
            "text": f"## 当前页面元素\n{structured_summary}\n\n请输出下一步操作（JSON 格式）。",
        })
        messages.append(LLMMessage(role="user", content=user_content))

        logger.debug(
            "DecisionPromptBuilder 构建完成: step=%d, 总消息数=%d, 策略=%s",
            step_index, len(messages), compression_strategy,
        )
        return messages

    @staticmethod
    def _apply_history_compression(
        history: Optional[list[str]],
        strategy: str,
    ) -> list[str]:
        """
        根据压缩策略裁剪历史上下文。

        参数
        ----------
        history : Optional[list[str]]
            原始历史摘要列表。
        strategy : str
            压缩策略名称。

        返回
        -------
        list[str]
            裁剪后的历史摘要列表。
        """
        if not history:
            return []

        if strategy == "none":
            return list(history)

        if strategy == "compress_history":
            # 只保留最近 MAX_HISTORY_COMPRESSED 条
            truncated = history[-MAX_HISTORY_COMPRESSED:]
            logger.debug("历史压缩: %d -> %d 条", len(history), len(truncated))
            return truncated

        if strategy in ("drop_images", "full_summary"):
            # 丢弃历史，仅保留文本摘要的第一条和最后一条
            if len(history) <= 2:
                return list(history)
            compressed = [history[0], f"... 中间 {len(history) - 2} 步已压缩 ...", history[-1]]
            logger.debug("历史极端压缩: %d -> %d 条", len(history), len(compressed))
            return compressed

        return list(history)
