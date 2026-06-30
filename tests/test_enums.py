"""枚举类型模块测试。

测试所有业务枚举的成员值、字符串转换和非法值处理。
"""

import pytest

from mobile_automation.models.enums import (
    ActionType,
    StepStatus,
    TaskStatus,
    PopupType,
    PopupStrategy,
    LLMProvider,
    LLMRole,
)


class TestActionType:
    """测试 ActionType 枚举的值和成员完整性。"""

    def test_values(self):
        """验证所有操作类型的字符串值。"""
        assert ActionType.CLICK.value == "click"
        assert ActionType.DOUBLE_CLICK.value == "double_click"
        assert ActionType.LONG_CLICK.value == "long_click"
        assert ActionType.TYPE.value == "type"
        assert ActionType.SWIPE.value == "swipe"
        assert ActionType.SCROLL.value == "scroll"
        assert ActionType.BACK.value == "back"
        assert ActionType.HOME.value == "home"
        assert ActionType.WAIT.value == "wait"
        assert ActionType.OPEN_APP.value == "open_app"
        assert ActionType.TERMINATE.value == "terminate"
        assert ActionType.VERIFY.value == "verify"

    def test_total_members(self):
        """验证 ActionType 成员数量完整。"""
        assert len(ActionType) == 17

    def test_from_string_valid(self):
        """测试通过字符串值创建枚举。"""
        assert ActionType("click") == ActionType.CLICK
        assert ActionType("swipe") == ActionType.SWIPE
        assert ActionType("back") == ActionType.BACK

    def test_from_string_invalid(self):
        """测试不支持的字符串值抛出 ValueError。"""
        with pytest.raises(ValueError):
            ActionType("invalid_action")


class TestStepStatus:
    """测试 StepStatus 枚举。"""

    def test_values(self):
        """验证所有状态值。"""
        assert StepStatus.PENDING.value == "pending"
        assert StepStatus.RUNNING.value == "running"
        assert StepStatus.SUCCESS.value == "success"
        assert StepStatus.FAILED.value == "failed"
        assert StepStatus.RETRYING.value == "retrying"

    def test_total_members(self):
        """验证 StepStatus 成员数量。"""
        assert len(StepStatus) == 7


class TestTaskStatus:
    """测试 TaskStatus 枚举。"""

    def test_values(self):
        """验证任务状态值。"""
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.ABORTED.value == "aborted"
        assert TaskStatus.PARTIALLY_COMPLETED.value == "partially_completed"

    def test_total_members(self):
        """验证 TaskStatus 成员数量。"""
        assert len(TaskStatus) == 5


class TestPopupType:
    """测试 PopupType 枚举。"""

    def test_values(self):
        """验证弹窗类型值。"""
        assert PopupType.PERMISSION_DIALOG.value == "permission_dialog"
        assert PopupType.AD_POPUP.value == "ad_popup"
        assert PopupType.UNKNOWN.value == "unknown"

    def test_total_members(self):
        """验证 PopupType 成员数量。"""
        assert len(PopupType) == 7


class TestPopupStrategy:
    """测试 PopupStrategy 枚举。"""

    def test_values(self):
        """验证弹窗策略值。"""
        assert PopupStrategy.ALLOW.value == "allow"
        assert PopupStrategy.DENY.value == "deny"
        assert PopupStrategy.DISMISS.value == "dismiss"
        assert PopupStrategy.REPORT_TO_LLM.value == "report_to_llm"

    def test_total_members(self):
        """验证 PopupStrategy 成员数量。"""
        assert len(PopupStrategy) == 6


class TestLLMProvider:
    """测试 LLMProvider 枚举。"""

    def test_values(self):
        """验证提供商值。"""
        assert LLMProvider.QWEN.value == "qwen"
        assert LLMProvider.OPENAI.value == "openai"
        assert LLMProvider.ANTHROPIC.value == "anthropic"

    def test_total_members(self):
        """验证 LLMProvider 成员数量。"""
        assert len(LLMProvider) == 4


class TestLLMRole:
    """测试 LLMRole 枚举。"""

    def test_values(self):
        """验证消息角色值。"""
        assert LLMRole.SYSTEM.value == "system"
        assert LLMRole.USER.value == "user"
        assert LLMRole.ASSISTANT.value == "assistant"

    def test_total_members(self):
        """验证 LLMRole 成员数量。"""
        assert len(LLMRole) == 3
