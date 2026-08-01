"""
OpenAI GPT-4o 适配器 —— 调用 OpenAI 标准 API。

使用 OpenAI SDK 连接 OpenAI 官方 API 端点，支持 GPT-4o 等视觉模型，
作为 Qwen 之外的可选备选 LLM 提供商。
"""

from typing import Any, Optional

from openai import APIError, OpenAI

from ..config import settings
from ..exception import LLMServiceError
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
        provider: Optional[str] = None,
    ) -> None:
        """
        初始化 OpenAIAdapter。

        优先从 settings.models.providers 读取配置（多模型架构），
        未找到时回退到 settings.llm（向后兼容）。

        参数
        ----------
        api_key : Optional[str]
            API 密钥，未传入时从配置读取。
        base_url : Optional[str]
            API 请求基础地址，未传入时从配置读取。
        model_name : Optional[str]
            模型名称，未传入时从配置读取。
        provider : Optional[str]
            提供商名称，用于从 settings.models.providers 查找配置。
        """
        provider_cfg = settings.models.providers.get(provider or "") if provider else None
        if provider_cfg:
            self._api_key: str = api_key or provider_cfg.api_key
            self._base_url: str = base_url or provider_cfg.base_url
            # 从模型注册表查找该 provider 的模型名称
            self._model: str = model_name or ""
            if not self._model:
                for model_entry in settings.models.models.values():
                    if model_entry.provider == provider:
                        self._model = model_entry.model_name
                        break
            if not self._model:
                self._model = "gpt-4o"
        else:
            self._api_key = api_key or settings.llm.api_key
            self._base_url = base_url or settings.llm.base_url
            self._model = model_name or settings.llm.model_name or "gpt-4o"

        logger.info("OpenAIAdapter 初始化: model=%s, base_url=%s", self._model, self._base_url)

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

        # 注意：不校验 API Key 空值——local provider（本地 llama-server）
        # 复用本适配器且无需认证，空 Key 是合法场景。
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=openai_messages,
                max_tokens=kwargs.get("max_tokens", settings.llm.max_tokens),
                temperature=kwargs.get("temperature", settings.llm.temperature),
                timeout=kwargs.get("timeout", settings.llm.request_timeout),
            )
        except APIError as exc:
            logger.error("OpenAI API 调用失败: %s", exc)
            raise LLMServiceError(f"OpenAI API 调用失败: {exc}", provider="openai") from exc
        except Exception as exc:
            logger.error("OpenAI 调用发生未知异常: %s", exc)
            raise LLMServiceError(f"OpenAI 调用异常: {exc}", provider="openai") from exc

        if not response.choices:
            raise LLMServiceError("OpenAI API 返回空响应（无 choices）", provider="openai")

        result: str = response.choices[0].message.content or ""
        logger.debug("OpenAIAdapter.chat 收到回复: %d 字符", len(result))
        return result

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
            logger.debug("OpenAIAdapter.close 异常（忽略）: %s", exc)
