"""LLM 服务模块测试。

测试 LLMServiceFactory 的创建、LLMService 统一入口和 mock Adapter 的行为。
"""

import pytest

from mobile_automation.llm.base import LLMAdapter, LLMMessage
from mobile_automation.llm.llm_service import LLMService, LLMServiceFactory


class TestLLMServiceFactory:
    """测试 LLMServiceFactory 的创建逻辑。"""

    def test_create_qwen_adapter(self, mocker):
        """验证创建 qwen 适配器。"""
        mock_adapter = mocker.MagicMock(spec=LLMAdapter)
        mocker.patch.object(LLMServiceFactory, "_adapters", {"qwen": lambda: mock_adapter})
        adapter = LLMServiceFactory.create("qwen")
        assert adapter == mock_adapter

    def test_create_openai_adapter(self, mocker):
        """验证创建 openai 适配器。"""
        mock_adapter = mocker.MagicMock(spec=LLMAdapter)
        mocker.patch.object(LLMServiceFactory, "_adapters", {"openai": lambda: mock_adapter})
        adapter = LLMServiceFactory.create("openai")
        assert adapter == mock_adapter

    def test_create_anthropic_adapter(self, mocker):
        """验证创建 anthropic 适配器。"""
        mock_adapter = mocker.MagicMock(spec=LLMAdapter)
        mocker.patch.object(LLMServiceFactory, "_adapters", {"anthropic": lambda: mock_adapter})
        adapter = LLMServiceFactory.create("anthropic")
        assert adapter == mock_adapter

    def test_create_invalid_provider_raises(self):
        """验证不支持的提供商抛出异常。"""
        with pytest.raises(ValueError, match="不支持的 LLM 提供商"):
            LLMServiceFactory.create("invalid_provider")

    def test_create_with_none_uses_settings(self, mocker):
        """验证 provider=None 时使用配置的默认值。"""
        mock_adapter = mocker.MagicMock(spec=LLMAdapter)
        mocker.patch.object(LLMServiceFactory, "_adapters", {"qwen": lambda: mock_adapter})
        mocker.patch("mobile_automation.llm.llm_service.settings.llm.provider", "qwen")
        adapter = LLMServiceFactory.create()
        assert adapter == mock_adapter

    def test_register_custom_adapter(self, mocker):
        """验证注册自定义 Adapter。"""
        class MockAdapter(LLMAdapter):
            def chat(self, messages, **kwargs):
                return "mock"
            def count_tokens(self, messages):
                return 0
            @property
            def context_window(self):
                return 1000

        LLMServiceFactory.register("custom", MockAdapter)
        adapter = LLMServiceFactory.create("custom")
        assert isinstance(adapter, MockAdapter)

    def test_register_replaces_existing(self, mocker):
        """验证重复注册同名 Adapter 覆盖。"""
        class AdapterA(LLMAdapter):
            def chat(self, messages, **kwargs): return "A"
            def count_tokens(self, messages): return 0
            @property
            def context_window(self): return 1000

        class AdapterB(LLMAdapter):
            def chat(self, messages, **kwargs): return "B"
            def count_tokens(self, messages): return 0
            @property
            def context_window(self): return 1000

        LLMServiceFactory.register("test", AdapterA)
        LLMServiceFactory.register("test", AdapterB)
        adapter = LLMServiceFactory.create("test")
        assert isinstance(adapter, AdapterB)


class TestLLMService:
    """测试 LLMService 统一入口。"""

    def test_initialization_with_provider(self, mocker):
        """验证指定提供商初始化。"""
        mock_adapter = mocker.MagicMock(spec=LLMAdapter)
        mocker.patch.object(LLMServiceFactory, "create", return_value=mock_adapter)

        service = LLMService("qwen")
        assert service.provider == "qwen"
        assert service.adapter == mock_adapter

    def test_initialization_default_provider(self, mocker):
        """验证未指定提供商时使用配置默认值。"""
        mock_adapter = mocker.MagicMock(spec=LLMAdapter)
        mocker.patch.object(LLMServiceFactory, "create", return_value=mock_adapter)
        mocker.patch("mobile_automation.llm.llm_service.settings.llm.provider", "qwen")

        service = LLMService()
        assert service.provider == "qwen"

    def test_chat_delegates_to_adapter(self, mocker):
        """验证 chat 委托给 Adapter。"""
        mock_adapter = mocker.MagicMock(spec=LLMAdapter)
        mock_adapter.chat.return_value = "response text"
        mocker.patch.object(LLMServiceFactory, "create", return_value=mock_adapter)

        service = LLMService("qwen")
        messages = [LLMMessage(role="user", content="hello")]
        result = service.chat(messages, temperature=0.5)
        assert result == "response text"
        mock_adapter.chat.assert_called_with(messages, temperature=0.5)

    def test_count_tokens_delegates_to_adapter(self, mocker):
        """验证 count_tokens 委托给 Adapter。"""
        mock_adapter = mocker.MagicMock(spec=LLMAdapter)
        mock_adapter.count_tokens.return_value = 42
        mocker.patch.object(LLMServiceFactory, "create", return_value=mock_adapter)

        service = LLMService("qwen")
        messages = [LLMMessage(role="user", content="hello")]
        result = service.count_tokens(messages)
        assert result == 42
        mock_adapter.count_tokens.assert_called_with(messages)

    def test_adapter_property(self, mocker):
        """验证 adapter 属性返回内部实例。"""
        mock_adapter = mocker.MagicMock(spec=LLMAdapter)
        mocker.patch.object(LLMServiceFactory, "create", return_value=mock_adapter)

        service = LLMService("qwen")
        assert service.adapter is mock_adapter

    def test_provider_property(self, mocker):
        """验证 provider 属性返回正确值。"""
        mock_adapter = mocker.MagicMock(spec=LLMAdapter)
        mocker.patch.object(LLMServiceFactory, "create", return_value=mock_adapter)

        service = LLMService("openai")
        assert service.provider == "openai"
