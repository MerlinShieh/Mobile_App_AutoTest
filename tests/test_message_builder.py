"""消息组装器模块测试。

测试 MessageBuilder 的多模态消息组装、历史上下文管理和摘要消息构建。
"""

from mobile_automation.llm.base import LLMMessage
from mobile_automation.llm.message_builder import MessageBuilder


class TestMessageBuilder:
    """测试 MessageBuilder 的消息组装功能。"""

    def test_build_decision_message_basic(self):
        """验证基本决策消息包含 system 和 user 两条消息。"""
        messages = MessageBuilder.build_decision_message(
            screenshot_base64="test_b64",
            structured_summary="#1 clickable 按钮",
            user_goal="打开设置",
            step_index=1,
        )
        assert len(messages) == 2
        assert messages[0].role == "system"
        assert messages[1].role == "user"

    def test_build_decision_message_with_history(self):
        """验证历史步骤摘要被正确添加到消息中。"""
        messages = MessageBuilder.build_decision_message(
            screenshot_base64="b64",
            structured_summary="#1 按钮",
            user_goal="打开设置",
            history=["已回到桌面", "已找到设置图标"],
            step_index=3,
        )
        assert len(messages) == 3
        assert messages[1].role == "user"
        assert "历史步骤摘要" in messages[1].content
        assert "步骤 1" in messages[1].content

    def test_build_decision_message_content_structure(self):
        """验证 user 消息内容包含文本和图片。"""
        messages = MessageBuilder.build_decision_message(
            screenshot_base64="b64_data",
            structured_summary="#1 clickable 确定",
            user_goal="点击确定",
            step_index=1,
        )
        content = messages[1].content
        assert isinstance(content, list)
        types = [item["type"] for item in content]
        assert "text" in types
        assert "image_url" in types

    def test_build_decision_message_contains_user_goal(self):
        """验证决策消息中包含用户目标描述。"""
        messages = MessageBuilder.build_decision_message(
            screenshot_base64="b64",
            structured_summary="#1 按钮",
            user_goal="打开微信朋友圈",
            step_index=1,
        )
        content = messages[1].content
        text_parts = [item for item in content if item["type"] == "text"]
        all_text = " ".join(t["text"] for t in text_parts)
        assert "打开微信朋友圈" in all_text

    def test_build_decision_message_step_index(self):
        """验证步骤编号在消息中正确显示。"""
        messages = MessageBuilder.build_decision_message(
            screenshot_base64="b64",
            structured_summary="#1 按钮",
            user_goal="测试",
            step_index=5,
        )
        content = messages[-1].content
        text_parts = [item for item in content if item["type"] == "text"]
        all_text = " ".join(t["text"] for t in text_parts)
        assert "#5" in all_text

    def test_build_decision_message_screenshot_format(self):
        """验证截图以 data:image/jpeg;base64 格式嵌入。"""
        messages = MessageBuilder.build_decision_message(
            screenshot_base64="my_screenshot_b64",
            structured_summary="#1 按钮",
            user_goal="测试",
        )
        content = messages[-1].content
        image_urls = [item for item in content if item["type"] == "image_url"]
        assert len(image_urls) == 1
        assert image_urls[0]["image_url"]["url"] == "data:image/jpeg;base64,my_screenshot_b64"

    def test_build_summary_message(self):
        """验证摘要消息包含 system 和 user 两条消息。"""
        messages = MessageBuilder.build_summary_message(
            page_content="完整的页面描述内容"
        )
        assert len(messages) == 2
        assert messages[0].role == "system"
        assert messages[1].role == "user"
        assert messages[1].content == "完整的页面描述内容"

    def test_build_summary_message_uses_summary_prompt(self):
        """验证摘要消息的 system prompt 来自 summary_prompt。"""
        from mobile_automation.prompts.summary_prompt import SUMMARY_PROMPT
        messages = MessageBuilder.build_summary_message("内容")
        assert messages[0].content == SUMMARY_PROMPT

    def test_no_history_when_not_provided(self):
        """验证不提供 history 时消息只有 2 条。"""
        messages = MessageBuilder.build_decision_message(
            screenshot_base64="b64",
            structured_summary="#1 按钮",
            user_goal="测试",
        )
        assert len(messages) == 2

    def test_messages_are_llm_message_type(self):
        """验证返回的消息列表元素类型为 LLMMessage。"""
        messages = MessageBuilder.build_decision_message(
            screenshot_base64="b64",
            structured_summary="#1 按钮",
            user_goal="测试",
        )
        for msg in messages:
            assert isinstance(msg, LLMMessage)
