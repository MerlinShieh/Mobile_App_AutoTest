"""系统通知读取（get_notifications）单元测试。

测试 ADBController.get_notifications 的 dumpsys notification 输出解析、
limit 参数校验、serial 注入防御与失败容错。通过 mock shell() 返回
模拟输出，不依赖真机。
"""

import pytest

from mobile_automation.device.adb_controller import ADBController


# 典型 dumpsys notification 输出（真实 MIUI 格式：0x... 后带冒号）
TYPICAL_OUTPUT = """\
Current notification status:
  Notification List (user=0):
    NotificationRecord(0x0197e345: pkg=com.android.mms user=UserHandle{0} id=1005 tag=null uid=10023)
      icon=0x7f0801b4
      pri=2 score=0
      key=0|com.android.mms|1005|null|10023
      contentIntent=PendingIntent{...}
      tickerText=null
      extras=Bundle[{android.title=StringValue{短信通知}, android.text=StringValue{验证码 123456}, android.subText=StringValue{}, ...}]
    NotificationRecord(0x0197e346: pkg=com.android.vending user=UserHandle{0} id=42 tag=null uid=10020)
      icon=0x7f0801c1
      pri=1 score=0
      key=0|com.android.vending|42|null|10020
      extras=Bundle[{android.title=StringValue{应用更新}, android.text=StringValue{Play 商店有新应用可用}, ...}]
"""


class TestGetNotifications:
    """测试 ADBController.get_notifications 的解析与校验。"""

    def test_parse_typical_output(self, mocker):
        """典型输出正确解析出 package/title/text。"""
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=(TYPICAL_OUTPUT, ""))

        result = controller.get_notifications()

        assert len(result) == 2
        assert result[0] == {
            "package": "com.android.mms",
            "title": "短信通知",
            "text": "验证码 123456",
        }
        assert result[1] == {
            "package": "com.android.vending",
            "title": "应用更新",
            "text": "Play 商店有新应用可用",
        }

    def test_parse_plain_value_format(self, mocker):
        """android.title/text 为直接明文（非 StringValue 包裹）时兼容解析。"""
        stdout = (
            "  NotificationRecord(0x01aabbcc pkg=com.example.app user=UserHandle{0} id=1 tag=null uid=10001)\n"
            "    android.title=验证码通知\n"
            "    android.text=您的验证码是 888888\n"
        )
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=(stdout, ""))

        result = controller.get_notifications()

        assert result == [
            {
                "package": "com.example.app",
                "title": "验证码通知",
                "text": "您的验证码是 888888",
            }
        ]

    def test_missing_title_text_empty_string(self, mocker):
        """NotificationRecord 缺少 title/text 时提取为空字符串。"""
        stdout = (
            "  NotificationRecord(0x01ddeeff pkg=com.android.systemui user=UserHandle{0} id=9 tag=null uid=1000)\n"
            "    icon=0x7f0801a7\n"
            "    pri=2 score=0\n"
            "    extras=Bundle[{android.tickerText=StringValue{}, ...}]\n"
        )
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=(stdout, ""))

        result = controller.get_notifications()

        assert result == [{"package": "com.android.systemui", "title": "", "text": ""}]

    def test_empty_output_returns_empty_list(self, mocker):
        """无 NotificationRecord（无通知）时返回空列表。"""
        stdout = (
            "Current notification status:\n"
            "  Notification List (user=0):\n"
        )
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=(stdout, ""))

        assert controller.get_notifications() == []

    def test_shell_failure_returns_empty_list(self, mocker):
        """shell 命令失败（返回 False, stderr）时返回空列表，不抛异常。"""
        controller = ADBController("test-serial")
        mocker.patch.object(
            controller, "shell", return_value=(False, "error: no devices/emulators found")
        )

        assert controller.get_notifications() == []

    def test_shell_stderr_returns_empty_list(self, mocker):
        """shell 返回 stderr 非空（如无权限）时视为命令失败，返回空列表。"""
        controller = ADBController("test-serial")
        mocker.patch.object(
            controller, "shell", return_value=(TYPICAL_OUTPUT, "Security exception: Permission Denial")
        )

        assert controller.get_notifications() == []

    def test_shell_raises_returns_empty_list(self, mocker):
        """shell 命令抛异常时返回空列表，不向上传播。"""
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", side_effect=RuntimeError("adb 崩溃"))

        assert controller.get_notifications() == []

    def test_invalid_limit_rejected(self, mocker):
        """limit 非整数或负数时抛出 ValueError。"""
        controller = ADBController("test-serial")
        with pytest.raises(ValueError, match="limit"):
            controller.get_notifications(limit="abc")  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="limit"):
            controller.get_notifications(limit=-1)

    def test_injection_serial_rejected(self):
        """serial 含注入字符时被拒绝。"""
        controller = ADBController("test-serial;rm -rf /")

        with pytest.raises(ValueError, match="可疑字符"):
            controller.get_notifications()

    def test_limit_truncation(self, mocker):
        """多条通知时只返回前 limit 条（截断生效）。"""
        records = []
        for i in range(5):
            records.append(
                f"  NotificationRecord(0x0100000{i} pkg=com.example.app{i} "
                f"user=UserHandle{{0}} id={i} tag=null uid=1000{i})\n"
                f"    extras=Bundle[{{android.title=StringValue{{标题{i}}}, "
                f"android.text=StringValue{{正文{i}}}, ...}}]\n"
            )
        stdout = "  Notification List (user=0):\n" + "\n".join(records)
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=(stdout, ""))

        result = controller.get_notifications(limit=3)

        assert len(result) == 3
        assert [item["package"] for item in result] == [
            "com.example.app0",
            "com.example.app1",
            "com.example.app2",
        ]

    def test_limit_str_converted(self, mocker):
        """limit 为数字字符串时正常转换并生效。"""
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=(TYPICAL_OUTPUT, ""))

        result = controller.get_notifications(limit="1")  # type: ignore[arg-type]

        assert len(result) == 1
        assert result[0]["package"] == "com.android.mms"

    def test_command_shape(self, mocker):
        """读取命令为 dumpsys notification（不带 --noredact）。"""
        controller = ADBController("test-serial")
        mock_shell = mocker.patch.object(controller, "shell", return_value=("", ""))

        controller.get_notifications()

        assert mock_shell.call_args[0][0] == "dumpsys notification"
        assert "--noredact" not in mock_shell.call_args[0][0]

    def test_parse_redacted_title_text_empty(self, mocker):
        """无 --noredact 时 title/text 脱敏为 String [length=N]，置空字符串。"""
        stdout = (
            "Current notification status:\n"
            "  Notification List (user=0):\n"
            "    NotificationRecord(0x0197e345 pkg=com.android.mms user=UserHandle{0} id=1005 tag=null uid=10023)\n"
            "      icon=0x7f0801b4\n"
            "      extras=Bundle[{android.title=String [length=11], android.text=String [length=32], android.subText=String [length=0], ...}]\n"
        )
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=(stdout, ""))

        result = controller.get_notifications()

        assert result == [{"package": "com.android.mms", "title": "", "text": ""}]

    def test_parse_mixed_redacted_and_plain(self, mocker):
        """同一输出中脱敏与完整通知混合时分别正确处理。"""
        stdout = (
            "  Notification List (user=0):\n"
            "    NotificationRecord(0x01 pkg=com.android.mms user=UserHandle{0} id=1 tag=null uid=1000)\n"
            "      extras=Bundle[{android.title=String [length=11], android.text=String [length=32], ...}]\n"
            "    NotificationRecord(0x02 pkg=com.example.app user=UserHandle{0} id=2 tag=null uid=1001)\n"
            "      extras=Bundle[{android.title=StringValue{完整标题}, android.text=StringValue{完整正文}, ...}]\n"
        )
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=(stdout, ""))

        result = controller.get_notifications()

        assert result[0] == {"package": "com.android.mms", "title": "", "text": ""}
        assert result[1] == {
            "package": "com.example.app",
            "title": "完整标题",
            "text": "完整正文",
        }
