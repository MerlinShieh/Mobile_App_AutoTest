"""小米 MiMo V2.5 适配器测试。

测试 MiMoAdapter 的初始化、chat 方法（含 reasoning_content 拼接）
和 Token 估算功能。所有外部 API 调用均通过 mock 隔离。
"""

import pytest

from mobile_automation.exception import LLMServiceError
from mobile_automation.llm.base import LLMMessage
from mobile_automation.llm.mimo_adapter import MiMoAdapter


class TestMiMoAdapterInit:
    """测试 MiMoAdapter 初始化。"""

    def test_init_with_default_config(self, mocker):
        """验证默认配置初始化。"""
        mocker.patch("mobile_automation.llm.mimo_adapter.settings.models.providers", {
            "mimo": mocker.MagicMock(api_key="test-key", base_url="https://api.xiaomimimo.com/v1"),
        })
        mocker.patch("mobile_automation.llm.mimo_adapter.settings.models.models", {
            "mimo-omni": mocker.MagicMock(provider="mimo", model_name="mimo-v2.5", context_window=128000),
        })
        mock_openai = mocker.patch("mobile_automation.llm.mimo_adapter.OpenAI")
        adapter = MiMoAdapter()
        assert adapter._model == "mimo-v2.5"
        assert adapter._base_url == "https://api.xiaomimimo.com/v1"
        assert adapter.context_window == 128000

    def test_init_fallback_to_llm_settings(self, mocker):
        """验证 provider 未配置时回退到 settings.llm。"""
        mocker.patch("mobile_automation.llm.mimo_adapter.settings.models.providers", {})
        mocker.patch("mobile_automation.llm.mimo_adapter.settings.models.models", {})
        mocker.patch("mobile_automation.llm.mimo_adapter.settings.llm.api_key", "fallback-key")
        mocker.patch("mobile_automation.llm.mimo_adapter.settings.llm.base_url", "https://fallback.com/v1")
        mock_openai = mocker.patch("mobile_automation.llm.mimo_adapter.OpenAI")
        adapter = MiMoAdapter()
        assert adapter._api_key == "fallback-key"
        assert adapter._base_url == "https://fallback.com/v1"

    def test_init_missing_api_key_raises(self, mocker):
        """验证 API Key 为空时初始化抛出 ValueError。"""
        mocker.patch("mobile_automation.llm.mimo_adapter.settings.models.providers", {
            "mimo": mocker.MagicMock(api_key="", base_url="https://api.xiaomimimo.com/v1"),
        })
        mocker.patch("mobile_automation.llm.mimo_adapter.settings.models.models", {
            "mimo-omni": mocker.MagicMock(provider="mimo", model_name="mimo-v2.5", context_window=128000),
        })
        mocker.patch("mobile_automation.llm.mimo_adapter.OpenAI")
        with pytest.raises(ValueError, match="API Key"):
            MiMoAdapter()


class TestMiMoAdapterChat:
    """测试 MiMoAdapter.chat 方法。"""

    def _make_adapter(self, mocker):
        """创建一个带 mock client 的 adapter 实例。"""
        mocker.patch("mobile_automation.llm.mimo_adapter.settings.models.providers", {
            "mimo": mocker.MagicMock(api_key="test-key", base_url="https://api.xiaomimimo.com/v1"),
        })
        mocker.patch("mobile_automation.llm.mimo_adapter.settings.models.models", {
            "mimo-omni": mocker.MagicMock(provider="mimo", model_name="mimo-v2.5", context_window=128000),
        })
        mock_openai = mocker.patch("mobile_automation.llm.mimo_adapter.OpenAI")
        adapter = MiMoAdapter()
        return adapter, mock_openai

    def test_chat_basic(self, mocker):
        """验证基本 chat 调用。"""
        adapter, mock_openai = self._make_adapter(mocker)
        mock_response = mocker.MagicMock()
        mock_response.choices = [mocker.MagicMock(message=mocker.MagicMock(
            content="Hello!", reasoning_content=None,
        ))]
        mock_openai.return_value.chat.completions.create.return_value = mock_response

        messages = [LLMMessage(role="user", content="hi")]
        result = adapter.chat(messages)
        assert result == "Hello!"

    def test_chat_with_reasoning_content(self, mocker):
        """验证 reasoning_content 与 content 拼接。"""
        adapter, mock_openai = self._make_adapter(mocker)
        mock_response = mocker.MagicMock()
        mock_response.choices = [mocker.MagicMock(message=mocker.MagicMock(
            content="The answer is 42.",
            reasoning_content="Let me think... 6*7=42",
        ))]
        mock_openai.return_value.chat.completions.create.return_value = mock_response

        messages = [LLMMessage(role="user", content="what is 6*7?")]
        result = adapter.chat(messages)
        assert "<think>" in result
        assert "Let me think... 6*7=42" in result
        assert "The answer is 42." in result

    def test_chat_reasoning_only_no_content(self, mocker):
        """验证仅有 reasoning_content 无 content 时的处理。"""
        adapter, mock_openai = self._make_adapter(mocker)
        mock_response = mocker.MagicMock()
        mock_response.choices = [mocker.MagicMock(message=mocker.MagicMock(
            content="",
            reasoning_content="thinking...",
        ))]
        mock_openai.return_value.chat.completions.create.return_value = mock_response

        messages = [LLMMessage(role="user", content="hi")]
        result = adapter.chat(messages)
        assert result == "<think>thinking...</think>"

    def test_chat_multimodal_content(self, mocker):
        """验证多模态消息（文本+图片）传递。"""
        adapter, mock_openai = self._make_adapter(mocker)
        mock_response = mocker.MagicMock()
        mock_response.choices = [mocker.MagicMock(message=mocker.MagicMock(
            content="green", reasoning_content=None,
        ))]
        mock_openai.return_value.chat.completions.create.return_value = mock_response

        messages = [LLMMessage(role="user", content=[
            {"type": "text", "text": "what color?"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
        ])]
        result = adapter.chat(messages)
        assert result == "green"

    def test_chat_api_error_wrapped(self, mocker):
        """验证 openai APIError 被包装为 LLMServiceError。

        conftest 为 mock 的 openai 模块注入了真实/虚拟 APIError 类，
        因此可以在此构造 APIError 实例触发适配器的特定捕获分支。
        """
        from openai import APIError

        adapter, mock_openai = self._make_adapter(mocker)
        mock_openai.return_value.chat.completions.create.side_effect = APIError(
            "connection timeout", request=None, body=None
        )

        messages = [LLMMessage(role="user", content="hi")]
        with pytest.raises(LLMServiceError, match="MiMo API 调用失败"):
            adapter.chat(messages)

    def test_chat_empty_choices_raises(self, mocker):
        """验证 API 返回空 choices 时抛出 LLMServiceError。"""
        adapter, mock_openai = self._make_adapter(mocker)
        mock_openai.return_value.chat.completions.create.return_value = mocker.MagicMock(choices=[])

        messages = [LLMMessage(role="user", content="hi")]
        with pytest.raises(LLMServiceError, match="空响应"):
            adapter.chat(messages)


class TestMiMoAdapterCountTokens:
    """测试 MiMoAdapter Token 估算。"""

    def test_count_tokens_text_only(self, mocker):
        """验证纯文本 Token 估算。"""
        mocker.patch("mobile_automation.llm.mimo_adapter.settings.models.providers", {
            "mimo": mocker.MagicMock(api_key="test-key", base_url="https://api.xiaomimimo.com/v1"),
        })
        mocker.patch("mobile_automation.llm.mimo_adapter.settings.models.models", {})
        mock_openai = mocker.patch("mobile_automation.llm.mimo_adapter.OpenAI")
        adapter = MiMoAdapter()

        messages = [LLMMessage(role="user", content="Hello World")]
        tokens = adapter.count_tokens(messages)
        assert tokens == len("Hello World") // 2

    def test_count_tokens_with_image(self, mocker):
        """验证含图片消息 Token 估算。"""
        mocker.patch("mobile_automation.llm.mimo_adapter.settings.models.providers", {
            "mimo": mocker.MagicMock(api_key="test-key", base_url="https://api.xiaomimimo.com/v1"),
        })
        mocker.patch("mobile_automation.llm.mimo_adapter.settings.models.models", {})
        mock_openai = mocker.patch("mobile_automation.llm.mimo_adapter.OpenAI")
        adapter = MiMoAdapter()

        messages = [LLMMessage(role="user", content=[
            {"type": "text", "text": "describe"},
            {"type": "image_url", "image_url": {"url": "https://example.com/photo.jpg"}},
        ])]
        tokens = adapter.count_tokens(messages)
        assert tokens > len("describe") // 2
