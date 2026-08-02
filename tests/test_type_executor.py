"""TypeExecutor 文本输入执行器测试。

测试 TYPE 操作的焦点点击、预填清空、文本输入流程，
以及 CLEAR_TEXT 操作和异常路径。
"""

import pytest

from mobile_automation.executor.type_executor import TypeExecutor
from mobile_automation.models.action import Action, ActionParams
from mobile_automation.models.enums import ActionType


class TestTypeExecutor:
    """测试 TypeExecutor 的 TYPE 和 CLEAR_TEXT 操作。"""

    def test_type_basic_focus_and_send(self, mocker):
        """验证 TYPE 基本流程：点击聚焦 → 清空预填 → 发送文本。"""
        mock_dm = mocker.MagicMock()
        mock_u2 = mocker.MagicMock()
        mock_dm.get_u2.return_value = mock_u2

        executor = TypeExecutor(mock_dm)
        action = Action(ActionType.TYPE, ActionParams(text="王者荣耀", x=100, y=200))
        result = executor.execute(action)

        assert result is True
        mock_u2.click.assert_called_once_with(100, 200)
        mock_u2.clear_text.assert_called_once()
        mock_u2.send_text.assert_called_once_with("王者荣耀")

    def test_type_clear_called_before_send(self, mocker):
        """验证 clear_text 在 send_text 之前调用（防止文本拼接）。"""
        mock_dm = mocker.MagicMock()
        mock_u2 = mocker.MagicMock()
        mock_dm.get_u2.return_value = mock_u2

        executor = TypeExecutor(mock_dm)
        action = Action(ActionType.TYPE, ActionParams(text="原神", x=50, y=100))

        # 记录调用顺序
        call_order = []
        mock_u2.click.side_effect = lambda *a, **k: call_order.append("click")
        mock_u2.clear_text.side_effect = lambda: call_order.append("clear_text")
        mock_u2.send_text.side_effect = lambda t: call_order.append("send_text")

        executor.execute(action)
        assert call_order == ["click", "clear_text", "send_text"]

    def test_type_clear_failure_not_blocking(self, mocker):
        """验证 clear_text 失败时不影响 send_text 执行（非编辑框控件）。"""
        mock_dm = mocker.MagicMock()
        mock_u2 = mocker.MagicMock()
        mock_u2.clear_text.side_effect = RuntimeError("控件不支持清空")
        mock_dm.get_u2.return_value = mock_u2

        executor = TypeExecutor(mock_dm)
        action = Action(ActionType.TYPE, ActionParams(text="搜索", x=10, y=20))
        result = executor.execute(action)

        assert result is True
        mock_u2.send_text.assert_called_once_with("搜索")

    def test_type_empty_text_returns_false(self, mocker):
        """验证空文本返回 False。"""
        mock_dm = mocker.MagicMock()
        mock_u2 = mocker.MagicMock()
        mock_dm.get_u2.return_value = mock_u2

        executor = TypeExecutor(mock_dm)
        action = Action(ActionType.TYPE, ActionParams(text="", x=100, y=200))
        result = executor.execute(action)

        assert result is False
        mock_u2.send_text.assert_not_called()

    def test_type_none_text_returns_false(self, mocker):
        """验证 None 文本返回 False。"""
        mock_dm = mocker.MagicMock()
        mock_u2 = mocker.MagicMock()
        mock_dm.get_u2.return_value = mock_u2

        executor = TypeExecutor(mock_dm)
        action = Action(ActionType.TYPE, ActionParams(x=100, y=200))
        result = executor.execute(action)

        assert result is False
        mock_u2.send_text.assert_not_called()

    def test_type_focus_click_failure_returns_false(self, mocker):
        """验证聚焦点击失败时返回 False 且不执行输入（防止文本泄露）。"""
        mock_dm = mocker.MagicMock()
        mock_u2 = mocker.MagicMock()
        mock_u2.click.side_effect = RuntimeError("点击失败")
        mock_dm.get_u2.return_value = mock_u2

        executor = TypeExecutor(mock_dm)
        action = Action(ActionType.TYPE, ActionParams(text="测试", x=500, y=600))
        result = executor.execute(action)

        assert result is False
        mock_u2.send_text.assert_not_called()

    def test_type_without_coordinates_sends_directly(self, mocker):
        """验证无坐标时直接对当前焦点发送文本（不点击）。"""
        mock_dm = mocker.MagicMock()
        mock_u2 = mocker.MagicMock()
        mock_dm.get_u2.return_value = mock_u2

        executor = TypeExecutor(mock_dm)
        action = Action(ActionType.TYPE, ActionParams(text="直接输入"))
        result = executor.execute(action)

        assert result is True
        mock_u2.click.assert_not_called()
        mock_u2.clear_text.assert_called_once()
        mock_u2.send_text.assert_called_once_with("直接输入")

    def test_clear_text_execution(self, mocker):
        """验证 CLEAR_TEXT 操作调用 u2.clear_text。"""
        mock_dm = mocker.MagicMock()
        mock_u2 = mocker.MagicMock()
        mock_dm.get_u2.return_value = mock_u2

        executor = TypeExecutor(mock_dm)
        action = Action(ActionType.CLEAR_TEXT, ActionParams())
        result = executor.execute(action)

        assert result is True
        mock_u2.clear_text.assert_called_once()

    def test_execute_exception_returns_false(self, mocker):
        """验证 get_u2 抛出 RuntimeError 时返回 False。"""
        mock_dm = mocker.MagicMock()
        mock_dm.get_u2.side_effect = RuntimeError("u2 未初始化")

        executor = TypeExecutor(mock_dm)
        action = Action(ActionType.TYPE, ActionParams(text="测试", x=0, y=0))
        result = executor.execute(action)

        assert result is False
