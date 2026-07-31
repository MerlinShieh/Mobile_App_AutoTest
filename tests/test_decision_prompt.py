"""
DecisionPromptBuilder 消息构建测试。

验证四种 Token 压缩策略的正确行为：none / compress_history / drop_images / full_summary。
"""

import pytest

from src.mobile_automation.llm.base import LLMMessage
from src.mobile_automation.prompts.decision_prompt import DecisionPromptBuilder, MAX_HISTORY_COMPRESSED

SAMPLE_SCREENSHOT = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
SAMPLE_SUMMARY = "#1 [可点] 设置"


class TestDecisionPromptBuilderCompression:
    """DecisionPromptBuilder Token 压缩策略测试。"""

    @pytest.fixture
    def builder(self):
        return DecisionPromptBuilder()

    @pytest.fixture
    def long_history(self):
        return [f"Step{i}: 页面有标题 按钮 输入框" for i in range(1, 21)]

    def test_strategy_none_keeps_all_history(self, builder, long_history):
        """策略 'none' 保留全部历史。"""
        messages = builder.build(
            user_goal="测试",
            screenshot=SAMPLE_SCREENSHOT,
            structured_summary=SAMPLE_SUMMARY,
            history=long_history,
            compression_strategy="none",
        )
        assert len(messages) == 3  # system + history + current
        assert "Step20" in messages[1].content
        assert "Step1" in messages[1].content

    def test_strategy_compress_history_truncates(self, builder, long_history):
        """策略 'compress_history' 只保留最近 N 条。"""
        messages = builder.build(
            user_goal="测试",
            screenshot=SAMPLE_SCREENSHOT,
            structured_summary=SAMPLE_SUMMARY,
            history=long_history,
            compression_strategy="compress_history",
        )
        history_text = messages[1].content if len(messages) > 1 else ""
        # 格式为 "## 历史步骤摘要\n步骤 1: Step16: 页面...\n步骤 2: Step17:..."
        # 每个历史条目格式为 "步骤 N: content"
        line_count = history_text.count("\n")  # 排除标题行
        assert line_count <= MAX_HISTORY_COMPRESSED, f"Expected <= {MAX_HISTORY_COMPRESSED} lines, got {line_count}"
        # 最新的步骤应该保留
        assert "Step20" in history_text
        # 最早的步骤应该被裁剪（Step1 是历史第一条，应该不在截断后的列表中）
        assert "Step1:" not in history_text

    def test_strategy_drop_images_still_has_history(self, builder, long_history):
        """策略 'drop_images' 裁剪历史到首尾 + 不保留截图。"""
        messages = builder.build(
            user_goal="测试",
            screenshot=SAMPLE_SCREENSHOT,
            structured_summary=SAMPLE_SUMMARY,
            history=long_history,
            compression_strategy="drop_images",
        )
        # 检查 history 被压缩到首尾
        history_text = messages[1].content if len(messages) > 1 else ""
        assert "已压缩" in history_text
        # drop_images 策略会移除当前步的截图以节省 Token
        current_content = messages[-1].content if isinstance(messages[-1].content, list) else []
        image_items = [c for c in current_content if isinstance(c, dict) and c.get("type") == "image_url"]
        assert len(image_items) == 0

    def test_no_history_no_change(self, builder):
        """无历史时所有策略行为一致。"""
        for strategy in ("none", "compress_history", "drop_images", "full_summary"):
            messages = builder.build(
                user_goal="测试",
                screenshot=SAMPLE_SCREENSHOT,
                structured_summary=SAMPLE_SUMMARY,
                history=None,
                compression_strategy=strategy,
            )
            assert len(messages) == 2  # system + current

    def test_strategy_none_includes_screenshot(self, builder):
        """策略 'none' 包含截图。"""
        messages = builder.build(
            user_goal="测试",
            screenshot=SAMPLE_SCREENSHOT,
            structured_summary=SAMPLE_SUMMARY,
            step_index=1,
            compression_strategy="none",
        )
        content = messages[-1].content
        assert isinstance(content, list)
        image_items = [c for c in content if isinstance(c, dict) and c.get("type") == "image_url"]
        assert len(image_items) == 1

    def test_single_step_history_no_truncation(self, builder):
        """只有一条历史时 compress_history 不会裁剪。"""
        history = ["步骤 1: 首页"]
        messages = builder.build(
            user_goal="测试",
            screenshot=SAMPLE_SCREENSHOT,
            structured_summary=SAMPLE_SUMMARY,
            history=history,
            compression_strategy="compress_history",
        )
        assert "步骤 1" in messages[1].content
        assert len(messages) == 3

    def test_two_step_history_drop_images_no_truncation(self, builder):
        """只有两条历史时 drop_images 不会裁剪。"""
        history = ["步骤 1: 首页", "步骤 2: 设置页"]
        messages = builder.build(
            user_goal="测试",
            screenshot=SAMPLE_SCREENSHOT,
            structured_summary=SAMPLE_SUMMARY,
            history=history,
            compression_strategy="drop_images",
        )
        history_text = messages[1].content
        assert "步骤 1" in history_text
        assert "步骤 2" in history_text
        assert "已压缩" not in history_text

    def test_messages_types(self, builder):
        """验证消息角色类型正确。"""
        messages = builder.build(
            user_goal="测试",
            screenshot=SAMPLE_SCREENSHOT,
            structured_summary=SAMPLE_SUMMARY,
            history=["步骤 1: 首页"],
            step_index=2,
            compression_strategy="none",
        )
        assert messages[0].role == "system"
        assert messages[1].role == "user"
        assert isinstance(messages[1].content, str)
        assert messages[2].role == "user"
        assert isinstance(messages[2].content, list)
