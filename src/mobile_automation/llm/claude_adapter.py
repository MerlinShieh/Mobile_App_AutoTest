"""
Anthropic Claude 适配器 —— 调用 Anthropic Messages API。

使用 Anthropic SDK 连接 Claude 系列模型（如 Claude 3.5 Sonnet），
支持 system 角色独立传输和多模态内容输入。
"""

from typing import Any, Optional

from anthropic import Anthropic

from ..config import settings
from ..logger import get_logger
from .base import LLMAdapter, LLMMessage

logger = get_logger(__name__)


class ClaudeAdapter(LLMAdapter):
    """
    Anthropic Claude 适配器。

    通过 Anthropic SDK 调用 Claude 系列模型。Claude API 要求 system 消息
    通过独立的 system 参数传递，user/assistant 消息中的内容需按 Anthropic
    多模态格式组织。

    使用方式
    --------
    >>> adapter = ClaudeAdapter()
    >>> messages = [LLMMessage(role="user", content="你好")]
    >>> response = adapter.chat(messages)
    """

    CONTEXT_WINDOW_DEFAULT: int = 200000
    """Claude 3.5 Sonnet 默认上下文窗口大小。"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> None:
        """
        初始化 ClaudeAdapter。

        参数
        ----------
        api_key : Optional[str]
            Anthropic API 密钥，未传入时从 settings.llm.api_key 读取。
        model_name : Optional[str]
            模型名称，未传入时从 settings.llm.model_name 读取，
            默认值为 "claude-3-5-sonnet-20241022"。
        """
        self._api_key: str = api_key or settings.llm.api_key
        self._model: str = model_name or settings.llm.model_name or "claude-3-5-sonnet-20241022"

        logger.info("ClaudeAdapter 初始化: model=%s", self._model)

        self._client: Anthropic = Anthropic(api_key=self._api_key)

    @property
    def context_window(self) -> int:
        """
        返回 Claude 模型的上下文窗口大小。

        返回
        -------
        int
            固定值 200000 Token。
        """
        return self.CONTEXT_WINDOW_DEFAULT

    def chat(self, messages: list[LLMMessage], **kwargs) -> str:
        """
        向 Claude 模型发送消息并获取回复。

        Claude API 的特殊处理：
        - system 角色的消息通过独立的 system 参数传入
        - 其余消息按 user/assistant 角色传入
        - 多模态内容需转换为 Anthropic 指定的 content block 格式

        参数
        ----------
        messages : list[LLMMessage]
            待发送的消息列表。
        **kwargs
            可选覆盖参数：max_tokens、temperature。

        返回
        -------
        str
            模型生成的回复文本。

        异常
        ------
        anthropic.APIError
            API 调用失败时抛出。
        """
        system_content: str = ""
        chat_messages: list[dict[str, Any]] = []

        for m in messages:
            if m.role == "system":
                system_content = m.content if isinstance(m.content, str) else str(m.content)
            else:
                content: list[dict[str, Any]] = []
                if isinstance(m.content, str):
                    content.append({"type": "text", "text": m.content})
                elif isinstance(m.content, list):
                    content = m.content
                chat_messages.append({"role": m.role, "content": content})

        logger.debug(
            "ClaudeAdapter.chat 发送消息: %d 条, system=%d 字符, model=%s",
            len(chat_messages), len(system_content), self._model,
        )

        response = self._client.messages.create(
            model=self._model,
            system=system_content or None,
            messages=chat_messages,
            max_tokens=kwargs.get("max_tokens", settings.llm.max_tokens),
            temperature=kwargs.get("temperature", settings.llm.temperature),
        )

        result: str = response.content[0].text if response.content else ""
        logger.debug("ClaudeAdapter.chat 收到回复: %d 字符", len(result))
        return result

    def count_tokens(self, messages: list[LLMMessage]) -> int:
        """
        估算 Claude 消息列表的 Token 消耗数。

        文本按字符数的一半估算，图片按每张 1000 Token 估算。

        参数
        ----------
        messages : list[LLMMessage]
            待估算的消息列表。

        返回
        -------
        int
            估算的 Token 总数。
        """
        total: int = 0
        for msg in messages:
            if isinstance(msg.content, str):
                total += len(msg.content) // 2
            elif isinstance(msg.content, list):
                for item in msg.content:
                    if item.get("type") == "text":
                        total += len(item.get("text", "")) // 2
                    elif item.get("type") == "image_url":
                        total += 1000
        logger.debug("ClaudeAdapter.count_tokens: %d 条消息共约 %d token", len(messages), total)
        return total
