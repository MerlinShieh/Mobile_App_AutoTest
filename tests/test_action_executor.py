"""动作执行器模块测试。

测试 ActionExecutor 的参数校验、动作分发、系统操作执行和坐标微调功能。
"""

import pytest

from mobile_automation.executor.action_executor import ActionExecutor
from mobile_automation.models.action import Action, ActionParams
from mobile_automation.models.enums import ActionType


class TestActionExecutor:
    """测试 ActionExecutor 的动作分发和执行。"""

    def test_execute_click_with_valid_params(self, mocker):
        """验证有效参数的 CLICK 操作成功执行。"""
        mock_dm = mocker.MagicMock()
        mock_u2 = mocker.MagicMock()
        mock_dm.get_u2.return_value = mock_u2

        executor = ActionExecutor(mock_dm)
        action = Action(ActionType.CLICK, ActionParams(element_id="#1", x=200, y=300))
        result = executor.execute(action)
        assert result is True

    def test_execute_invalid_params_raises(self, mocker):
        """验证无效参数抛出 ValueError。"""
        mock_dm = mocker.MagicMock()
        executor = ActionExecutor(mock_dm)
        action = Action(ActionType.CLICK, ActionParams())
        with pytest.raises(ValueError, match="参数校验失败"):
            executor.execute(action)

    def test_execute_system_back(self, mocker):
        """验证 BACK 系统操作委托给 U2Controller。"""
        mock_dm = mocker.MagicMock()
        mock_u2 = mocker.MagicMock()
        mock_dm.get_u2.return_value = mock_u2

        executor = ActionExecutor(mock_dm)
        action = Action(ActionType.BACK, ActionParams())
        result = executor.execute(action)
        assert result is True
        mock_u2.press_back.assert_called_once()

    def test_execute_system_home(self, mocker):
        """验证 HOME 系统操作。"""
        mock_dm = mocker.MagicMock()
        mock_u2 = mocker.MagicMock()
        mock_dm.get_u2.return_value = mock_u2

        executor = ActionExecutor(mock_dm)
        action = Action(ActionType.HOME, ActionParams())
        result = executor.execute(action)
        assert result is True
        mock_u2.press_home.assert_called_once()

    def test_execute_system_recent_apps(self, mocker):
        """验证 RECENT_APPS 系统操作。"""
        mock_dm = mocker.MagicMock()
        mock_u2 = mocker.MagicMock()
        mock_dm.get_u2.return_value = mock_u2

        executor = ActionExecutor(mock_dm)
        action = Action(ActionType.RECENT_APPS, ActionParams())
        result = executor.execute(action)
        assert result is True
        mock_u2.press_recent.assert_called_once()

    def test_execute_system_open_app(self, mocker):
        """验证 OPEN_APP 系统操作。"""
        mock_dm = mocker.MagicMock()
        mock_u2 = mocker.MagicMock()
        mock_dm.get_u2.return_value = mock_u2

        executor = ActionExecutor(mock_dm)
        action = Action(ActionType.OPEN_APP, ActionParams(package_name="com.example"))
        result = executor.execute(action)
        assert result is True
        mock_u2.app_start.assert_called_once_with("com.example")

    def test_execute_system_close_app(self, mocker):
        """验证 CLOSE_APP 系统操作。"""
        mock_dm = mocker.MagicMock()
        mock_u2 = mocker.MagicMock()
        mock_dm.get_u2.return_value = mock_u2

        executor = ActionExecutor(mock_dm)
        action = Action(ActionType.CLOSE_APP, ActionParams(package_name="com.example"))
        result = executor.execute(action)
        assert result is True
        mock_u2.app_stop.assert_called_once_with("com.example")

    def test_execute_wait_uses_wait_executor(self, mocker):
        """验证 WAIT 操作委托给 WaitExecutor。"""
        mock_dm = mocker.MagicMock()
        executor = ActionExecutor(mock_dm)
        action = Action(ActionType.WAIT, ActionParams(duration_ms=1000))

        mock_wait = mocker.patch.object(executor._executors[ActionType.WAIT], "execute", return_value=True)
        result = executor.execute(action)
        assert result is True
        mock_wait.assert_called_once_with(action)

    def test_priority_click_by_ui_element(self, mocker):
        """验证 CLICK 优先使用 ui_element 定位。"""
        mock_dm = mocker.MagicMock()
        mock_u2 = mocker.MagicMock()
        mock_u2.click_by_text.return_value = True
        mock_dm.get_u2.return_value = mock_u2

        executor = ActionExecutor(mock_dm)
        action = Action(ActionType.CLICK, ActionParams(element_id="#1", ui_element="确定", x=100, y=200))
        result = executor.execute(action)
        assert result is True
        # 优先使用 ui_element，所以 click_by_text 应该被调用
        mock_u2.click_by_text.assert_called_once_with("确定", exact=False)

    def test_execute_with_coordinate_tuning(self, mocker):
        """验证启用坐标微调时应用偏移。"""
        mocker.patch("mobile_automation.executor.action_executor.settings.coordinate_tuning.enable_tuning", True)
        mocker.patch("mobile_automation.executor.action_executor.settings.coordinate_tuning.offset_x", 10)
        mocker.patch("mobile_automation.executor.action_executor.settings.coordinate_tuning.offset_y", -5)

        mock_dm = mocker.MagicMock()
        executor = ActionExecutor(mock_dm)
        action = Action(ActionType.CLICK, ActionParams(x=100, y=200))

        executor._apply_tuning(action.params)
        assert action.params.x == 110
        assert action.params.y == 195

    def test_execute_unknown_system_action(self, mocker):
        """验证未知系统操作返回 False。"""
        mock_dm = mocker.MagicMock()
        mock_u2 = mocker.MagicMock()
        mock_dm.get_u2.return_value = mock_u2

        executor = ActionExecutor(mock_dm)
        # 使用一个既没有子执行器也不是已知系统操作的 ActionType（例如 TERMINATE）
        action = Action(ActionType.TERMINATE, ActionParams())
        result = executor.execute(action)
        assert result is True  # TERMINATE 现在在系统操作字典中有映射

    def test_executor_initialization_creates_sub_executors(self, mocker):
        """验证初始化时创建所有子执行器。"""
        mock_dm = mocker.MagicMock()
        executor = ActionExecutor(mock_dm)
        assert len(executor._executors) == 9
        assert ActionType.CLICK in executor._executors
        assert ActionType.TYPE in executor._executors
        assert ActionType.SWIPE in executor._executors
        assert ActionType.WAIT in executor._executors
