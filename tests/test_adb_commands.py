"""ADB 基础交互命令封装单元测试。

测试 ADBController 的 input tap/swipe/text/keyevent、press_*、
app_start/app_stop、list_packages、get_window_focus、get_resolution
等命令的命令构造、参数校验、失败容错与 serial 注入防御。
通过 mock shell() 返回模拟输出，不依赖真机。
"""

import shlex

import pytest

from mobile_automation.device.adb_controller import ADBController


class TestInputTap:
    """测试 ADBController.input_tap 的构造与校验。"""

    def test_command_shape(self, mocker):
        """合法坐标构造 input tap 命令并返回 True。"""
        controller = ADBController("test-serial")
        mock_shell = mocker.patch.object(controller, "shell", return_value=("", ""))

        assert controller.input_tap(100, 200) is True

        assert mock_shell.call_args[0][0] == "input tap 100 200"

    @pytest.mark.parametrize(
        "x,y",
        [
            (-1, 10),       # 负数
            (10, -1),       # 负数
            (1.5, 10),      # 浮点
            (True, 10),     # bool（int 子类）
            ("10", 10),     # 字符串
        ],
    )
    def test_invalid_coordinate_raises_value_error(self, x, y):
        """x/y 非法（负数/浮点/bool/字符串）时抛 ValueError。"""
        controller = ADBController("test-serial")

        with pytest.raises(ValueError):
            controller.input_tap(x, y)

    def test_shell_failure_returns_false(self, mocker):
        """shell 返回 stderr（失败）时返回 False。"""
        controller = ADBController("test-serial")
        mocker.patch.object(
            controller, "shell", return_value=("", "Error: input device not found")
        )

        assert controller.input_tap(1, 1) is False

    def test_shell_raises_returns_false(self, mocker):
        """shell 命令抛异常时返回 False，不向上传播。"""
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", side_effect=RuntimeError("adb 崩溃"))

        assert controller.input_tap(1, 1) is False

    def test_injection_serial_rejected(self):
        """serial 含注入字符时抛 ValueError。"""
        controller = ADBController("test-serial;rm -rf /")

        with pytest.raises(ValueError, match="可疑字符"):
            controller.input_tap(1, 1)


class TestInputSwipe:
    """测试 ADBController.input_swipe 的构造与校验。"""

    def test_command_default_duration(self, mocker):
        """默认时长 300ms 的滑动命令构造正确。"""
        controller = ADBController("test-serial")
        mock_shell = mocker.patch.object(controller, "shell", return_value=("", ""))

        assert controller.input_swipe(0, 100, 200, 300) is True

        assert mock_shell.call_args[0][0] == "input swipe 0 100 200 300 300"

    def test_command_custom_duration(self, mocker):
        """自定义时长 500ms 的滑动命令构造正确。"""
        controller = ADBController("test-serial")
        mock_shell = mocker.patch.object(controller, "shell", return_value=("", ""))

        assert controller.input_swipe(0, 0, 100, 100, 500) is True

        assert mock_shell.call_args[0][0] == "input swipe 0 0 100 100 500"

    def test_invalid_coordinate_raises_value_error(self):
        """任一坐标为负数时抛 ValueError。"""
        controller = ADBController("test-serial")

        with pytest.raises(ValueError):
            controller.input_swipe(-1, 0, 100, 100)
        with pytest.raises(ValueError):
            controller.input_swipe(0, 0, 100, -100)

    @pytest.mark.parametrize("duration", [-1, 1.5, "300", True])
    def test_invalid_duration_raises_value_error(self, duration):
        """duration_ms 非法（负数/浮点/字符串/bool）时抛 ValueError。"""
        controller = ADBController("test-serial")

        with pytest.raises(ValueError):
            controller.input_swipe(0, 0, 100, 100, duration)

    def test_shell_failure_returns_false(self, mocker):
        """shell 返回 stderr（失败）时返回 False。"""
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=("", "Error: swipe failed"))

        assert controller.input_swipe(0, 0, 100, 100) is False


class TestInputText:
    """测试 ADBController.input_text 的转义与校验。"""

    def test_command_plain_ascii(self, mocker):
        """纯 ASCII 无特殊字符文本直接拼接（shlex.quote 原样返回）。"""
        controller = ADBController("test-serial")
        mock_shell = mocker.patch.object(controller, "shell", return_value=("", ""))

        assert controller.input_text("hello") is True

        assert mock_shell.call_args[0][0] == "input text hello"

    def test_command_quoted_spaces(self, mocker):
        """含空格的文本经 shlex.quote 用单引号包裹。"""
        controller = ADBController("test-serial")
        mock_shell = mocker.patch.object(controller, "shell", return_value=("", ""))

        assert controller.input_text("hello world") is True

        assert mock_shell.call_args[0][0] == "input text 'hello world'"

    def test_command_quotes_and_special_chars(self, mocker):
        """含引号/中文的文本转义结果与 shlex.quote 一致。"""
        controller = ADBController("test-serial")
        mock_shell = mocker.patch.object(controller, "shell", return_value=("", ""))

        text = "it's a \"test\" 验证码"
        assert controller.input_text(text) is True

        command = mock_shell.call_args[0][0]
        assert command == "input text " + shlex.quote(text)

    def test_command_unicode_quoted(self, mocker):
        """中文文本仍尝试传递（shlex.quote 单引号包裹），不阻断。"""
        controller = ADBController("test-serial")
        mock_shell = mocker.patch.object(controller, "shell", return_value=("", ""))

        assert controller.input_text("你好世界") is True

        assert mock_shell.call_args[0][0] == "input text '你好世界'"

    def test_empty_text_returns_false(self, mocker):
        """text 为空或 None 时返回 False，且不执行 shell。"""
        controller = ADBController("test-serial")
        mock_shell = mocker.patch.object(controller, "shell", return_value=("", ""))

        assert controller.input_text("") is False
        assert controller.input_text(None) is False  # type: ignore[arg-type]
        assert mock_shell.call_count == 0

    def test_shell_raises_returns_false(self, mocker):
        """shell 命令抛异常时返回 False，不向上传播。"""
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", side_effect=RuntimeError("adb 崩溃"))

        assert controller.input_text("hello") is False

    def test_injection_serial_rejected(self):
        """serial 含注入字符时抛 ValueError。"""
        controller = ADBController("test-serial;rm -rf /")

        with pytest.raises(ValueError, match="可疑字符"):
            controller.input_text("hello")


class TestInputKeyevent:
    """测试 ADBController.input_keyevent 的构造与校验。"""

    def test_command_shape(self, mocker):
        """合法 keycode 构造 input keyevent 命令并返回 True。"""
        controller = ADBController("test-serial")
        mock_shell = mocker.patch.object(controller, "shell", return_value=("", ""))

        assert controller.input_keyevent(4) is True

        assert mock_shell.call_args[0][0] == "input keyevent 4"

    @pytest.mark.parametrize("keycode", [4.5, "4", True, None])
    def test_invalid_keycode_raises_value_error(self, keycode):
        """keycode 非法（浮点/字符串/bool/None）时抛 ValueError。"""
        controller = ADBController("test-serial")

        with pytest.raises(ValueError):
            controller.input_keyevent(keycode)

    def test_shell_failure_returns_false(self, mocker):
        """shell 返回 stderr（失败）时返回 False。"""
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=("", "Error: keyevent failed"))

        assert controller.input_keyevent(4) is False

    def test_injection_serial_rejected(self):
        """serial 含注入字符时抛 ValueError。"""
        controller = ADBController("test-serial;rm -rf /")

        with pytest.raises(ValueError, match="可疑字符"):
            controller.input_keyevent(4)


class TestPressShortcuts:
    """测试 ADBController.press_back / press_home / press_recent。"""

    def test_press_back_uses_keyevent_4(self, mocker):
        """返回键发送 KeyEvent 4。"""
        controller = ADBController("test-serial")
        mock_ke = mocker.patch.object(controller, "input_keyevent", return_value=True)

        assert controller.press_back() is True

        mock_ke.assert_called_once_with(4)

    def test_press_home_uses_keyevent_3(self, mocker):
        """Home 键发送 KeyEvent 3。"""
        controller = ADBController("test-serial")
        mock_ke = mocker.patch.object(controller, "input_keyevent", return_value=True)

        assert controller.press_home() is True

        mock_ke.assert_called_once_with(3)

    def test_press_recent_uses_keyevent_187(self, mocker):
        """最近任务键发送 KeyEvent 187。"""
        controller = ADBController("test-serial")
        mock_ke = mocker.patch.object(controller, "input_keyevent", return_value=True)

        assert controller.press_recent() is True

        mock_ke.assert_called_once_with(187)

    def test_press_propagates_failure(self, mocker):
        """底层按键失败时 press_* 返回 False。"""
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "input_keyevent", return_value=False)

        assert controller.press_back() is False


class TestAppStart:
    """测试 ADBController.app_start 的启动命令与兜底。"""

    def test_command_shape_am_start(self, mocker):
        """优先使用 am start 按包名匹配 LAUNCHER 活动。"""
        controller = ADBController("test-serial")
        mock_shell = mocker.patch.object(controller, "shell", return_value=("", ""))

        assert controller.app_start("com.example.app") is True

        assert mock_shell.call_args[0][0] == (
            "am start -a android.intent.action.MAIN "
            "-c android.intent.category.LAUNCHER -p com.example.app"
        )
        assert mock_shell.call_count == 1

    def test_am_start_failure_falls_back_monkey(self, mocker):
        """am start 失败时回退到 monkey 启动器。"""
        controller = ADBController("test-serial")
        mock_shell = mocker.patch.object(
            controller,
            "shell",
            side_effect=[
                ("", "Error: Activity class not found"),
                ("", ""),
            ],
        )

        assert controller.app_start("com.example.app") is True

        assert mock_shell.call_args_list[0][0][0] == (
            "am start -a android.intent.action.MAIN "
            "-c android.intent.category.LAUNCHER -p com.example.app"
        )
        assert mock_shell.call_args_list[1][0][0] == (
            "monkey -p com.example.app -c android.intent.category.LAUNCHER 1"
        )

    def test_both_fail_returns_false(self, mocker):
        """两种启动方式均失败时返回 False。"""
        controller = ADBController("test-serial")
        mock_shell = mocker.patch.object(
            controller, "shell", side_effect=[("", "err"), ("", "err2")]
        )

        assert controller.app_start("com.example.app") is False
        assert mock_shell.call_count == 2

    @pytest.mark.parametrize("package", ["", "com.example;rm -rf /", "com example", "包名中文"])
    def test_invalid_package_raises_value_error(self, package):
        """包名非法（空/含注入字符/空格/中文）时抛 ValueError。"""
        controller = ADBController("test-serial")

        with pytest.raises(ValueError):
            controller.app_start(package)

    def test_injection_serial_rejected(self):
        """serial 含注入字符时抛 ValueError。"""
        controller = ADBController("test-serial;rm -rf /")

        with pytest.raises(ValueError, match="可疑字符"):
            controller.app_start("com.example.app")


class TestAppStop:
    """测试 ADBController.app_stop 的构造与校验。"""

    def test_command_shape(self, mocker):
        """合法包名构造 am force-stop 命令并返回 True。"""
        controller = ADBController("test-serial")
        mock_shell = mocker.patch.object(controller, "shell", return_value=("", ""))

        assert controller.app_stop("com.example.app") is True

        assert mock_shell.call_args[0][0] == "am force-stop com.example.app"

    @pytest.mark.parametrize("package", ["", "com.example;ls", 123, None])
    def test_invalid_package_raises_value_error(self, package):
        """包名非法（空/注入字符/非字符串）时抛 ValueError。"""
        controller = ADBController("test-serial")

        with pytest.raises(ValueError):
            controller.app_stop(package)

    def test_shell_failure_returns_false(self, mocker):
        """shell 返回 stderr（失败）时返回 False。"""
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=("", "Error: force-stop failed"))

        assert controller.app_stop("com.example.app") is False

    def test_injection_serial_rejected(self):
        """serial 含注入字符时抛 ValueError。"""
        controller = ADBController("test-serial;rm -rf /")

        with pytest.raises(ValueError, match="可疑字符"):
            controller.app_stop("com.example.app")


class TestListPackages:
    """测试 ADBController.list_packages 的过滤与解析。"""

    def test_third_party_flag_default(self, mocker):
        """默认 include_system=False 使用 -3（仅三方包）。"""
        controller = ADBController("test-serial")
        mock_shell = mocker.patch.object(controller, "shell", return_value=("", ""))

        controller.list_packages()

        assert mock_shell.call_args[0][0] == "pm list packages -3"

    def test_system_flag(self, mocker):
        """include_system=True 使用 -s（仅系统包）。"""
        controller = ADBController("test-serial")
        mock_shell = mocker.patch.object(controller, "shell", return_value=("", ""))

        controller.list_packages(include_system=True)

        assert mock_shell.call_args[0][0] == "pm list packages -s"

    def test_parse_package_prefix(self, mocker):
        """解析 package: 前缀，跳过无效行与空行。"""
        stdout = (
            "package:com.example.app\n"
            "package:com.example.other\n"
            "some:invalid-line\n"
            "\n"
        )
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=(stdout, ""))

        assert controller.list_packages() == ["com.example.app", "com.example.other"]

    def test_shell_failure_returns_empty(self, mocker):
        """shell 返回 stderr（失败）时返回空列表。"""
        controller = ADBController("test-serial")
        mocker.patch.object(
            controller, "shell", return_value=("", "Error: no devices/emulators found")
        )

        assert controller.list_packages() == []

    def test_shell_raises_returns_empty(self, mocker):
        """shell 命令抛异常时返回空列表，不向上传播。"""
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", side_effect=RuntimeError("adb 崩溃"))

        assert controller.list_packages() == []

    def test_injection_serial_rejected(self):
        """serial 含注入字符时抛 ValueError。"""
        controller = ADBController("test-serial;rm -rf /")

        with pytest.raises(ValueError, match="可疑字符"):
            controller.list_packages()


class TestGetWindowFocus:
    """测试 ADBController.get_window_focus 的解析与容错。"""

    FOCUS_OUTPUT = """\
WINDOW MANAGER WINDOWS (dumpsys window windows)
  Window #0 Window{abc123 u0 com.android.settings/com.android.settings.Settings}:
    mCurrentFocus=Window{abc123 u0 com.android.settings/com.android.settings.Settings}
"""

    def test_parse_focus_window(self, mocker):
        """解析 mCurrentFocus 行，返回 = 之后的内容。"""
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=(self.FOCUS_OUTPUT, ""))

        assert (
            controller.get_window_focus()
            == "Window{abc123 u0 com.android.settings/com.android.settings.Settings}"
        )

    def test_null_focus_returns_empty(self, mocker):
        """mCurrentFocus=null 时返回空字符串。"""
        stdout = "  mCurrentFocus=null\n"
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=(stdout, ""))

        assert controller.get_window_focus() == ""

    def test_no_focus_line_returns_empty(self, mocker):
        """输出中无 mCurrentFocus 行时返回空字符串。"""
        stdout = "WINDOW MANAGER WINDOWS (dumpsys window windows)\n"
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=(stdout, ""))

        assert controller.get_window_focus() == ""

    def test_shell_failure_returns_empty(self, mocker):
        """shell 返回 stderr（失败）时返回空字符串。"""
        controller = ADBController("test-serial")
        mocker.patch.object(
            controller, "shell", return_value=("", "Error: no devices/emulators found")
        )

        assert controller.get_window_focus() == ""

    def test_command_shape(self, mocker):
        """查询命令为 dumpsys window（兼容不输出 mCurrentFocus 的 ROM）。"""
        controller = ADBController("test-serial")
        mock_shell = mocker.patch.object(controller, "shell", return_value=("", ""))

        controller.get_window_focus()

        assert mock_shell.call_args[0][0] == "dumpsys window"

    def test_parse_focused_app_priority(self, mocker):
        """MIUI ROM：优先解析 mFocusedApp 提取「包名/Activity」。"""
        stdout = (
            "WINDOW MANAGER WINDOWS (dumpsys window)\n"
            "  mCurrentFocus=Window{d8d9d01 u0 PopupWindow:1ca877a}\n"
            "  mFocusedApp=ActivityRecord{133663800 u0 com.miui.calculator/.cal.CalculatorActivity t47}\n"
        )
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=(stdout, ""))

        assert (
            controller.get_window_focus()
            == "com.miui.calculator/.cal.CalculatorActivity"
        )

    def test_focused_app_null_fallback_to_current_focus(self, mocker):
        """mFocusedApp=null 时回退解析 mCurrentFocus 的 Window 名。"""
        stdout = (
            "WINDOW MANAGER WINDOWS (dumpsys window)\n"
            "  mCurrentFocus=Window{abc123 u0 com.android.settings/com.android.settings.Settings}\n"
            "  mFocusedApp=null\n"
        )
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=(stdout, ""))

        assert (
            controller.get_window_focus()
            == "Window{abc123 u0 com.android.settings/com.android.settings.Settings}"
        )

    def test_injection_serial_rejected(self):
        """serial 含注入字符时抛 ValueError。"""
        controller = ADBController("test-serial;rm -rf /")

        with pytest.raises(ValueError, match="可疑字符"):
            controller.get_window_focus()


class TestGetResolution:
    """测试 ADBController.get_resolution 的解析与容错。"""

    def test_parse_physical_size(self, mocker):
        """解析 Physical size 为 (宽, 高)。"""
        stdout = "Physical size: 1440x3200\nOverride size: 1080x2400\n"
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=(stdout, ""))

        assert controller.get_resolution() == (1440, 3200)

    def test_parse_only_physical_size(self, mocker):
        """仅有 Physical size 时正常解析。"""
        stdout = "Physical size: 1080x2340\n"
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=(stdout, ""))

        assert controller.get_resolution() == (1080, 2340)

    def test_unparseable_returns_zeros(self, mocker):
        """输出中无 Physical size 字段时返回 (0, 0)。"""
        stdout = "Override size: 1080x2400\n"
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=(stdout, ""))

        assert controller.get_resolution() == (0, 0)

    def test_shell_failure_returns_zeros(self, mocker):
        """shell 返回 stderr（失败）时返回 (0, 0)。"""
        controller = ADBController("test-serial")
        mocker.patch.object(
            controller, "shell", return_value=("", "Error: no devices/emulators found")
        )

        assert controller.get_resolution() == (0, 0)

    def test_shell_raises_returns_zeros(self, mocker):
        """shell 命令抛异常时返回 (0, 0)，不向上传播。"""
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", side_effect=RuntimeError("adb 崩溃"))

        assert controller.get_resolution() == (0, 0)

    def test_injection_serial_rejected(self):
        """serial 含注入字符时抛 ValueError。"""
        controller = ADBController("test-serial;rm -rf /")

        with pytest.raises(ValueError, match="可疑字符"):
            controller.get_resolution()
