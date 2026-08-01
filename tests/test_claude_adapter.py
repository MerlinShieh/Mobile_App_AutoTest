"""Anthropic Claude 适配器测试。

测试 ClaudeAdapter 的初始化、消息组织、thinking 块防御和 close 方法。
所有外部 API 调用均通过 mock 隔离。
"""

import pytest

from mobile_automation.exception import LLMServiceError
from mobile_automation.llm.base import LLMMessage
from mobile_automation.llm.claude_adapter import ClaudeAdapter


class TestClaudeAdapterInit:
    """测试 ClaudeAdapter 初始化。"""

    def test_init_with_provider_config(self, mocker):
        """验证 provider 配置存在时使用其配置。"""
        mocker.patch("mobile_automation.llm.claude_adapter.settings.models.providers", {
            "anthropic": mocker.MagicMock(api_key="test-key", base_url="https://api.anthropic.com"),
        })
        mocker.patch("mobile_automation.llm.claude_adapter.settings.models.models", {
            "claude": mocker.MagicMock(provider="anthropic", model_name="claude-3-5-sonnet", context_window=200000),
        })
        mock_client = mocker.patch("mobile_automation.llm.claude_adapter.Anthropic")
        adapter = ClaudeAdapter()
        assert adapter._api_key == "test-key"
        assert adapter._model == "claude-3-5-sonnet"

    def test_init_missing_api_key_raises(self, mocker):
        """验证 API Key 为空时初始化抛出 ValueError。"""
        mocker.patch("mobile_automation.llm.claude_adapter.settings.models.providers", {
            "anthropic": mocker.MagicMock(api_key="", base_url="https://api.anthropic.com"),
        })
        mocker.patch("mobile_automation.llm.claude_adapter.settings.models.models", {})
        with pytest.raises(ValueError, match="API Key"):
            ClaudeAdapter()


class TestClaudeAdapterChat:
    """测试 ClaudeAdapter.chat 消息组织与响应提取。"""

    def _make_adapter(self, mocker):
        mocker.patch("mobile_automation.llm.claude_adapter.settings.models.providers", {
            "anthropic": mocker.MagicMock(api_key="test-key", base_url="https://api.anthropic.com"),
        })
        mocker.patch("mobile_automation.llm.claude_adapter.settings.models.models", {})
        mock_client = mocker.patch("mobile_automation.llm.claude_adapter.Anthropic")
        return ClaudeAdapter(), mock_client

    def test_chat_extracts_text_block(self, mocker):
        """验证响应中的 TextBlock 文本被正确提取。"""
        adapter, mock_client = self._make_adapter(mocker)
        text_block = mocker.MagicMock()
        text_block.type = "text"
        text_block.text = "你好，Claude"
        mock_response = mocker.MagicMock()
        mock_response.content = [text_block]
        mock_client.return_value.messages.create.return_value = mock_response

        messages = [LLMMessage(role="user", content="你好")]
        result = adapter.chat(messages)
        assert result == "你好，Claude"

    def test_chat_handles_thinking_block(self, mocker):
        """验证 thinking 块（无 text 属性）不会导致崩溃。"""
        adapter, mock_client = self._make_adapter(mocker)
        thinking_block = mocker.MagicMock()
        thinking_block.type = "thinking"
        # 故意不设置 text 属性，模拟 ThinkingBlock 无 text 字段
        del thinking_block.text
        text_block = mocker.MagicMock()
        text_block.type = "text"
        text_block.text = "最终答案"
        mock_response = mocker.MagicMock()
        mock_response.content = [thinking_block, text_block]
        mock_client.return_value.messages.create.return_value = mock_response

        messages = [LLMMessage(role="user", content="你好")]
        result = adapter.chat(messages)
        assert result == "最终答案"

    def test_chat_empty_content_returns_empty(self, mocker):
        """验证响应无内容块时返回空字符串而非崩溃。"""
        adapter, mock_client = self._make_adapter(mocker)
        mock_response = mocker.MagicMock()
        mock_response.content = []
        mock_client.return_value.messages.create.return_value = mock_response

        messages = [LLMMessage(role="user", content="你好")]
        result = adapter.chat(messages)
        assert result == ""

    def test_chat_api_error_wrapped(self, mocker):
        """验证 API 异常被包装为 LLMServiceError。"""
        from anthropic import APIError
        adapter, mock_client = self._make_adapter(mocker)
        mock_client.return_value.messages.create.side_effect = APIError(
            "request failed",
            request=mocker.MagicMock(),
            body=mocker.MagicMock(),
        )

        messages = [LLMMessage(role="user", content="你好")]
        with pytest.raises(LLMServiceError, match="Claude API"):
            adapter.chat(messages)


class TestClaudeAdapterClose:
    """测试 ClaudeAdapter.close 资源释放。"""

    def test_close_calls_client_close(self, mocker):
        """验证 close() 调用底层 Anthropic client.close()。"""
        mocker.patch("mobile_automation.llm.claude_adapter.settings.models.providers", {
            "anthropic": mocker.MagicMock(api_key="test-key", base_url="https://api.anthropic.com"),
        })
        mocker.patch("mobile_automation.llm.claude_adapter.settings.models.models", {})
        mock_client = mocker.patch("mobile_automation.llm.claude_adapter.Anthropic")
        adapter = ClaudeAdapter()
        adapter.close()
        mock_client.return_value.close.assert_called_once()
