"""等待动作执行器模块测试。

测试 WaitExecutor 的正常等待、None 防御和页面稳定等待。
"""

import pytest

from mobile_automation.executor.wait_executor import WaitExecutor
from mobile_automation.models.action import Action, ActionParams
from mobile_automation.models.enums import ActionType


class TestWaitExecutor:
    """测试 WaitExecutor 的等待执行与防御逻辑。"""

    def test_execute_duration_wait(self, mocker):
        """验证指定时长的 WAIT 操作走 _wait_duration 并返回 True。"""
        mock_dm = mocker.MagicMock()
        executor = WaitExecutor(mock_dm)
        action = Action(ActionType.WAIT, ActionParams(duration_ms=100))

        mock_dm.get_u2.assert_not_called()
        result = executor.execute(action)
        assert result is True

    def test_execute_none_action_uses_default_wait(self, mocker):
        """验证 action 为 None 时回退默认 1500ms 等待而不崩溃。"""
        mock_dm = mocker.MagicMock()
        executor = WaitExecutor(mock_dm)
        mock_dm.get_u2.assert_not_called()

        result = executor.execute(None)
        assert result is True

    def test_execute_none_params_uses_default_wait(self, mocker):
        """验证 params 为 None 时回退默认 1500ms 等待而不崩溃。"""
        mock_dm = mocker.MagicMock()
        executor = WaitExecutor(mock_dm)
        action = Action(ActionType.WAIT, None)

        mock_dm.get_u2.assert_not_called()
        result = executor.execute(action)
        assert result is True

    def test_execute_stable_wait(self, mocker):
        """验证未指定时长时委托 wait_stable 检测页面稳定。"""
        mock_dm = mocker.MagicMock()
        mock_u2 = mocker.MagicMock()
        mock_u2.wait_stable.return_value = True
        mock_dm.get_u2.return_value = mock_u2

        executor = WaitExecutor(mock_dm)
        action = Action(ActionType.WAIT, ActionParams(duration_ms=0))

        result = executor.execute(action)
        assert result is True
        mock_u2.wait_stable.assert_called_once_with(timeout_ms=5000)

    def test_execute_stable_wait_timeout(self, mocker):
        """验证页面稳定等待超时返回 False。"""
        mock_dm = mocker.MagicMock()
        mock_u2 = mocker.MagicMock()
        mock_u2.wait_stable.return_value = False
        mock_dm.get_u2.return_value = mock_u2

        executor = WaitExecutor(mock_dm)
        action = Action(ActionType.WAIT, ActionParams(duration_ms=0))

        result = executor.execute(action)
        assert result is False

    def test_execute_stable_wait_u2_not_connected(self, mocker):
        """验证 u2 未连接（抛 RuntimeError）时返回 False 而非崩溃。"""
        mock_dm = mocker.MagicMock()
        mock_dm.get_u2.side_effect = RuntimeError("uiautomator2 未连接")

        executor = WaitExecutor(mock_dm)
        action = Action(ActionType.WAIT, ActionParams(duration_ms=0))

        result = executor.execute(action)
        assert result is False
