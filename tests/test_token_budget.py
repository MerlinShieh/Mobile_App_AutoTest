"""Token 预算管理模块测试。

测试 TokenBudgetManager 的预算计算、Token 跟踪、压缩策略建议和重置功能。
"""

import pytest

from mobile_automation.llm.base import LLMMessage
from mobile_automation.llm.token_budget import TokenBudgetManager


class TestTokenBudgetManager:
    """测试 TokenBudgetManager 的预算管理功能。"""

    def test_initial_budget_for_qwen(self, monkeypatch):
        """验证 Qwen 模型的初始预算（32000 - 4096 = 27904）。"""
        monkeypatch.setattr("mobile_automation.llm.token_budget.settings.llm.max_tokens", 4096)
        manager = TokenBudgetManager("qwen")
        assert manager.max_context == 32000
        assert manager.input_budget == 32000 - 4096

    def test_initial_budget_for_openai(self, monkeypatch):
        """验证 OpenAI 模型的初始预算（128000 - 4096）。"""
        monkeypatch.setattr("mobile_automation.llm.token_budget.settings.llm.max_tokens", 4096)
        manager = TokenBudgetManager("openai")
        assert manager.max_context == 128000

    def test_initial_budget_for_anthropic(self, monkeypatch):
        """验证 Anthropic 模型的初始预算（200000 - 4096）。"""
        monkeypatch.setattr("mobile_automation.llm.token_budget.settings.llm.max_tokens", 4096)
        manager = TokenBudgetManager("anthropic")
        assert manager.max_context == 200000

    def test_get_available_budget_full(self, monkeypatch):
        """验证未消耗时可用预算等于输入预算。"""
        monkeypatch.setattr("mobile_automation.llm.token_budget.settings.llm.max_tokens", 4096)
        manager = TokenBudgetManager("qwen")
        assert manager.get_available_budget() == manager.input_budget

    def test_get_available_budget_partial(self, monkeypatch):
        """验证消耗部分 Token 后可用预算减少。"""
        monkeypatch.setattr("mobile_automation.llm.token_budget.settings.llm.max_tokens", 4096)
        manager = TokenBudgetManager("qwen")
        manager.record_usage(1000)
        assert manager.get_available_budget() == manager.input_budget - 1000

    def test_get_available_budget_exhausted(self, monkeypatch):
        """验证超支时可用预算为 0。"""
        monkeypatch.setattr("mobile_automation.llm.token_budget.settings.llm.max_tokens", 4096)
        manager = TokenBudgetManager("qwen")
        manager.record_usage(manager.input_budget + 1000)
        assert manager.get_available_budget() == 0

    def test_record_usage_accumulates(self, monkeypatch):
        """验证 record_usage 累加 Token 消耗。"""
        monkeypatch.setattr("mobile_automation.llm.token_budget.settings.llm.max_tokens", 4096)
        manager = TokenBudgetManager("qwen")
        manager.record_usage(500)
        manager.record_usage(300)
        assert manager.total_used == 800

    def test_needs_compression_under_threshold(self, monkeypatch):
        """验证预算充足时不需要压缩。"""
        monkeypatch.setattr("mobile_automation.llm.token_budget.settings.llm.max_tokens", 4096)
        manager = TokenBudgetManager("qwen")
        threshold = int(manager.input_budget * 0.8)
        need = manager.needs_compression(threshold - 100)
        assert need is False

    def test_needs_compression_over_threshold(self, monkeypatch):
        """验证超预算阈值时需要压缩。"""
        monkeypatch.setattr("mobile_automation.llm.token_budget.settings.llm.max_tokens", 4096)
        manager = TokenBudgetManager("qwen")
        threshold = int(manager.input_budget * 0.8)
        need = manager.needs_compression(threshold + 100)
        assert need is True

    def test_estimate_messages_tokens_text_only(self):
        """验证纯文本消息的 Token 估算。"""
        manager = TokenBudgetManager("qwen")
        messages = [LLMMessage(role="user", content="Hello World")]
        estimated = manager.estimate_messages_tokens(messages)
        assert estimated == len("Hello World") // 2

    def test_estimate_messages_tokens_with_image(self):
        """验证含图片消息的 Token 估算。"""
        manager = TokenBudgetManager("qwen")
        messages = [LLMMessage(role="user", content=[
            {"type": "text", "text": "描述图片"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}},
        ])]
        estimated = manager.estimate_messages_tokens(messages)
        assert estimated == len("描述图片") // 2 + 1000

    def test_compression_strategy_none(self, monkeypatch):
        """验证预算充足时策略为 none。"""
        monkeypatch.setattr("mobile_automation.llm.token_budget.settings.llm.max_tokens", 4096)
        manager = TokenBudgetManager("qwen")
        messages = [LLMMessage(role="user", content="short")]
        strategy = manager.get_compression_strategy(messages)
        assert strategy == "none"

    def test_compression_strategy_compress_history(self, monkeypatch):
        """验证轻度超预算时策略为 compress_history。"""
        monkeypatch.setattr("mobile_automation.llm.token_budget.settings.llm.max_tokens", 4096)
        manager = TokenBudgetManager("qwen")
        long_text = "A" * (manager.input_budget * 3)
        messages = [LLMMessage(role="user", content=long_text)]
        strategy = manager.get_compression_strategy(messages)
        assert strategy == "compress_history"

    def test_compression_strategy_drop_images(self, monkeypatch):
        """验证中度超预算时策略为 drop_images。"""
        monkeypatch.setattr("mobile_automation.llm.token_budget.settings.llm.max_tokens", 4096)
        manager = TokenBudgetManager("qwen")
        long_text = "A" * (manager.input_budget * 3 + 1000)
        messages = [LLMMessage(role="user", content=long_text)]
        strategy = manager.get_compression_strategy(messages)
        assert strategy == "drop_images"

    def test_compression_strategy_full_summary(self, monkeypatch):
        """验证严重超预算时策略为 full_summary。"""
        monkeypatch.setattr("mobile_automation.llm.token_budget.settings.llm.max_tokens", 4096)
        manager = TokenBudgetManager("qwen")
        very_long_text = "A" * (manager.input_budget * 5)
        messages = [LLMMessage(role="user", content=very_long_text)]
        strategy = manager.get_compression_strategy(messages)
        assert strategy == "full_summary"

    def test_reset_clears_total_used(self, monkeypatch):
        """验证 reset 将 total_used 置零。"""
        monkeypatch.setattr("mobile_automation.llm.token_budget.settings.llm.max_tokens", 4096)
        manager = TokenBudgetManager("qwen")
        manager.record_usage(5000)
        assert manager.total_used == 5000
        manager.reset()
        assert manager.total_used == 0

    def test_unknown_provider_defaults_to_32k(self, monkeypatch):
        """验证未知提供商默认 32K 窗口。"""
        monkeypatch.setattr("mobile_automation.llm.token_budget.settings.llm.max_tokens", 4096)
        manager = TokenBudgetManager("unknown_provider")
        assert manager.max_context == 32000
