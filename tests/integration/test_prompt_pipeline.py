"""集成测试：验证 system + decision prompt 是否包含 CoT 指令关键字。

确保 prompt 中引导 LLM 输出 <think>/<answer> 标签格式。

"""

from __future__ import annotations

import unittest

from mobile_automation.prompts.decision_prompt import DecisionPromptBuilder
from mobile_automation.prompts.system_prompt import SYSTEM_PROMPT


class TestPromptPipeline(unittest.TestCase):
    """验证 prompt 包含 CoT 关键字。"""

    def test_system_prompt_contains_think_tag(self):
        """system_prompt 应包含 <think> 标记。"""
        self.assertIn("<think>", SYSTEM_PROMPT)
        self.assertIn("</think>", SYSTEM_PROMPT)
        self.assertIn("<answer>", SYSTEM_PROMPT)
        self.assertIn("</answer>", SYSTEM_PROMPT)

    def test_decision_prompt_contains_think_answer_instruction(self):
        """decision_prompt 应引导使用 <think>/<answer>。"""
        builder = DecisionPromptBuilder()
        messages = builder.build(
            user_goal="打开设置",
            screenshot="",
            structured_summary="#1 可点 设置",
            step_index=1,
        )
        # 查找 user 消息中的文本内容，确保包含 CoT 指令
        user_text = ""
        for msg in messages:
            if msg.role == "user":
                if isinstance(msg.content, str):
                    user_text += msg.content
                elif isinstance(msg.content, list):
                    for item in msg.content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            user_text += item.get("text", "")
        self.assertIn("<think>", user_text)
        self.assertIn("<answer>", user_text)

    def test_system_prompt_has_process_section(self):
        """system_prompt 应包含「决策过程」章节。"""
        self.assertIn("决策过程", SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
