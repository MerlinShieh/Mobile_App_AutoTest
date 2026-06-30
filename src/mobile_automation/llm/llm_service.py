"""
LLM 服务统一入口 —— LLMServiceFactory 工厂与 LLMService 服务类。

通过工厂模式根据配置字符串（qwen / openai / anthropic）创建对应的
Adapter 实例，LLMService 对外提供统一的 chat 和 count_tokens 接口。
"""

from typing import Optional

from ..config import settings
from ..logger import get_logger
from .base import LLMAdapter, LLMMessage
from .claude_adapter import ClaudeAdapter
from .openai_adapter import OpenAIAdapter
from .qwen_adapter import QwenAdapter
from .zhipu_adapter import ZhipuAdapter

logger = get_logger(__name__)


class LLMServiceFactory:
    """
    LLM 服务工厂。

    根据提供商名称字符串创建对应的 Adapter 实例。
    注册新的 Adapter 只需在 _adapters 字典中添加映射。

    使用方式
    --------
    >>> adapter = LLMServiceFactory.create("qwen")
    >>> adapter = LLMServiceFactory.create("openai")
    >>> adapter = LLMServiceFactory.create("anthropic")
    """

    _adapters: dict[str, type[LLMAdapter]] = {
        "qwen": QwenAdapter,
        "openai": OpenAIAdapter,
        "anthropic": ClaudeAdapter,
        "zhipu": ZhipuAdapter,
    }
    """提供商名称到 Adapter 类的映射字典。"""

    @classmethod
    def create(cls, provider: Optional[str] = None) -> LLMAdapter:
        """
        根据提供商名称创建并返回对应的 Adapter 实例。

        参数
        ----------
        provider : Optional[str]
            提供商名称，支持 "qwen" / "openai" / "anthropic"。
            为 None 时从 settings.llm.provider 读取。

        返回
        -------
        LLMAdapter
            对应提供商的 Adapter 实例。

        异常
        ------
        ValueError
            不支持的提供商名称时抛出。
        """
        provider = provider or settings.llm.provider
        adapter_cls = cls._adapters.get(provider)
        if adapter_cls is None:
            raise ValueError(
                f"不支持的 LLM 提供商: {provider}，可选: {list(cls._adapters.keys())}"
            )
        logger.info("LLMServiceFactory 创建 Adapter: provider=%s, cls=%s", provider, adapter_cls.__name__)
        return adapter_cls()

    @classmethod
    def register(cls, name: str, adapter_cls: type[LLMAdapter]) -> None:
        """
        注册新的 Adapter 类到工厂。

        参数
        ----------
        name : str
            提供商名称，如 "custom"。
        adapter_cls : type[LLMAdapter]
            适配器类，必须是 LLMAdapter 的子类。
        """
        cls._adapters[name] = adapter_cls
        logger.info("LLMServiceFactory 注册新 Adapter: name=%s, cls=%s", name, adapter_cls.__name__)


class LLMService:
    """
    LLM 服务统一入口。

    封装 LLMAdapter 的调用细节，对外提供简洁的 chat 和 count_tokens 接口。
    通过 LLMServiceFactory 在内部创建具体 Adapter 实例。

    使用方式
    --------
    >>> service = LLMService("qwen")
    >>> messages = [LLMMessage(role="user", content="你好")]
    >>> response = service.chat(messages)
    >>> tokens = service.count_tokens(messages)
    """

    def __init__(self, provider: Optional[str] = None) -> None:
        """
        初始化 LLMService。

        参数
        ----------
        provider : Optional[str]
            LLM 提供商名称，为 None 时从 settings.llm.provider 读取。
        """
        self._provider: str = provider or settings.llm.provider
        self._adapter: LLMAdapter = LLMServiceFactory.create(self._provider)
        logger.info("LLMService 初始化: provider=%s", self._provider)

    @property
    def adapter(self) -> LLMAdapter:
        """
        返回内部持有的 Adapter 实例。

        返回
        -------
        LLMAdapter
            当前使用的 Adapter 实例。
        """
        return self._adapter

    @property
    def provider(self) -> str:
        """
        返回当前使用的 LLM 提供商名称。

        返回
        -------
        str
            提供商名称，如 "qwen" / "openai" / "anthropic"。
        """
        return self._provider

    def chat(self, messages: list[LLMMessage], **kwargs) -> str:
        """
        向 LLM 发送消息并获取回复。

        参数
        ----------
        messages : list[LLMMessage]
            待发送的消息列表。
        **kwargs
            额外参数，透传给具体 Adapter 的 chat 方法。

        返回
        -------
        str
            模型生成的回复文本。
        """
        logger.debug("LLMService.chat: provider=%s, 消息数=%d", self._provider, len(messages))
        return self._adapter.chat(messages, **kwargs)

    def count_tokens(self, messages: list[LLMMessage]) -> int:
        """
        估算消息列表的 Token 消耗数。

        参数
        ----------
        messages : list[LLMMessage]
            待估算的消息列表。

        返回
        -------
        int
            估算的 Token 总数。
        """
        return self._adapter.count_tokens(messages)
