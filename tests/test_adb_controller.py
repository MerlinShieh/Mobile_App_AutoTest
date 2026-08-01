"""ADB 控制器模块测试。

测试 ADBController 的 shell 命令校验与正常执行。
"""

import pytest

from mobile_automation.device.adb_controller import ADBController


class TestADBController:
    """测试 ADBController 的 shell 命令安全校验。"""

    def test_shell_allows_normal_command(self, mocker):
        """验证合法命令（input/settings）正常放行并执行。"""
        mock_run = mocker.patch("mobile_automation.device.adb_controller.subprocess.run")
        mock_result = mocker.MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        controller = ADBController("test-serial")
        stdout, stderr = controller.shell("input keyevent 26")

        assert stdout == ""
        assert stderr == ""
        assert mock_run.call_count == 1

    def test_shell_rejects_empty_command(self):
        """验证空命令被拒绝并抛出 ValueError。"""
        controller = ADBController("test-serial")
        with pytest.raises(ValueError, match="不能为空"):
            controller.shell("")

    def test_shell_rejects_injection_semicolon(self):
        """验证含分号注入的命令被拒绝。"""
        controller = ADBController("test-serial")
        with pytest.raises(ValueError, match="可疑字符"):
            controller.shell("input keyevent 26; rm -rf /data")

    def test_shell_rejects_injection_dollar(self):
        """验证含 $() 注入的命令被拒绝。"""
        controller = ADBController("test-serial")
        with pytest.raises(ValueError, match="可疑字符"):
            controller.shell("settings get global `id`")

    def test_shell_rejects_injection_backtick(self):
        """验证含反引号注入的命令被拒绝。"""
        controller = ADBController("test-serial")
        with pytest.raises(ValueError, match="可疑字符"):
            controller.shell("echo `whoami`")

    def test_shell_rejects_injection_rm_keyword(self):
        """验证含危险命令关键字（rm）的命令被拒绝。"""
        controller = ADBController("test-serial")
        with pytest.raises(ValueError, match="可疑字符"):
            controller.shell("input keyevent 26 && rm -f /sdcard/x")

    def test_shell_rejects_newline_injection(self):
        """验证含换行注入的命令被拒绝。"""
        controller = ADBController("test-serial")
        with pytest.raises(ValueError, match="可疑字符"):
            controller.shell("settings put system user_rotation 0\nreboot")

    def test_set_rotation_allows_valid_values(self, mocker):
        """验证 set_rotation 合法值正常执行。"""
        mock_run = mocker.patch("mobile_automation.device.adb_controller.subprocess.run")
        mock_result = mocker.MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        controller = ADBController("test-serial")
        controller.set_rotation(1)

        assert mock_run.call_count == 1
