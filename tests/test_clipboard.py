"""剪贴板读写（get_clipboard / set_clipboard）单元测试。

测试 ADBController 的 cmd clipboard 命令构造、输出 trim、失败容错
与 shlex.quote 转义。通过 mock shell() 返回模拟输出，不依赖真机。
"""

import shlex

import pytest

from mobile_automation.device.adb_controller import ADBController


class TestGetClipboard:
    """测试 ADBController.get_clipboard 的读取与容错。"""

    def test_get_clipboard_trims_newline(self, mocker):
        """剪贴板读取成功，输出末尾换行被 trim。"""
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=("hello\n", ""))

        assert controller.get_clipboard() == "hello"

    def test_get_clipboard_unicode_and_special_chars(self, mocker):
        """含中文/特殊字符的剪贴板文本正确返回（trim 不影响内容）。"""
        controller = ADBController("test-serial")
        text = "验证码：A1B2@#$%^&*() 测试"
        mocker.patch.object(controller, "shell", return_value=(text + "\n", ""))

        assert controller.get_clipboard() == text

    def test_get_clipboard_empty_output_returns_empty(self, mocker):
        """剪贴板为空（无有效输出）时返回空字符串。"""
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=("", ""))

        assert controller.get_clipboard() == ""

    def test_get_clipboard_shell_failure_returns_empty(self, mocker):
        """shell 命令失败（无有效 stdout）时返回空字符串，不抛异常。"""
        controller = ADBController("test-serial")
        mocker.patch.object(
            controller, "shell", return_value=(False, "error: no devices/emulators found")
        )

        assert controller.get_clipboard() == ""

    def test_get_clipboard_stderr_returns_empty(self, mocker):
        """stderr 非空（如无权限）时视为命令失败，返回空字符串。"""
        controller = ADBController("test-serial")
        mocker.patch.object(
            controller,
            "shell",
            return_value=("some text", "Security exception: Permission Denial"),
        )

        assert controller.get_clipboard() == ""

    def test_get_clipboard_shell_raises_returns_empty(self, mocker):
        """shell 命令抛异常时返回空字符串，不向上传播。"""
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", side_effect=RuntimeError("adb 崩溃"))

        assert controller.get_clipboard() == ""

    def test_get_clipboard_fallback_command_shape(self, mocker):
        """service call 通道失败时回退命令为 cmd clipboard get（标准 ROM）。"""
        controller = ADBController("test-serial")
        mock_shell = mocker.patch.object(
            controller,
            "shell",
            side_effect=[("x\n", ""), ("y\n", "")],
        )

        controller.get_clipboard()

        assert mock_shell.call_args_list[0][0][0] == "service call clipboard 1"
        assert mock_shell.call_args_list[1][0][0] == "cmd clipboard get"

    def test_get_clipboard_primary_command_service_call(self, mocker):
        """读取优先走 service call clipboard 1（部分定制 ROM 无 cmd clipboard）。"""
        stdout = (
            "Result: Parcel(\n"
            "  0x00000000: 00000000 00000000 00650068 006c006c '........e.h.l.l'\n"
            "  0x00000010: 0000006f 00000000 00000000 00000000 'o..............'\n"
            ")\n"
        )
        controller = ADBController("test-serial")
        mock_shell = mocker.patch.object(controller, "shell", return_value=(stdout, ""))

        text = controller.get_clipboard()

        assert text == "hello"
        assert mock_shell.call_count == 1
        assert mock_shell.call_args[0][0] == "service call clipboard 1"

    def test_get_clipboard_service_call_empty_returns_empty(self, mocker):
        """service call 返回 "No items"（剪贴板为空）时返回空字符串。"""
        stdout = (
            "Result: Parcel(\n"
            "  0x00000000: 00000000 00000000 006f004e 00690020 '........N.o. .i'\n"
            "  0x00000010: 00650074 0073006d 00000000 00000000 't.e.m.s........'\n"
            "  0x00000020: 00000000 00000000 00000000 00000000 '................'\n"
            ")\n"
        )
        controller = ADBController("test-serial")
        mock_shell = mocker.patch.object(controller, "shell", return_value=(stdout, ""))

        assert controller.get_clipboard() == ""
        assert mock_shell.call_count == 1
        assert mock_shell.call_args[0][0] == "service call clipboard 1"

    def test_get_clipboard_service_call_single_line_parcel(self, mocker):
        """兼容单行 Parcel(...) 输出格式。"""
        stdout = "Result: Parcel(00000000 00000000 00650068 006c006c 0000006f)\n"
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=(stdout, ""))

        assert controller.get_clipboard() == "hello"

    def test_get_clipboard_service_call_fallback_to_cmd(self, mocker):
        """service call 通道失败（无 Parcel 输出）时回退 cmd clipboard get。"""
        controller = ADBController("test-serial")
        mock_shell = mocker.patch.object(
            controller,
            "shell",
            side_effect=[
                ("No shell command implementation\n", ""),
                ("hello world\n", ""),
            ],
        )

        assert controller.get_clipboard() == "hello world"

        assert mock_shell.call_count == 2
        assert mock_shell.call_args_list[0][0][0] == "service call clipboard 1"
        assert mock_shell.call_args_list[1][0][0] == "cmd clipboard get"

    def test_get_clipboard_service_call_stderr_fallback(self, mocker):
        """service call 返回 stderr 时回退 cmd clipboard get。"""
        controller = ADBController("test-serial")
        mock_shell = mocker.patch.object(
            controller,
            "shell",
            side_effect=[
                ("Result: Parcel(...)", "Error: unknown transaction"),
                ("cmd 内容\n", ""),
            ],
        )

        assert controller.get_clipboard() == "cmd 内容"
        assert mock_shell.call_count == 2

    def test_get_clipboard_injection_serial_rejected(self):
        """serial 含注入字符时 get_clipboard 抛出 ValueError。"""
        controller = ADBController("test-serial;rm -rf /")

        with pytest.raises(ValueError, match="可疑字符"):
            controller.get_clipboard()


class TestSetClipboard:
    """测试 ADBController.set_clipboard 的写入与校验。"""

    def test_set_clipboard_success_returns_true(self, mocker):
        """写入成功（无 stderr）返回 True。"""
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=("", ""))

        assert controller.set_clipboard("hello world") is True

    def test_set_clipboard_command_quoted(self, mocker):
        """命令中的文本经 shlex.quote 转义（含空格时用单引号包裹）。"""
        controller = ADBController("test-serial")
        mock_shell = mocker.patch.object(controller, "shell", return_value=("", ""))

        controller.set_clipboard("hello world")

        command = mock_shell.call_args[0][0]
        assert command == "cmd clipboard set 'hello world'"

    def test_set_clipboard_escapes_quotes_and_spaces(self, mocker):
        """text 含引号/空格时命令正确转义（与 shlex.quote 结果一致）。"""
        controller = ADBController("test-serial")
        mock_shell = mocker.patch.object(controller, "shell", return_value=("", ""))

        text = "it's a \"test\" 验证码"
        assert controller.set_clipboard(text) is True

        command = mock_shell.call_args[0][0]
        assert command == "cmd clipboard set " + shlex.quote(text)
        assert command.startswith("cmd clipboard set ")

    def test_set_clipboard_empty_text_returns_false(self, mocker):
        """text 为空或 None 时返回 False，且不执行 shell。"""
        controller = ADBController("test-serial")
        mock_shell = mocker.patch.object(controller, "shell", return_value=("", ""))

        assert controller.set_clipboard("") is False
        assert controller.set_clipboard(None) is False  # type: ignore[arg-type]
        assert mock_shell.call_count == 0

    def test_set_clipboard_shell_failure_returns_false(self, mocker):
        """shell 返回 stderr（失败）时返回 False。"""
        controller = ADBController("test-serial")
        mocker.patch.object(
            controller, "shell", return_value=("", "Error: cannot write clipboard")
        )

        assert controller.set_clipboard("hello") is False

    def test_set_clipboard_shell_raises_returns_false(self, mocker):
        """shell 命令抛异常时返回 False，不向上传播。"""
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", side_effect=RuntimeError("adb 崩溃"))

        assert controller.set_clipboard("hello") is False

    def test_set_clipboard_injection_serial_rejected(self):
        """serial 含注入字符时 set_clipboard 抛出 ValueError。"""
        controller = ADBController("test-serial;rm -rf /")

        with pytest.raises(ValueError, match="可疑字符"):
            controller.set_clipboard("hello")
