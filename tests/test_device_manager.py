"""设备管理器模块测试。

使用 mock 子进程方式测试 list_devices、connect、disconnect 和 health_check 方法，
避免依赖实际的 ADB 设备和子进程调用。
"""

import subprocess

import pytest

from mobile_automation.device.device_manager import DeviceManager, DeviceInfo
from mobile_automation.exception import DeviceConnectionError


class TestDeviceManager:
    """测试 DeviceManager 的设备管理功能。"""

    def test_list_devices_parses_output(self, mocker):
        """验证 list_devices 正确解析 adb devices -l 的输出。"""
        fake_output = (
            "List of devices attached\n"
            "emulator-5554 device product:sdk_gphone64_x86_64 model:Pixel_7 device:google_sdk_gphone64_x86_64\n"
            "0123456789ABCDEF device product:realme model:RMX3000\n"
        )
        mocker.patch("subprocess.run", return_value=mocker.MagicMock(
            stdout=fake_output, stderr="", returncode=0,
        ))

        dm = DeviceManager()
        devices = dm.list_devices()
        assert len(devices) == 2
        assert devices[0].serial == "emulator-5554"
        assert devices[0].online is True
        assert devices[0].model == "Pixel_7"
        assert devices[1].serial == "0123456789ABCDEF"
        assert devices[1].model == "RMX3000"

    def test_list_devices_offline_device(self, mocker):
        """验证离线设备的 online 状态为 False。"""
        fake_output = (
            "List of devices attached\n"
            "emulator-5554 offline\n"
        )
        mocker.patch("subprocess.run", return_value=mocker.MagicMock(
            stdout=fake_output, stderr="", returncode=0,
        ))

        dm = DeviceManager()
        devices = dm.list_devices()
        assert len(devices) == 1
        assert devices[0].online is False

    def test_list_devices_timeout(self, mocker):
        """验证 adb 超时后返回空列表。"""
        mocker.patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="adb", timeout=10))

        dm = DeviceManager()
        devices = dm.list_devices()
        assert devices == []

    def test_list_devices_file_not_found(self, mocker):
        """验证 adb 可执行文件未找到时返回空列表。"""
        mocker.patch("subprocess.run", side_effect=FileNotFoundError())

        dm = DeviceManager()
        devices = dm.list_devices()
        assert devices == []

    def test_connect_auto_select_first_online(self, mocker):
        """验证 connect 无参数时自动选择首个在线设备。"""
        mocker.patch.object(DeviceManager, "list_devices", return_value=[
            DeviceInfo(serial="emulator-5554", model="Pixel_7", online=True),
        ])
        mocker.patch("mobile_automation.device.u2_controller.U2Controller")
        mocker.patch("mobile_automation.device.adb_controller.ADBController")

        dm = DeviceManager()
        result = dm.connect()
        assert result is True
        assert dm.get_serial() == "emulator-5554"

    def test_connect_no_online_devices_raises(self, mocker):
        """验证无在线设备时抛出异常。"""
        mocker.patch.object(DeviceManager, "list_devices", return_value=[])

        dm = DeviceManager()
        with pytest.raises(DeviceConnectionError, match="未发现在线设备"):
            dm.connect()

    def test_connect_with_serial(self, mocker):
        """验证指定序列号连接设备。"""
        mocker.patch("mobile_automation.device.u2_controller.U2Controller")
        mocker.patch("mobile_automation.device.adb_controller.ADBController")

        dm = DeviceManager()
        result = dm.connect(serial="test-device-001")
        assert result is True
        assert dm.get_serial() == "test-device-001"

    def test_disconnect(self, mocker):
        """验证 disconnect 重置连接状态。"""
        mocker.patch("mobile_automation.device.u2_controller.U2Controller")
        mocker.patch("mobile_automation.device.adb_controller.ADBController")

        dm = DeviceManager()
        dm.connect(serial="test-device")
        assert dm.get_serial() == "test-device"
        dm.disconnect()
        assert dm.get_serial() == ""
        with pytest.raises(RuntimeError):
            dm.get_u2()
        with pytest.raises(RuntimeError):
            dm.get_adb()

    def test_get_screen_size_default(self):
        """验证未连接时返回默认屏幕尺寸。"""
        dm = DeviceManager()
        assert dm.get_screen_size() == (1080, 2400)

    def test_health_check_not_connected(self):
        """验证未连接时健康检查返回 False。"""
        dm = DeviceManager()
        assert dm.health_check() is False

    def test_health_check_u2_healthy(self, mocker):
        """验证 u2 健康时 health_check 返回 True。"""
        mock_u2 = mocker.MagicMock()
        mock_u2.health_check.return_value = True

        dm = DeviceManager()
        dm._serial = "test-device"
        dm._u2 = mock_u2
        assert dm.health_check() is True

    def test_health_check_reconnect_on_failure(self, mocker):
        """验证 u2 异常后自动重连。"""
        mock_u2 = mocker.MagicMock()
        mock_u2.health_check.side_effect = Exception("u2 error")

        mock_u2_new = mocker.MagicMock()
        mock_u2_new.health_check.return_value = True

        mocker.patch("mobile_automation.device.u2_controller.U2Controller", return_value=mock_u2_new)

        dm = DeviceManager()
        dm._serial = "test-device"
        dm._u2 = mock_u2
        dm._adb = mocker.MagicMock()

        # 让 connect 实际执行时能设置 _u2
        original_connect = DeviceManager.connect
        def patched_connect(self, serial=""):
            self._serial = serial or "test-device"
            self._u2 = mock_u2_new
            self._adb = mocker.MagicMock()
            return True
        mocker.patch.object(DeviceManager, "connect", patched_connect)

        result = dm.health_check()
        assert result is True

    def test_singleton_pattern(self):
        """验证 DeviceManager 是单例。"""
        dm1 = DeviceManager()
        dm2 = DeviceManager()
        assert dm1 is dm2

    def test_device_info_dataclass(self):
        """验证 DeviceInfo 数据类字段默认值。"""
        info = DeviceInfo(serial="test")
        assert info.serial == "test"
        assert info.model == ""
        assert info.screen_width == 0
        assert info.screen_height == 0
        assert info.online is False
