"""
小米 MiMo V2.5 适配器 —— 通过 OpenAI 兼容接口调用。

MiMo API 完全兼容 OpenAI 协议，使用 OpenAI SDK 即可对接。
支持 mimo-v2.5（多模态）和 mimo-v2.5-pro（纯文本旗舰）等模型。
"""

from typing import Any, Optional

from openai import APIError, OpenAI

from ..config import settings
from ..exception import LLMServiceError
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

        if not self._api_key:
            raise ValueError(
                "MiMo API Key 未配置。请在 .env 中设置 LLM_API_KEY 或 "
                "MODELS__PROVIDERS__MIMO__API_KEY。"
            )

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

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=openai_messages,
                max_tokens=kwargs.get("max_tokens", settings.llm.max_tokens),
                temperature=kwargs.get("temperature", settings.llm.temperature),
                timeout=kwargs.get("timeout", settings.llm.request_timeout),
            )
        except APIError as exc:
            logger.error("MiMo API 调用失败: %s", exc)
            raise LLMServiceError(f"MiMo API 调用失败: {exc}", provider="mimo") from exc
        except Exception as exc:
            logger.error("MiMo 调用发生未知异常: %s", exc)
            raise LLMServiceError(f"MiMo 调用异常: {exc}", provider="mimo") from exc

        if not response.choices:
            raise LLMServiceError("MiMo API 返回空响应（无 choices）", provider="mimo")

        message = response.choices[0].message
        content: str = message.content or ""

        # MiMo 的 reasoning_content（思维链）与 content 拼接
        # 仅在 enable_reasoning=True 时捕获，避免图片推理耗时过长
        if settings.models.enable_reasoning:
            reasoning = getattr(message, "reasoning_content", None)
            if reasoning:
                content = f"<think>{reasoning}</think>\n{content}" if content else f"<think>{reasoning}</think>"

        logger.debug("MiMoAdapter.chat 收到回复: %d 字符", len(content))
        return content

    def close(self) -> None:
        """
        释放 OpenAI SDK client 的底层连接池资源。

        返回
        ------
        None
        """
        try:
            self._client.close()
        except Exception as exc:
            logger.debug("MiMoAdapter.close 异常（忽略）: %s", exc)
