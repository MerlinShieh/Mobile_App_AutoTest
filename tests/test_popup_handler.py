"""弹窗处理模块测试。

测试 PopupHandler 的弹窗检测策略（Dialog 关键词、覆盖层、特征文本）
和弹窗处理（ALLOW/DENY/DISMISS/CANCEL）功能。
"""

import pytest

from mobile_automation.models.enums import PopupType, PopupStrategy
from mobile_automation.models.perception import UINode, UITree
from mobile_automation.popup.models import PopupDetectResult
from mobile_automation.popup.popup_handler import PopupHandler, PatternRules


class TestPopupHandlerDetect:
    """测试 PopupHandler 的弹窗检测方法。"""

    def test_detect_disabled_when_popup_disabled(self, mocker):
        """验证弹窗检测禁用时返回 None。"""
        mock_dm = mocker.MagicMock()
        mocker.patch("mobile_automation.popup.popup_handler.settings.popup.enabled", False)
        handler = PopupHandler(mock_dm)
        root = UINode()
        tree = UITree(root=root, local_index={})
        result = handler.detect(tree)
        assert result is None

    def test_detect_dialog_keywords(self, mocker):
        """验证 Dialog 关键词检测命中。"""
        mock_dm = mocker.MagicMock()
        root = UINode()
        node = UINode(element_id="#1", resource_id="com.example:id/dialog_container",
                      class_name="android.widget.LinearLayout")
        tree = UITree(root=root, local_index={"#1": node})
        handler = PopupHandler(mock_dm)
        result = handler.detect(tree)
        assert result is not None
        assert result.detected is True
        assert result.confidence == 0.85

    def test_detect_overlay(self, mocker):
        """验证覆盖层检测命中。"""
        mock_dm = mocker.MagicMock()
        mock_dm.get_screen_size.return_value = (1080, 2400)
        root = UINode()
        node = UINode(element_id="#1", bounds=(0, 0, 1080, 2400))
        tree = UITree(root=root, local_index={"#1": node})
        handler = PopupHandler(mock_dm)
        result = handler.detect(tree)
        assert result is not None
        assert result.detected is True
        assert result.confidence == 0.7

    def test_detect_feature_text(self, mocker):
        """验证特征文本检测命中。"""
        mock_dm = mocker.MagicMock()
        mock_dm.get_screen_size.return_value = (1080, 2400)
        root = UINode()
        node = UINode(element_id="#1", text="allow", bounds=(10, 10, 100, 50))
        tree = UITree(root=root, local_index={"#1": node})
        handler = PopupHandler(mock_dm)
        result = handler.detect(tree)
        assert result is not None
        assert result.detected is True

    def test_detect_no_popup(self, mocker):
        """验证无弹窗时返回 None。"""
        mock_dm = mocker.MagicMock()
        mock_dm.get_screen_size.return_value = (1080, 2400)
        root = UINode()
        node = UINode(element_id="#1", resource_id="com.example:id/normal_btn",
                      bounds=(100, 100, 200, 150), text="普通按钮")
        tree = UITree(root=root, local_index={"#1": node})
        handler = PopupHandler(mock_dm)
        result = handler.detect(tree)
        assert result is None

    def test_detect_empty_tree(self, mocker):
        """验证空 UI 树返回 None。"""
        mock_dm = mocker.MagicMock()
        handler = PopupHandler(mock_dm)
        result = handler.detect(None)
        assert result is None

    def test_detect_classification_permission(self, mocker):
        """验证权限弹窗分类（dialog 节点含精确关键词）。"""
        mock_dm = mocker.MagicMock()
        root = UINode()
        dialog_node = UINode(
            element_id="#1",
            resource_id="com.example:id/dialog",
            class_name="android.widget.LinearLayout",
            text="allow",
        )
        tree = UITree(root=root, local_index={"#1": dialog_node})
        handler = PopupHandler(mock_dm)
        result = handler.detect(tree)
        assert result is not None
        assert result.popup_type == PopupType.PERMISSION_DIALOG

    def test_detect_classification_update(self, mocker):
        """验证更新弹窗分类（dialog 节点含精确关键词）。"""
        mock_dm = mocker.MagicMock()
        root = UINode()
        dialog_node = UINode(
            element_id="#1",
            resource_id="com.example:id/dialogroot",
            text="update",
        )
        tree = UITree(root=root, local_index={"#1": dialog_node})
        handler = PopupHandler(mock_dm)
        result = handler.detect(tree)
        assert result is not None
        assert result.popup_type == PopupType.UPDATE_DIALOG


class TestPopupHandlerHandle:
    """测试 PopupHandler 的弹窗处理方法。"""

    def test_handle_allow_strategy(self, mocker):
        """验证 ALLOW 策略点击允许按钮。"""
        mock_dm = mocker.MagicMock()
        mock_u2 = mocker.MagicMock()
        mock_u2.click_by_text.return_value = True
        mock_dm.get_u2.return_value = mock_u2

        handler = PopupHandler(mock_dm)
        result = PopupDetectResult(detected=True, popup_type=PopupType.PERMISSION_DIALOG)
        handled = handler.handle(result)
        assert handled is True
        mock_u2.click_by_text.assert_called()

    def test_handle_deny_strategy(self, mocker):
        """验证 DENY 策略点击拒绝按钮。"""
        mock_dm = mocker.MagicMock()
        mock_u2 = mocker.MagicMock()
        mock_u2.click_by_text.return_value = True
        mock_dm.get_u2.return_value = mock_u2

        handler = PopupHandler(mock_dm)
        result = PopupDetectResult(detected=True, popup_type=PopupType.PERMISSION_DIALOG)
        mocker.patch.object(handler._rules, "get_strategy", return_value=PopupStrategy.DENY)
        handled = handler.handle(result)
        assert handled is True

    def test_handle_dismiss_strategy(self, mocker):
        """验证 DISMISS 策略关闭弹窗。"""
        mock_dm = mocker.MagicMock()
        mock_u2 = mocker.MagicMock()
        mock_u2.click_by_text.return_value = False
        mock_dm.get_u2.return_value = mock_u2

        handler = PopupHandler(mock_dm)
        mocker.patch.object(handler._rules, "get_strategy", return_value=PopupStrategy.DISMISS)
        result = PopupDetectResult(detected=True, popup_type=PopupType.AD_POPUP)
        handled = handler.handle(result)
        assert handled is True
        mock_u2.press_back.assert_called_once()

    def test_handle_cancel_strategy(self, mocker):
        """验证 CANCEL 策略点击取消按钮。"""
        mock_dm = mocker.MagicMock()
        mock_u2 = mocker.MagicMock()
        mock_u2.click_by_text.return_value = True
        mock_dm.get_u2.return_value = mock_u2

        handler = PopupHandler(mock_dm)
        mocker.patch.object(handler._rules, "get_strategy", return_value=PopupStrategy.CANCEL)
        result = PopupDetectResult(detected=True, popup_type=PopupType.UPDATE_DIALOG)
        handled = handler.handle(result)
        assert handled is True
        mock_u2.click_by_text.assert_called_once_with("取消", exact=False)

    def test_handle_report_to_llm(self, mocker):
        """验证 REPORT_TO_LLM 策略返回 False。"""
        mock_dm = mocker.MagicMock()
        handler = PopupHandler(mock_dm)
        mocker.patch.object(handler._rules, "get_strategy", return_value=PopupStrategy.REPORT_TO_LLM)
        result = PopupDetectResult(detected=True, popup_type=PopupType.UNKNOWN)
        handled = handler.handle(result)
        assert handled is False

    def test_handle_not_detected(self, mocker):
        """验证未检测到弹窗时返回 False。"""
        mock_dm = mocker.MagicMock()
        handler = PopupHandler(mock_dm)
        result = PopupDetectResult(detected=False)
        handled = handler.handle(result)
        assert handled is False


class TestPatternRules:
    """测试 PatternRules 策略匹配。"""

    def test_get_strategy_permission(self):
        """验证权限弹窗返回 ALLOW 策略。"""
        rules = PatternRules()
        strategy = rules.get_strategy(PopupType.PERMISSION_DIALOG)
        assert strategy == PopupStrategy.ALLOW

    def test_get_strategy_update(self):
        """验证更新弹窗返回 CANCEL 策略。"""
        rules = PatternRules()
        strategy = rules.get_strategy(PopupType.UPDATE_DIALOG)
        assert strategy == PopupStrategy.CANCEL

    def test_get_strategy_ad(self):
        """验证广告弹窗返回 DISMISS 策略。"""
        rules = PatternRules()
        strategy = rules.get_strategy(PopupType.AD_POPUP)
        assert strategy == PopupStrategy.DISMISS

    def test_get_strategy_unknown(self):
        """验证未知弹窗返回 REPORT_TO_LLM。"""
        rules = PatternRules()
        strategy = rules.get_strategy(PopupType.UNKNOWN)
        assert strategy == PopupStrategy.REPORT_TO_LLM
