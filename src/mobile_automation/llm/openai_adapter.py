"""
OpenAI GPT-4o 适配器 —— 调用 OpenAI 标准 API。

使用 OpenAI SDK 连接 OpenAI 官方 API 端点，支持 GPT-4o 等视觉模型，
作为 Qwen 之外的可选备选 LLM 提供商。
"""

from typing import Any, Optional

from openai import OpenAI

from ..config import settings
from ..logger import get_logger
from .base import LLMAdapter, LLMMessage

logger = get_logger(__name__)


class OpenAIAdapter(LLMAdapter):
    """
    OpenAI GPT-4o 适配器。

    通过 OpenAI SDK 调用 GPT-4o 系列模型。支持多模态输入，
    构造函数支持依赖注入所有配置项。

    使用方式
    --------
    >>> adapter = OpenAIAdapter()
    >>> messages = [LLMMessage(role="user", content="描述这张图片")]
    >>> response = adapter.chat(messages)
    """

    CONTEXT_WINDOW_DEFAULT: int = 128000
    """GPT-4o 默认上下文窗口大小。"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> None:
        """
        初始化 OpenAIAdapter。

        参数
        ----------
        api_key : Optional[str]
            OpenAI API 密钥，未传入时从 settings.llm.api_key 读取。
        base_url : Optional[str]
            API 请求基础地址，未传入时从 settings.llm.base_url 读取。
        model_name : Optional[str]
            模型名称，未传入时从 settings.llm.model_name 读取。
        """
        self._api_key: str = api_key or settings.llm.api_key
        self._base_url: str = base_url or settings.llm.base_url
        self._model: str = model_name or settings.llm.model_name or "gpt-4o"

        logger.info("OpenAIAdapter 初始化: model=%s", self._model)

        self._client: OpenAI = OpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
        )

    @property
    def context_window(self) -> int:
        """
        返回 GPT-4o 模型的上下文窗口大小。

        返回
        -------
        int
            固定值 128000 Token。
        """
        return self.CONTEXT_WINDOW_DEFAULT

    def chat(self, messages: list[LLMMessage], **kwargs) -> str:
        """
        向 OpenAI 模型发送消息并获取回复。

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
        openai.APIError
            API 调用失败时抛出。
        """
        openai_messages: list[dict[str, Any]] = [
            {"role": m.role, "content": m.content} for m in messages
        ]

        logger.debug("OpenAIAdapter.chat 发送消息: %d 条, model=%s", len(openai_messages), self._model)

        response = self._client.chat.completions.create(
            model=self._model,
            messages=openai_messages,
            max_tokens=kwargs.get("max_tokens", settings.llm.max_tokens),
            temperature=kwargs.get("temperature", settings.llm.temperature),
        )

        result: str = response.choices[0].message.content or ""
        logger.debug("OpenAIAdapter.chat 收到回复: %d 字符", len(result))
        return result

    def count_tokens(self, messages: list[LLMMessage]) -> int:
        """
        估算 OpenAI 消息列表的 Token 消耗数。

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
        logger.debug("OpenAIAdapter.count_tokens: %d 条消息共约 %d token", len(messages), total)
        return total
