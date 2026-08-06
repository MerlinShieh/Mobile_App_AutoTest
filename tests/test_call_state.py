"""通话状态检测（get_call_state）单元测试。

测试 ADBController.get_call_state 的 dumpsys telephony.registry 输出解析、
失败容错与 serial 注入防御。通过 mock shell() 返回模拟输出，不依赖真机。
"""

import pytest

from mobile_automation.device.adb_controller import ADBController


# 典型 dumpsys telephony.registry 输出（来电场景）
RINGING_OUTPUT = """\
TelephonyRegistry dump:
  mPhoneCount=2
  mCallState=1
  mCallIncomingNumber=+8613800138000
  mCallIncomingNumberSlots=[null]
  mServiceState=[0 0 0 ...]
"""


class TestGetCallState:
    """测试 ADBController.get_call_state 的解析与校验。"""

    def test_parse_ringing_output(self, mocker):
        """来电场景：mCallState=1 解析为 ringing 并提取来电号码。"""
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=(RINGING_OUTPUT, ""))

        result = controller.get_call_state()

        assert result == {
            "state": "ringing",
            "state_code": 1,
            "incoming_number": "+8613800138000",
        }

    def test_parse_idle_output(self, mocker):
        """空闲场景：mCallState=0 解析为 idle，号码为空字符串。"""
        stdout = (
            "TelephonyRegistry dump:\n"
            "  mPhoneCount=1\n"
            "  mCallState=0\n"
            "  mCallIncomingNumber=\n"
        )
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=(stdout, ""))

        result = controller.get_call_state()

        assert result == {
            "state": "idle",
            "state_code": 0,
            "incoming_number": "",
        }

    def test_parse_offhook_output(self, mocker):
        """通话中场景：mCallState=2 解析为 offhook。"""
        stdout = (
            "TelephonyRegistry dump:\n"
            "  mCallState=2\n"
            "  mCallIncomingNumber=\n"
        )
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=(stdout, ""))

        result = controller.get_call_state()

        assert result["state"] == "offhook"
        assert result["state_code"] == 2
        assert result["incoming_number"] == ""

    def test_unknown_state_code_maps_unknown(self, mocker):
        """解析到 0/1/2 之外的数值时 state 为 unknown，保留原始 state_code。"""
        stdout = "  mCallState=9\n  mCallIncomingNumber=\n"
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=(stdout, ""))

        result = controller.get_call_state()

        assert result["state"] == "unknown"
        assert result["state_code"] == 9

    def test_missing_call_state_returns_unknown(self, mocker):
        """输出中无 mCallState 字段时视为 unknown/-1。"""
        stdout = (
            "TelephonyRegistry dump:\n"
            "  mPhoneCount=2\n"
            "  mServiceState=[0 0 0 ...]\n"
        )
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=(stdout, ""))

        result = controller.get_call_state()

        assert result == {
            "state": "unknown",
            "state_code": -1,
            "incoming_number": "",
        }

    def test_first_call_state_value_used(self, mocker):
        """mCallState 出现在输出多处时取第一个有效值。"""
        stdout = (
            "  mCallState=0\n"
            "  mCallIncomingNumber=\n"
            "  mCallState=1\n"
            "  mCallIncomingNumber=+8613800138000\n"
        )
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=(stdout, ""))

        result = controller.get_call_state()

        assert result == {
            "state": "idle",
            "state_code": 0,
            "incoming_number": "",
        }

    def test_shell_failure_returns_unknown(self, mocker):
        """shell 命令失败（返回 False, stderr）时返回 unknown/-1，不抛异常。"""
        controller = ADBController("test-serial")
        mocker.patch.object(
            controller, "shell", return_value=(False, "error: no devices/emulators found")
        )

        result = controller.get_call_state()

        assert result == {
            "state": "unknown",
            "state_code": -1,
            "incoming_number": "",
        }

    def test_shell_stderr_returns_unknown(self, mocker):
        """shell 返回 stderr 非空（如无权限）时视为命令失败，返回 unknown/-1。"""
        controller = ADBController("test-serial")
        mocker.patch.object(
            controller, "shell", return_value=(RINGING_OUTPUT, "Security exception: Permission Denial")
        )

        result = controller.get_call_state()

        assert result["state"] == "unknown"
        assert result["state_code"] == -1
        assert result["incoming_number"] == ""

    def test_shell_empty_output_returns_unknown(self, mocker):
        """shell 返回空 stdout 时视为命令失败，返回 unknown/-1。"""
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", return_value=("", ""))

        result = controller.get_call_state()

        assert result == {
            "state": "unknown",
            "state_code": -1,
            "incoming_number": "",
        }

    def test_shell_raises_returns_unknown(self, mocker):
        """shell 命令抛异常时返回 unknown/-1，不向上传播。"""
        controller = ADBController("test-serial")
        mocker.patch.object(controller, "shell", side_effect=RuntimeError("adb 崩溃"))

        result = controller.get_call_state()

        assert result == {
            "state": "unknown",
            "state_code": -1,
            "incoming_number": "",
        }

    def test_injection_serial_rejected(self):
        """serial 含注入字符时被拒绝。"""
        controller = ADBController("test-serial;rm -rf /")

        with pytest.raises(ValueError, match="可疑字符"):
            controller.get_call_state()

    def test_command_shape(self, mocker):
        """读取命令为 dumpsys telephony.registry。"""
        controller = ADBController("test-serial")
        mock_shell = mocker.patch.object(controller, "shell", return_value=("", ""))

        controller.get_call_state()

        assert mock_shell.call_args[0][0] == "dumpsys telephony.registry"
