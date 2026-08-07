"""短信读取（get_sms_messages）单元测试。

测试 ADBController.get_sms_messages 的 content query 命令构造、
输出解析与参数/注入校验。通过 mock shell() 返回模拟输出，不依赖真机。
"""

import pytest

from mobile_automation.device.adb_controller import ADBController


class TestGetSmsMessages:
    """测试 ADBController.get_sms_messages 的解析与校验。"""

    def test_parse_typical_output(self, mocker):
        """典型 content query 输出（完整 Row 行）正确解析出 address/body/date。"""
        stdout = (
            "Row: 0 _id=13960, thread_id=200, address=+8613800138000, person=NULL, "
            "date=1690000000000, read=1, body=验证码123456, service_center=+8613800200572, "
            "locked=0, type=1\n"
            "Row: 1 _id=13961, thread_id=201, address=10086, person=NULL, "
            "date=1690000001000, read=1, body=流量提醒, service_center=+8613800200572, "
            "locked=0, type=1\n"
        )
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=(stdout, ""))

        result = controller.get_sms_messages()

        # 命令不带 --sort-order，Python 侧按 date 降序：date=1690000001000 在前
        assert len(result) == 2
        assert result[0] == {
            "address": "10086",
            "body": "流量提醒",
            "date": 1690000001000,
        }
        assert result[1] == {
            "address": "+8613800138000",
            "body": "验证码123456",
            "date": 1690000000000,
        }

    def test_parse_body_with_comma_and_equals(self, mocker):
        """body 含逗号/等号/中文验证码时解析正确（取到下一个字段名）。"""
        stdout = (
            "Row: 0 _id=1, thread_id=1, address=10086, person=NULL, date=1690000002000, "
            "read=1, body=验证码 123,456 请勿转发, service_center=+8613800200572, locked=0\n"
            "Row: 1 _id=2, thread_id=2, address=95555, person=NULL, date=1690000003000, "
            "read=1, body=余额=a,000 元, service_center=+8613800200572, locked=0\n"
        )
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=(stdout, ""))

        result = controller.get_sms_messages()

        # date 降序：date=1690000003000（95555）在前
        assert result[0] == {
            "address": "95555",
            "body": "余额=a,000 元",
            "date": 1690000003000,
        }
        assert result[1] == {
            "address": "10086",
            "body": "验证码 123,456 请勿转发",
            "date": 1690000002000,
        }

    def test_parse_empty_body(self, mocker):
        """body 为空时正常解析。"""
        stdout = (
            "Row: 0 _id=1, thread_id=1, address=10010, person=NULL, "
            "date=1690000001000, read=1, body=, service_center=+8613800200572, locked=0\n"
        )
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
            "Row: 0 _id=1, thread_id=1, address=10086, person=NULL, date=1690000000000, "
            "read=1, body=正常短信, service_center=+8613800200572\n"
            "garbage line without Row prefix\n"
            "Row: 2 _id=3, thread_id=3, address=10010, person=NULL, date=not_a_number, "
            "read=1, body=损坏的日期, service_center=+8613800200572\n"
            "Row: 3 _id=4, thread_id=4, address=10010, person=NULL, date=1690000001000, "
            "read=1, body=另一条, service_center=+8613800200572\n"
        )
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=(stdout, ""))

        result = controller.get_sms_messages()

        # date 降序：date=1690000001000（另一条）在前
        assert len(result) == 2
        assert result[0] == {"address": "10010", "body": "另一条", "date": 1690000001000}
        assert result[1] == {"address": "10086", "body": "正常短信", "date": 1690000000000}

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
        """limit 为数字字符串时正常转换并在 Python 侧截取生效。"""
        rows = "\n".join(
            f"Row: {i} _id={i}, thread_id={i}, address=10000, person=NULL, "
            f"date={1690000000000 + i}, read=1, body=msg{i}, service_center=x\n"
            for i in range(6)
        )
        controller = ADBController("test-serial")
        mock_shell = mocker.patch.object(controller, "shell", return_value=(rows, ""))

        result = controller.get_sms_messages(limit="5")  # type: ignore[arg-type]

        assert len(result) == 5
        command = mock_shell.call_args[0][0]
        assert "content://sms/inbox" in command
        assert "--limit" not in command

    def test_default_command_shape(self, mocker):
        """默认命令为无附加参数的 content query（兼容不支持投影/排序/limit 的 ROM）。"""
        controller = ADBController("test-serial")
        mock_shell = mocker.patch.object(controller, "shell", return_value=("", ""))

        controller.get_sms_messages()

        command = mock_shell.call_args[0][0]
        assert command == "content query --uri content://sms/inbox"
        assert "--projection" not in command
        assert "--sort-order" not in command
        assert "--limit" not in command

    def test_sent_type_command(self, mocker):
        """sent 类型构造命令使用 content://sms/sent。"""
        controller = ADBController("test-serial")
        mock_shell = mocker.patch.object(controller, "shell", return_value=("", ""))

        controller.get_sms_messages(sms_type="sent")

        command = mock_shell.call_args[0][0]
        assert "content://sms/sent" in command

    def test_parse_full_row_miui_format(self, mocker):
        """MIUI ROM 实测格式（完整字段行，body 含中文/逗号/URL）正确解析。"""
        stdout = (
            "Row: 0 _id=13960, thread_id=200, address=10086, person=NULL, "
            "date=1765793247858, read=1, status=-1, "
            "body=【停机前提醒】您的账户余额不足,请及时充值 https://t.cn/abc123, "
            "service_center=+8613800200572, locked=0, type=1\n"
        )
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=(stdout, ""))

        result = controller.get_sms_messages()

        assert result == [
            {
                "address": "10086",
                "body": "【停机前提醒】您的账户余额不足,请及时充值 https://t.cn/abc123",
                "date": 1765793247858,
            }
        ]

    def test_date_desc_sort(self, mocker):
        """命令不带 --sort-order，Python 侧按 date 降序排序。"""
        stdout = (
            "Row: 0 _id=1, thread_id=1, address=10001, person=NULL, date=1690000001000, "
            "read=1, body=older, service_center=x\n"
            "Row: 1 _id=2, thread_id=2, address=10002, person=NULL, date=1690000003000, "
            "read=1, body=newest, service_center=x\n"
            "Row: 2 _id=3, thread_id=3, address=10003, person=NULL, date=1690000002000, "
            "read=1, body=middle, service_center=x\n"
        )
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=(stdout, ""))

        result = controller.get_sms_messages()

        assert [item["date"] for item in result] == [
            1690000003000,
            1690000002000,
            1690000001000,
        ]
        assert result[0]["body"] == "newest"

    def test_limit_truncation(self, mocker):
        """命令不带 --limit，Python 侧截取最新 limit 条。"""
        rows = "\n".join(
            f"Row: {i} _id={i}, thread_id={i}, address=10000, person=NULL, "
            f"date={1690000000000 + i}, read=1, body=msg{i}, service_center=x\n"
            for i in range(5)
        )
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=(rows, ""))

        result = controller.get_sms_messages(limit=2)

        # date 最大（最新）的两条
        assert [item["date"] for item in result] == [1690000000004, 1690000000003]
