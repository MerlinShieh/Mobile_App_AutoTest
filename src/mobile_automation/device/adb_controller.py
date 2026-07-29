"""
ADB 控制器封装模块。

提供对 Android Debug Bridge 的命令行封装，作为 uiautomator2
不可用时的 fallback 方案。支持截图、shell 命令、重连等基础操作。
"""

import subprocess
import time
from typing import Optional

from ..config import settings
from ..logger import get_logger

logger = get_logger(__name__)


class ADBController:
    """
    ADB 控制器（uiautomator2 的 fallback 方案）。

    通过调用 adb 命令行工具与 Android 设备交互。当 uiautomator2
    会话异常断开或不可用时，使用此控制器执行基础设备操作。

    参数
    ----------
    serial : str
        目标设备的序列号。
    max_retries : int
        ADB 命令执行失败时的最大重试次数，默认 3。
    """

    def __init__(self, serial: str, max_retries: int = 3) -> None:
        self.serial: str = serial
        self.max_retries: int = max_retries
        logger.debug("ADBController 初始化，设备: %s", serial)

    def _adb_cmd(self, args: list[str]) -> list[str]:
        """
        构建完整的 adb 命令参数列表。

        参数
        ----------
        args : list[str]
            附加的 adb 子命令与参数列表。

        返回
        -------
        list[str]
            完整的 adb 命令参数，形如 [adb_path, "-s", serial, ...]。
        """
        return [settings.device.adb_path, "-s", self.serial] + args

    def shell(self, command: str, timeout: int = 30) -> tuple[str, str]:
        """
        在设备上执行 ADB shell 命令。

        参数
        ----------
        command : str
            要执行的 shell 命令字符串。
        timeout : int
            命令执行超时（秒），默认 30。

        返回
        -------
        tuple[str, str]
            (标准输出, 标准错误) 的文本内容。
        """
        cmd = self._adb_cmd(["shell", command])
        logger.debug("执行 ADB shell: %s", " ".join(cmd))
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if result.returncode != 0:
                logger.warning("ADB shell 返回非零: %s, stderr: %s", command, result.stderr.strip())
            return result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            logger.error("ADB shell 超时: %s", command)
            raise
        except Exception as exc:
            logger.error("ADB shell 执行异常: %s", exc)
            raise

    def screenshot(self, timeout: int = 30) -> bytes:
        """
        通过 ADB screencap 截取设备屏幕。

        返回
        -------
        bytes
            PNG 格式的原始图片字节数据。
        """
        cmd = self._adb_cmd(["exec-out", "screencap", "-p"])
        logger.debug("执行 ADB 截图")
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=timeout)
            if result.returncode != 0:
                logger.error("ADB 截图失败，returncode: %d", result.returncode)
                raise RuntimeError(f"ADB 截图失败，returncode: {result.returncode}")
            logger.debug("ADB 截图成功，大小: %d 字节", len(result.stdout))
            return result.stdout
        except subprocess.TimeoutExpired:
            logger.error("ADB 截图超时")
            raise
        except Exception as exc:
            logger.error("ADB 截图异常: %s", exc)
            raise

    def reconnect(self) -> bool:
        """
        尝试重新连接设备。

        先尝试 adb reconnect 命令；如果失败则重启 adb server。
        每次尝试后等待 2 秒让设备重新上线。

        返回
        -------
        bool
            True 表示重连操作已触发（不保证设备已完全就绪）。
        """
        logger.info("尝试重连设备: %s", self.serial)

        # 尝试 adb reconnect
        try:
            result = subprocess.run(
                self._adb_cmd(["reconnect"]),
                capture_output=True, timeout=10,
            )
            if result.returncode == 0:
                logger.info("adb reconnect 成功")
                time.sleep(2)
                return True
            else:
                logger.warning("adb reconnect 返回非零: %s", result.stderr.strip())
        except Exception as exc:
            logger.warning("adb reconnect 异常: %s", exc)

        # fallback: 重启 adb server
        try:
            logger.info("尝试重启 ADB server")
            subprocess.run(
                [settings.device.adb_path, "kill-server"],
                capture_output=True, timeout=10,
            )
            time.sleep(1)
            subprocess.run(
                [settings.device.adb_path, "start-server"],
                capture_output=True, timeout=10,
            )
            time.sleep(2)
            logger.info("ADB server 重启完成")
            return True
        except Exception as exc:
            logger.error("ADB server 重启失败: %s", exc)
            return False

    def lock_screen(self) -> None:
        """
        锁定/熄屏设备（toggle 操作）。

        通过 ADB 发送 KeyEvent 26（电源键）切换屏幕锁定状态。
        此操作为 toggle 性质：若屏幕当前亮起则锁定；若已锁定则可能
        唤醒屏幕。调用方应确保在屏幕亮起时调用以获得锁定效果。
        """
        self.shell("input keyevent 26")
        logger.info("设备已执行熄屏/电源键操作")

    def open_notifications(self) -> None:
        """
        展开系统通知栏。

        通过 ADB statusbar 命令展开通知面板。部分定制 ROM 可能
        不支持此命令，此时可考虑通过滑动屏幕顶部下拉替代。
        """
        self.shell("cmd statusbar expand-notifications")
        logger.info("通知栏已展开")

    def set_rotation(self, rotation: int = 0) -> None:
        """
        设置屏幕旋转方向。

        通过 ADB 修改 system user_rotation 设置项。
        修改立即生效，但部分应用可能锁定方向不响应。

        参数
        ----------
        rotation : int
            目标旋转值：
            - 0 = 竖屏（portrait）
            - 1 = 横屏（landscape）
            - 2 = 反向竖屏（reverse_portrait）
            - 3 = 反向横屏（reverse_landscape）
        """
        if rotation not in (0, 1, 2, 3):
            logger.warning("无效的旋转值: %d，使用 0（竖屏）代替", rotation)
            rotation = 0
        self.shell(f"settings put system user_rotation {rotation}")
        logger.info("屏幕旋转已设置为: %d", rotation)

    def volume_up(self) -> None:
        """
        调高媒体音量。

        通过 ADB 发送 KeyEvent 24（音量+键）。
        每次调用增加一级音量。
        """
        self.shell("input keyevent 24")
        logger.info("音量 +1")

    def volume_down(self) -> None:
        """
        调低媒体音量。

        通过 ADB 发送 KeyEvent 25（音量-键）。
        每次调用减少一级音量。
        """
        self.shell("input keyevent 25")
        logger.info("音量 -1")

    def wait_for_device(self, timeout_ms: int = 30000) -> bool:
        """
        等待设备处于可用的在线状态。

        轮询 adb get-state 命令，直到设备状态变为 "device"。

        参数
        ----------
        timeout_ms : int
            最大等待时间（毫秒），默认 30000。

        返回
        -------
        bool
            True 表示设备已在超时前就绪，False 表示超时。
        """
        deadline = time.time() + timeout_ms / 1000.0
        logger.info("等待设备就绪: %s，超时 %d ms", self.serial, timeout_ms)

        while time.time() < deadline:
            try:
                result = subprocess.run(
                    self._adb_cmd(["get-state"]),
                    capture_output=True, text=True, timeout=5,
                )
                state = result.stdout.strip()
                if state == "device":
                    logger.info("设备已就绪: %s", self.serial)
                    return True
                logger.debug("设备状态: %s", state)
            except Exception as exc:
                logger.debug("等待设备状态时出错: %s", exc)
            time.sleep(1)

        logger.warning("等待设备就绪超时: %s", self.serial)
        return False
