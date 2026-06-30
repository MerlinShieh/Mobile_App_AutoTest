"""
通义千问 Qwen-VL 适配器 —— 通过 DashScope 兼容接口调用。

使用 OpenAI SDK 连接阿里云 DashScope 兼容接口（/compatible-mode/v1），
支持 Qwen-VL-Max、Qwen2.5-VL-72B-Instruct 等多模态视觉模型。
"""

from typing import Any, Optional

from openai import OpenAI

from ..config import settings
from ..logger import get_logger
from .base import LLMAdapter, LLMMessage

logger = get_logger(__name__)


class QwenAdapter(LLMAdapter):
    """
    通义千问 Qwen-VL 适配器。

    基于 DashScope 兼容接口实现，使用 OpenAI SDK 发送请求。
    默认连接地址为 https://dashscope.aliyuncs.com/compatible-mode/v1。

    使用方式
    --------
    >>> adapter = QwenAdapter()
    >>> messages = [LLMMessage(role="user", content="你好")]
    >>> response = adapter.chat(messages)
    """

    CONTEXT_WINDOW_DEFAULT: int = 32000
    """Qwen-VL-Max 默认上下文窗口大小。"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        context_window: Optional[int] = None,
    ) -> None:
        """
        初始化 QwenAdapter。

        参数
        ----------
        api_key : Optional[str]
            DashScope API 密钥，未传入时从 settings.llm.api_key 读取。
        base_url : Optional[str]
            API 请求基础地址，未传入时从 settings.llm.base_url 读取。
        model_name : Optional[str]
            模型名称，未传入时从 settings.llm.model_name 读取。
        context_window : Optional[int]
            上下文窗口大小，未传入时默认为 32000。
        """
        self._api_key: str = api_key or settings.llm.api_key
        self._base_url: str = base_url or settings.llm.base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        self._model: str = model_name or settings.llm.model_name or "qwen-vl-max"
        self._context_window: int = context_window or getattr(settings.llm, "context_window", self.CONTEXT_WINDOW_DEFAULT)

        logger.info("QwenAdapter 初始化: model=%s, base_url=%s", self._model, self._base_url)

        self._client: OpenAI = OpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
        )

    @property
    def context_window(self) -> int:
        """
        返回 Qwen 模型的上下文窗口大小。

        返回
        -------
        int
            当前模型支持的上下文窗口 Token 数上限。
        """
        return self._context_window

    def chat(self, messages: list[LLMMessage], **kwargs) -> str:
        """
        向 Qwen-VL 模型发送消息并获取回复。

        将 LLMMessage 列表转换为 OpenAI SDK 兼容的消息格式后发起请求。
        支持多模态消息（文本 + 图片混合输入）。

        参数
        ----------
        messages : list[LLMMessage]
            待发送的消息列表。
        **kwargs
            可选覆盖参数：max_tokens、temperature、timeout。

        返回
        -------
        str
            模型生成的回复文本。

        异常
        ------
        openai.APIError
            API 调用失败时抛出。
        """
        openai_messages: list[dict[str, Any]] = []
        for msg in messages:
            if isinstance(msg.content, str):
                openai_messages.append({"role": msg.role, "content": msg.content})
            elif isinstance(msg.content, list):
                openai_messages.append({"role": msg.role, "content": msg.content})
            else:
                openai_messages.append({"role": msg.role, "content": str(msg.content)})

        logger.debug("QwenAdapter.chat 发送消息: %d 条, model=%s", len(openai_messages), self._model)

        response = self._client.chat.completions.create(
            model=self._model,
            messages=openai_messages,
            max_tokens=kwargs.get("max_tokens", settings.llm.max_tokens),
            temperature=kwargs.get("temperature", settings.llm.temperature),
            timeout=kwargs.get("timeout", settings.llm.request_timeout),
        )

        result: str = response.choices[0].message.content or ""
        logger.debug("QwenAdapter.chat 收到回复: %d 字符", len(result))
        return result

    def count_tokens(self, messages: list[LLMMessage]) -> int:
        """
        估算 Qwen 消息列表的 Token 消耗数。

        文本按字符数的一半估算（约 2 字符/Token），
        图片按每张 1000 Token 估算。

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
        logger.debug("QwenAdapter.count_tokens: %d 条消息共约 %d token", len(messages), total)
        return total
