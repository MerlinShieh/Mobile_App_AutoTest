"""
LLM 适配器抽象基类与消息数据类定义。

定义 LLMAdapter 抽象接口，所有具体 LLM 提供商适配器必须实现该接口。
LLMMessage 数据类统一表示发送给 LLM 的消息结构。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class LLMMessage:
    """
    表示一条发送给 LLM 的消息。

    role 表示消息来源角色（system / user / assistant），
    content 支持字符串文本或多模态内容列表（如图片 + 文本混合）。

    属性
    ----------
    role : str
        消息角色，可选值: "system", "user", "assistant"。
    content : Any
        消息内容。字符串时为纯文本；列表时为多模态内容，
        每个元素为 {"type": "text", "text": "..."} 或
        {"type": "image_url", "image_url": {"url": "data:..."}} 格式。
    """
    role: str
    content: Any


class LLMAdapter(ABC):
    """
    LLM 适配器抽象基类。

    所有具体 LLM 提供商（Qwen / OpenAI / Anthropic）的适配器必须
    继承此类并实现 chat、count_tokens 和 context_window 属性。

    使用方式
    --------
    >>> class MyAdapter(LLMAdapter):
    ...     @property
    ...     def context_window(self) -> int:
    ...         return 32000
    ...     def chat(self, messages, **kwargs) -> str:
    ...         return "response"
    ...     def count_tokens(self, messages) -> int:
    ...         return 0
    """

    @abstractmethod
    def chat(self, messages: list[LLMMessage], **kwargs) -> str:
        """
        向 LLM 发送消息列表并返回模型生成的回复文本。

        参数
        ----------
        messages : list[LLMMessage]
            消息列表，包含 system / user / assistant 角色的消息。
        **kwargs
            额外参数，可覆盖默认的 max_tokens、temperature、timeout 等。

        返回
        -------
        str
            模型生成的回复文本。

        异常
        ------
        LLMServiceError
            API 调用失败、超时或返回异常状态时抛出。
        """

    @abstractmethod
    def count_tokens(self, messages: list[LLMMessage]) -> int:
        """
        估算给定消息列表的 Token 消耗数。

        参数
        ----------
        messages : list[LLMMessage]
            待估算的消息列表。

        返回
        -------
        int
            估算的 Token 总数。文本按字符数/2 估算，图片按固定值估算。
        """

    @property
    @abstractmethod
    def context_window(self) -> int:
        """
        返回当前模型的最大上下文窗口大小。

        返回
        -------
        int
            模型支持的上下文窗口 Token 数上限。
        """
