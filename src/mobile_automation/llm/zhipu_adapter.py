"""
智谱 GLM-4V 适配器 —— 调用智谱开放平台 API。

使用 OpenAI SDK 连接智谱开放平台（https://open.bigmodel.cn/api/paas/v4/），
支持 GLM-4.1V-Thinking-Flash 等多模态视觉模型。
"""

from typing import Any, Optional

from openai import APIError, OpenAI

from ..config import settings
from ..exception import LLMServiceError
from ..logger import get_logger
from .base import LLMAdapter, LLMMessage

logger = get_logger(__name__)


class ZhipuAdapter(LLMAdapter):
    """
    智谱 GLM-4V 适配器。

    通过 OpenAI SDK 调用智谱开放平台的 OpenAI 兼容接口。
    支持多模态输入，构造函数支持依赖注入所有配置项。

    使用方式
    --------
    >>> adapter = ZhipuAdapter()
    >>> messages = [LLMMessage(role="user", content="描述这张图片")]
    >>> response = adapter.chat(messages)
    """

    CONTEXT_WINDOW_DEFAULT: int = 128000
    """GLM-4V 系列模型默认上下文窗口大小。"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> None:
        """
        初始化 ZhipuAdapter。

        参数
        ----------
        api_key : Optional[str]
            智谱 API 密钥，未传入时从 settings.llm.api_key 读取。
        base_url : Optional[str]
            API 请求基础地址，未传入时从 settings.llm.base_url 读取。
        model_name : Optional[str]
            模型名称，未传入时从 settings.llm.model_name 读取。
        """
        self._api_key: str = api_key or settings.llm.api_key
        self._base_url: str = base_url or settings.llm.base_url or "https://open.bigmodel.cn/api/paas/v4/"
        self._model: str = model_name or settings.llm.model_name or "glm-4.1v-thinking-flash"

        if not self._api_key:
            raise ValueError(
                "智谱 API Key 未配置。请在 .env 中设置 LLM_API_KEY 或 "
                "MODELS__PROVIDERS__ZHIPU__API_KEY。"
            )

        logger.info("ZhipuAdapter 初始化: model=%s, base_url=%s", self._model, self._base_url)

        self._client: OpenAI = OpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
        )

    @property
    def context_window(self) -> int:
        """
        返回 GLM-4V 模型的上下文窗口大小。

        返回
        -------
        int
            固定值 128000 Token。
        """
        return self.CONTEXT_WINDOW_DEFAULT

    def chat(self, messages: list[LLMMessage], **kwargs) -> str:
        """
        向智谱模型发送消息并获取回复。

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
        openai_messages: list[dict[str, Any]] = [
            {"role": m.role, "content": m.content} for m in messages
        ]

        logger.debug("ZhipuAdapter.chat 发送消息: %d 条, model=%s", len(openai_messages), self._model)

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=openai_messages,
                max_tokens=kwargs.get("max_tokens", settings.llm.max_tokens),
                temperature=kwargs.get("temperature", settings.llm.temperature),
                timeout=kwargs.get("timeout", settings.llm.request_timeout),
            )
        except APIError as exc:
            logger.error("智谱 API 调用失败: %s", exc)
            raise LLMServiceError(f"智谱 API 调用失败: {exc}", provider="zhipu") from exc
        except Exception as exc:
            logger.error("智谱调用发生未知异常: %s", exc)
            raise LLMServiceError(f"智谱调用异常: {exc}", provider="zhipu") from exc

        if not response.choices:
            raise LLMServiceError("智谱 API 返回空响应（无 choices）", provider="zhipu")

        result: str = response.choices[0].message.content or ""
        logger.debug("ZhipuAdapter.chat 收到回复: %d 字符", len(result))
        return result
