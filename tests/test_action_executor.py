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
        mock_dm.get_screen_size.return_value = (1080, 2400)
        executor = ActionExecutor(mock_dm)
        action = Action(ActionType.CLICK, ActionParams(x=100, y=200))

        executor._apply_tuning(action.params)
        assert action.params.x == 110
        assert action.params.y == 195

    def test_apply_tuning_clamps_to_screen(self, mocker):
        """验证微调结果被裁剪到屏幕有效范围。"""
        mocker.patch("mobile_automation.executor.action_executor.settings.coordinate_tuning.enable_tuning", True)
        mocker.patch("mobile_automation.executor.action_executor.settings.coordinate_tuning.offset_x", 10)
        mocker.patch("mobile_automation.executor.action_executor.settings.coordinate_tuning.offset_y", -5)

        mock_dm = mocker.MagicMock()
        mock_dm.get_screen_size.return_value = (1080, 2400)
        executor = ActionExecutor(mock_dm)

        # x=0 加偏移 10 -> 10 正常；y=5 减偏移 5 -> 0（裁剪到 0）
        action = Action(ActionType.CLICK, ActionParams(x=0, y=5))
        executor._apply_tuning(action.params)
        assert action.params.x == 10
        assert action.params.y == 0

        # 超出屏幕边界时裁剪到 screen-1
        action2 = Action(ActionType.CLICK, ActionParams(x=1075, y=2405))
        executor._apply_tuning(action2.params)
        assert action2.params.x == 1079
        assert action2.params.y == 2399

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

    def test_execute_system_lock_screen(self, mocker):
        """验证 LOCK_SCREEN 通过 ADB 执行熄屏操作。"""
        mock_dm = mocker.MagicMock()
        mock_adb = mocker.MagicMock()
        mock_dm.get_adb.return_value = mock_adb

        executor = ActionExecutor(mock_dm)
        action = Action(ActionType.LOCK_SCREEN, ActionParams())
        result = executor.execute(action)
        assert result is True
        mock_adb.lock_screen.assert_called_once()

    def test_execute_system_open_notifications(self, mocker):
        """验证 OPEN_NOTIFICATIONS 通过 ADB 展开通知栏。"""
        mock_dm = mocker.MagicMock()
        mock_adb = mocker.MagicMock()
        mock_dm.get_adb.return_value = mock_adb

        executor = ActionExecutor(mock_dm)
        action = Action(ActionType.OPEN_NOTIFICATIONS, ActionParams())
        result = executor.execute(action)
        assert result is True
        mock_adb.open_notifications.assert_called_once()

    def test_execute_system_rotate_screen(self, mocker):
        """验证 ROTATE_SCREEN 通过 ADB 设置旋转方向。"""
        mock_dm = mocker.MagicMock()
        mock_adb = mocker.MagicMock()
        mock_dm.get_adb.return_value = mock_adb

        executor = ActionExecutor(mock_dm)
        action = Action(ActionType.ROTATE_SCREEN, ActionParams(direction="landscape"))
        result = executor.execute(action)
        assert result is True
        mock_adb.set_rotation.assert_called_once_with(1)

    def test_execute_system_volume_up(self, mocker):
        """验证 VOLUME_UP 通过 ADB 调高音量。"""
        mock_dm = mocker.MagicMock()
        mock_adb = mocker.MagicMock()
        mock_dm.get_adb.return_value = mock_adb

        executor = ActionExecutor(mock_dm)
        action = Action(ActionType.VOLUME_UP, ActionParams())
        result = executor.execute(action)
        assert result is True
        mock_adb.volume_up.assert_called_once()

    def test_execute_system_volume_down(self, mocker):
        """验证 VOLUME_DOWN 通过 ADB 调低音量。"""
        mock_dm = mocker.MagicMock()
        mock_adb = mocker.MagicMock()
        mock_dm.get_adb.return_value = mock_adb

        executor = ActionExecutor(mock_dm)
        action = Action(ActionType.VOLUME_DOWN, ActionParams())
        result = executor.execute(action)
        assert result is True
        mock_adb.volume_down.assert_called_once()

    def test_execute_system_rotate_screen_default_portrait(self, mocker):
        """验证 ROTATE_SCREEN 无 direction 时默认竖屏。"""
        mock_dm = mocker.MagicMock()
        mock_adb = mocker.MagicMock()
        mock_dm.get_adb.return_value = mock_adb

        executor = ActionExecutor(mock_dm)
        action = Action(ActionType.ROTATE_SCREEN, ActionParams())
        result = executor.execute(action)
        assert result is True
        mock_adb.set_rotation.assert_called_once_with(0)

    # ------------------------------------------------------------------
    # 系统级查询动作（READ_SMS / GET_CLIPBOARD / GET_NOTIFICATIONS / GET_CALL_STATE）
    # ------------------------------------------------------------------

    def test_execute_read_sms_dispatches_to_adb(self, mocker):
        """验证 READ_SMS 调用 ADB get_sms_messages，参数透传，结果写入 params.result。"""
        mock_dm = mocker.MagicMock()
        mock_adb = mocker.MagicMock()
        sms_result = [{"address": "10086", "body": "验证码 123456", "date": 1700000000000}]
        mock_adb.get_sms_messages.return_value = sms_result
        mock_dm.get_adb.return_value = mock_adb

        executor = ActionExecutor(mock_dm)
        action = Action(ActionType.READ_SMS, ActionParams(sms_type="inbox", limit=3))
        result = executor.execute(action)
        assert result is True
        mock_adb.get_sms_messages.assert_called_once_with(sms_type="inbox", limit=3)
        assert action.params.result == sms_result

    def test_execute_read_sms_invalid_type_falls_back_inbox(self, mocker):
        """验证 READ_SMS 非法 sms_type 回退 inbox，非法 limit 回退 20。"""
        mock_dm = mocker.MagicMock()
        mock_adb = mocker.MagicMock()
        mock_adb.get_sms_messages.return_value = []
        mock_dm.get_adb.return_value = mock_adb

        executor = ActionExecutor(mock_dm)
        action = Action(ActionType.READ_SMS, ActionParams(sms_type="received", limit="abc"))  # type: ignore[arg-type]
        result = executor.execute(action)
        assert result is True
        mock_adb.get_sms_messages.assert_called_once_with(sms_type="inbox", limit=20)

    def test_execute_get_clipboard_dispatches_to_adb(self, mocker):
        """验证 GET_CLIPBOARD 调用 ADB get_clipboard，结果写入 params.result。"""
        mock_dm = mocker.MagicMock()
        mock_adb = mocker.MagicMock()
        mock_adb.get_clipboard.return_value = "复制内容 ABC"
        mock_dm.get_adb.return_value = mock_adb

        executor = ActionExecutor(mock_dm)
        action = Action(ActionType.GET_CLIPBOARD, ActionParams())
        result = executor.execute(action)
        assert result is True
        mock_adb.get_clipboard.assert_called_once()
        assert action.params.result == "复制内容 ABC"

    def test_execute_get_notifications_dispatches_to_adb(self, mocker):
        """验证 GET_NOTIFICATIONS 调用 ADB get_notifications，limit 透传。"""
        mock_dm = mocker.MagicMock()
        mock_adb = mocker.MagicMock()
        mock_adb.get_notifications.return_value = [{"package": "com.android.mms", "title": "验证码", "text": "123456"}]
        mock_dm.get_adb.return_value = mock_adb

        executor = ActionExecutor(mock_dm)
        action = Action(ActionType.GET_NOTIFICATIONS, ActionParams(limit=5))
        result = executor.execute(action)
        assert result is True
        mock_adb.get_notifications.assert_called_once_with(limit=5)
        assert action.params.result == [{"package": "com.android.mms", "title": "验证码", "text": "123456"}]

    def test_execute_get_call_state_dispatches_to_adb(self, mocker):
        """验证 GET_CALL_STATE 调用 ADB get_call_state，结果写入 params.result。"""
        mock_dm = mocker.MagicMock()
        mock_adb = mocker.MagicMock()
        mock_adb.get_call_state.return_value = {"state": "ringing", "state_code": 1, "incoming_number": "13800000000"}
        mock_dm.get_adb.return_value = mock_adb

        executor = ActionExecutor(mock_dm)
        action = Action(ActionType.GET_CALL_STATE, ActionParams())
        result = executor.execute(action)
        assert result is True
        mock_adb.get_call_state.assert_called_once()
        assert action.params.result == {"state": "ringing", "state_code": 1, "incoming_number": "13800000000"}

    def test_execute_query_action_failure_returns_false(self, mocker):
        """验证查询动作执行异常时返回 False 且 result 置 None。"""
        mock_dm = mocker.MagicMock()
        mock_adb = mocker.MagicMock()
        mock_adb.get_clipboard.side_effect = RuntimeError("adb 异常")
        mock_dm.get_adb.return_value = mock_adb

        executor = ActionExecutor(mock_dm)
        action = Action(ActionType.GET_CLIPBOARD, ActionParams())
        result = executor.execute(action)
        assert result is False
        assert action.params.result is None

    def test_execute_query_action_no_params_passes_validation(self, mocker):
        """验证查询动作空参数通过 validate（不抛 ValueError）并执行。"""
        mock_dm = mocker.MagicMock()
        mock_adb = mocker.MagicMock()
        mock_adb.get_notifications.return_value = []
        mock_dm.get_adb.return_value = mock_adb

        executor = ActionExecutor(mock_dm)
        action = Action(ActionType.GET_NOTIFICATIONS, ActionParams())
        result = executor.execute(action)
        assert result is True
        mock_adb.get_notifications.assert_called_once_with(limit=20)

    def test_executor_initialization_creates_sub_executors(self, mocker):
        """验证初始化时创建所有子执行器。"""
        mock_dm = mocker.MagicMock()
        executor = ActionExecutor(mock_dm)
        assert ActionType.CLICK in executor._executors
        assert ActionType.DOUBLE_CLICK in executor._executors
        assert ActionType.LONG_CLICK in executor._executors
        assert ActionType.TYPE in executor._executors
        assert ActionType.CLEAR_TEXT in executor._executors
        assert ActionType.SWIPE in executor._executors
        assert ActionType.SWIPE_POINT in executor._executors
        assert ActionType.SCROLL in executor._executors
        assert ActionType.WAIT in executor._executors
