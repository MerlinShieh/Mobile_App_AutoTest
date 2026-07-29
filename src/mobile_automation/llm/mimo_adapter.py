"""
小米 MiMo V2.5 适配器 —— 通过 OpenAI 兼容接口调用。

MiMo API 完全兼容 OpenAI 协议，使用 OpenAI SDK 即可对接。
支持 mimo-v2.5（多模态）和 mimo-v2.5-pro（纯文本旗舰）等模型。
"""

from typing import Any, Optional

from openai import OpenAI

from ..config import settings
from ..logger import get_logger
from .base import LLMAdapter, LLMMessage

logger = get_logger(__name__)


class MiMoAdapter(LLMAdapter):
    """
    小米 MiMo V2.5 适配器。

    通过 OpenAI SDK 连接 MiMo API（https://api.xiaomimimo.com/v1）。
    支持多模态输入（文本 + 图片），MiMo 特有的 reasoning_content
    字段会与 content 拼接后返回。

    使用方式
    --------
    >>> adapter = MiMoAdapter()
    >>> messages = [LLMMessage(role="user", content="你好")]
    >>> response = adapter.chat(messages)
    """

    CONTEXT_WINDOW_DEFAULT: int = 128000
    """MiMo V2.5 默认上下文窗口大小（omni 模型 128K）。"""

    def __init__(self, provider: Optional[str] = None) -> None:
        """
        初始化 MiMoAdapter。

        优先从 settings.models.providers 读取配置（多模型架构），
        未找到时回退到 settings.llm（向后兼容）。

        参数
        ----------
        provider : Optional[str]
            提供商名称，默认 "mimo"。
        """
        self._provider_name: str = provider or "mimo"
        provider_cfg = settings.models.providers.get(self._provider_name)

        if provider_cfg:
            self._api_key: str = provider_cfg.api_key
            self._base_url: str = provider_cfg.base_url or "https://api.xiaomimimo.com/v1"
        else:
            self._api_key = settings.llm.api_key
            self._base_url = settings.llm.base_url or "https://api.xiaomimimo.com/v1"

        # 从模型注册表查找本 provider 的第一个模型
        self._model: str = "mimo-v2.5"
        self._context_window: int = self.CONTEXT_WINDOW_DEFAULT
        for model_entry in settings.models.models.values():
            if model_entry.provider == self._provider_name:
                self._model = model_entry.model_name or self._model
                self._context_window = model_entry.context_window or self._context_window
                break

        logger.info("MiMoAdapter 初始化: model=%s, base_url=%s", self._model, self._base_url)

        self._client: OpenAI = OpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
        )

    @property
    def context_window(self) -> int:
        """返回当前 MiMo 模型的上下文窗口大小。"""
        return self._context_window

    def chat(self, messages: list[LLMMessage], **kwargs) -> str:
        """
        向 MiMo 模型发送消息并获取回复。

        MiMo 特有的 reasoning_content 字段会与 content 拼接返回，
        确保 CoT 思维链推理内容不丢失。

        参数
        ----------
        messages : list[LLMMessage]
            待发送的消息列表，支持多模态（文本 + 图片）。
        **kwargs
            可选覆盖参数：max_tokens、temperature、timeout。

        返回
        -------
        str
            模型生成的回复文本（含 reasoning_content 拼接）。
        """
        openai_messages: list[dict[str, Any]] = []
        for msg in messages:
            if isinstance(msg.content, (str, list)):
                openai_messages.append({"role": msg.role, "content": msg.content})
            else:
                openai_messages.append({"role": msg.role, "content": str(msg.content)})

        logger.debug("MiMoAdapter.chat 发送消息: %d 条, model=%s", len(openai_messages), self._model)

        response = self._client.chat.completions.create(
            model=self._model,
            messages=openai_messages,
            max_tokens=kwargs.get("max_tokens", settings.llm.max_tokens),
            temperature=kwargs.get("temperature", settings.llm.temperature),
            timeout=kwargs.get("timeout", settings.llm.request_timeout),
        )

        message = response.choices[0].message
        content: str = message.content or ""

        # MiMo 的 reasoning_content（思维链）与 content 拼接
        reasoning = getattr(message, "reasoning_content", None)
        if reasoning:
            content = f"<think>{reasoning}</think>\n{content}" if content else f"<think>{reasoning}</think>"

        logger.debug("MiMoAdapter.chat 收到回复: %d 字符", len(content))
        return content

    def count_tokens(self, messages: list[LLMMessage]) -> int:
        """
        估算 MiMo 消息列表的 Token 消耗数。

        文本按字符数的一半估算，图片按 Base64 长度估算。

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
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            total += len(item.get("text", "")) // 2
                        elif item.get("type") == "image_url":
                            total += self._estimate_image_tokens(item)
        logger.debug("MiMoAdapter.count_tokens: %d 条消息共约 %d token", len(messages), total)
        return total

    @staticmethod
    def _estimate_image_tokens(item: dict) -> int:
        """基于 Base64 数据长度估算图片 Token 消耗。"""
        image_url = item.get("image_url", {}) if isinstance(item, dict) else {}
        url = image_url.get("url", "") if isinstance(image_url, dict) else ""
        if not isinstance(url, str) or not url.startswith("data:image/"):
            return 1000
        base64_part = url.split(",", 1)[-1] if "," in url else url
        file_bytes = len(base64_part) * 3 // 4
        if file_bytes < 1000:
            return 85
        pixel_est = int(file_bytes * 8 / 2.5)
        side = int(pixel_est ** 0.5)
        tiles_x = max(1, (side + 511) // 512)
        tiles_y = max(1, (side + 511) // 512)
        return tiles_x * tiles_y * 170 + 85
