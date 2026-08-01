"""
Anthropic Claude 适配器 —— 调用 Anthropic Messages API。

使用 Anthropic SDK 连接 Claude 系列模型（如 Claude 3.5 Sonnet），
支持 system 角色独立传输和多模态内容输入。
"""

from typing import Any, Optional

from anthropic import Anthropic, APIError as AnthropicAPIError

from ..config import settings
from ..exception import LLMServiceError
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
        provider: Optional[str] = None,
    ) -> None:
        """
        初始化 ClaudeAdapter。

        优先从 settings.models.providers["anthropic"] 读取配置（多模型架构），
        未配置时回退到 settings.llm（向后兼容旧架构）。

        参数
        ----------
        api_key : Optional[str]
            Anthropic API 密钥，未传入时从配置读取。
        model_name : Optional[str]
            模型名称，未传入时从配置读取，
            默认值为 "claude-3-5-sonnet-20241022"。
        provider : Optional[str]
            提供商名称，默认 "anthropic"。
        """
        provider_name = provider or "anthropic"
        provider_cfg = settings.models.providers.get(provider_name)

        if provider_cfg:
            self._api_key: str = api_key or provider_cfg.api_key
            # 从模型注册表查找本 provider 的第一个模型
            self._model: str = model_name or ""
            for model_entry in settings.models.models.values():
                if model_entry.provider == provider_name:
                    self._model = self._model or model_entry.model_name
                    break
            self._model = self._model or "claude-3-5-sonnet-20241022"
        else:
            self._api_key = api_key or settings.llm.api_key
            self._model = model_name or settings.llm.model_name or "claude-3-5-sonnet-20241022"

        if not self._api_key:
            raise ValueError(
                "Anthropic API Key 未配置。请在 .env 中设置 LLM_API_KEY 或 "
                "MODELS__PROVIDERS__ANTHROPIC__API_KEY。"
            )

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

        try:
            response = self._client.messages.create(
                model=self._model,
                system=system_content or None,
                messages=chat_messages,
                max_tokens=kwargs.get("max_tokens", settings.llm.max_tokens),
                temperature=kwargs.get("temperature", settings.llm.temperature),
                timeout=kwargs.get("timeout", settings.llm.request_timeout),
            )
        except AnthropicAPIError as exc:
            logger.error("Claude API 调用失败: %s", exc)
            raise LLMServiceError(f"Claude API 调用失败: {exc}", provider="anthropic") from exc
        except Exception as exc:
            logger.error("Claude 调用发生未知异常: %s", exc)
            raise LLMServiceError(f"Claude 调用异常: {exc}", provider="anthropic") from exc

        result: str = response.content[0].text if response.content else ""
        logger.debug("ClaudeAdapter.chat 收到回复: %d 字符", len(result))
        return result

    def close(self) -> None:
        """
        释放 Anthropic SDK client 的底层连接池资源。

        返回
        ------
        None
        """
        try:
            self._client.close()
        except Exception as exc:
            logger.debug("ClaudeAdapter.close 异常（忽略）: %s", exc)
