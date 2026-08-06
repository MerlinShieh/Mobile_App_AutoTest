"""短信读取（get_sms_messages）单元测试。

测试 ADBController.get_sms_messages 的 content query 命令构造、
输出解析与参数/注入校验。通过 mock shell() 返回模拟输出，不依赖真机。
"""

import pytest

from mobile_automation.device.adb_controller import ADBController


class TestGetSmsMessages:
    """测试 ADBController.get_sms_messages 的解析与校验。"""

    def test_parse_typical_output(self, mocker):
        """典型 content query 输出正确解析出 address/body/date。"""
        stdout = (
            "Row: 0 address=+8613800138000, body=验证码123456, date=1690000000000\n"
            "Row: 1 address=10086, body=流量提醒, date=1690000001000\n"
        )
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=(stdout, ""))

        result = controller.get_sms_messages()

        assert len(result) == 2
        assert result[0] == {
            "address": "+8613800138000",
            "body": "验证码123456",
            "date": 1690000000000,
        }
        assert result[1] == {"address": "10086", "body": "流量提醒", "date": 1690000001000}

    def test_parse_body_with_comma_and_equals(self, mocker):
        """body 含逗号/等号/中文验证码时解析正确。"""
        stdout = (
            "Row: 0 address=10086, body=验证码 123,456 请勿转发, date=1690000002000\n"
            "Row: 1 address=95555, body=余额=a,000 元, date=1690000003000\n"
        )
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=(stdout, ""))

        result = controller.get_sms_messages()

        assert result[0] == {
            "address": "10086",
            "body": "验证码 123,456 请勿转发",
            "date": 1690000002000,
        }
        assert result[1] == {
            "address": "95555",
            "body": "余额=a,000 元",
            "date": 1690000003000,
        }

    def test_parse_empty_body(self, mocker):
        """body 为空时正常解析。"""
        stdout = "Row: 0 address=10010, body=, date=1690000001000\n"
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=(stdout, ""))

        result = controller.get_sms_messages()

        assert result == [{"address": "10010", "body": "", "date": 1690000001000}]

    def test_empty_output_returns_empty_list(self, mocker):
        """空输出返回空列表。"""
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=("", ""))

        assert controller.get_sms_messages() == []

    def test_shell_failure_returns_empty_list(self, mocker):
        """shell 命令失败（返回 False, stderr）时返回空列表，不抛异常。"""
        controller = ADBController("test-serial")
        mocker.patch.object(
            controller, "shell", return_value=(False, "error: no devices/emulators found")
        )

        assert controller.get_sms_messages() == []

    def test_shell_stderr_returns_empty_list(self, mocker):
        """shell 返回空 stdout 但 stderr 非空时视为命令失败，返回空列表。"""
        controller = ADBController("test-serial")
        mocker.patch.object(
            controller, "shell", return_value=("", "Security exception: Permission Denial")
        )

        assert controller.get_sms_messages() == []

    def test_shell_raises_returns_empty_list(self, mocker):
        """shell 命令抛异常时返回空列表，不向上传播。"""
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", side_effect=RuntimeError("adb 崩溃"))

        assert controller.get_sms_messages() == []

    def test_malformed_row_skipped(self, mocker):
        """畸形行被跳过，不影响其他正常行解析。"""
        stdout = (
            "Row: 0 address=10086, body=正常短信, date=1690000000000\n"
            "garbage line without Row prefix\n"
            "Row: 2 address=10010, body=损坏的日期, date=not_a_number\n"
            "Row: 3 address=10010, body=另一条, date=1690000001000\n"
        )
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=(stdout, ""))

        result = controller.get_sms_messages()

        assert len(result) == 2
        assert result[0] == {"address": "10086", "body": "正常短信", "date": 1690000000000}
        assert result[1] == {"address": "10010", "body": "另一条", "date": 1690000001000}

    def test_invalid_sms_type_rejected(self, mocker):
        """非法 sms_type（spam）抛出 ValueError。"""
        controller = ADBController("test-serial")
        with pytest.raises(ValueError, match="无效的短信类型"):
            controller.get_sms_messages(sms_type="spam")

    def test_injection_sms_type_rejected(self, mocker):
        """sms_type 含注入字符时被拒绝（不在合法取值内）。"""
        controller = ADBController("test-serial")
        with pytest.raises(ValueError, match="无效的短信类型"):
            controller.get_sms_messages(sms_type="inbox;rm -rf /data")

    def test_injection_serial_rejected(self):
        """serial 含注入字符时被拒绝。"""
        controller = ADBController("test-serial;rm -rf /")
        with pytest.raises(ValueError, match="可疑字符"):
            controller.get_sms_messages()

    def test_invalid_limit_rejected(self, mocker):
        """limit 非整数或负数时抛出 ValueError。"""
        controller = ADBController("test-serial")
        with pytest.raises(ValueError, match="limit"):
            controller.get_sms_messages(limit="abc")  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="limit"):
            controller.get_sms_messages(limit=-1)

    def test_limit_str_converted(self, mocker):
        """limit 为数字字符串时正常转换并传入命令。"""
        stdout = "Row: 0 address=10086, body=x, date=1690000000000"
        controller = ADBController("test-serial")
        mock_shell = mocker.patch.object(controller, "shell", return_value=(stdout, ""))

        result = controller.get_sms_messages(limit="5")  # type: ignore[arg-type]

        assert len(result) == 1
        command = mock_shell.call_args[0][0]
        assert "content://sms/inbox" in command
        assert "--limit 5" in command

    def test_default_command_shape(self, mocker):
        """默认参数构造的命令包含 inbox URI、投影列与时间倒序排序。"""
        controller = ADBController("test-serial")
        mock_shell = mocker.patch.object(controller, "shell", return_value=("", ""))

        controller.get_sms_messages()

        command = mock_shell.call_args[0][0]
        assert "content query --uri content://sms/inbox" in command
        assert "--projection address,body,date" in command
        assert '--sort-order "date DESC"' in command
        assert "--limit 20" in command

    def test_sent_type_command(self, mocker):
        """sent 类型构造命令使用 content://sms/sent。"""
        controller = ADBController("test-serial")
        mock_shell = mocker.patch.object(controller, "shell", return_value=("", ""))

        controller.get_sms_messages(sms_type="sent")

        command = mock_shell.call_args[0][0]
        assert "content://sms/sent" in command
