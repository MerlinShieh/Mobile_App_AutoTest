"""
设备管理器模块 —— DeviceManager 单例实现。

管理 Android 设备的连接生命周期，为上层的感知层和执行层提供
统一的设备访问入口。支持自动选择设备、健康检查、自动重连、
uiautomator2 优先 + ADB fallback 的双通道连接策略。
"""

import re
import subprocess
import time
from dataclasses import dataclass, field
from typing import Optional

from ..config import settings
from ..exception import DeviceConnectionError
from ..logger import get_logger
from .adb_controller import ADBController
from .u2_controller import U2Controller

logger = get_logger(__name__)


@dataclass
class DeviceInfo:
    """
    设备信息数据类。

    描述一台 Android 设备的基本信息，由 DeviceManager.list_devices()
    返回。

    参数
    ----------
    serial : str
        设备序列号，唯一标识一台设备。
    model : str
        设备型号名，如 "Pixel_7"、"SM-S9280"。
    screen_width : int
        屏幕宽度（像素），0 表示尚未获取。
    screen_height : int
        屏幕高度（像素），0 表示尚未获取。
    online : bool
        设备是否在线可连接。
    """
    serial: str = ""
    model: str = ""
    screen_width: int = 0
    screen_height: int = 0
    online: bool = False


class DeviceManager:
    """
    设备管理器（单例模式）。

    管理设备连接生命周期，支持：
    - 列出已连接的设备列表
    - 按序列号连接设备（自动选择首个在线设备）
    - 断开连接并释放资源
    - 健康检查与自动重连（含指数退避）
    - 获取 uiautomator2 / ADB 控制器实例
    - 缓存屏幕尺寸信息

    使用示例
    --------
    >>> dm = DeviceManager()
    >>> dm.connect("emulator-5554")
    True
    >>> u2 = dm.get_u2()
    >>> u2.click(100, 200)
    >>> adb = dm.get_adb()
    >>> stdout, _ = adb.shell("wm size")
    """

    _instance: Optional["DeviceManager"] = None
    """单例全局实例"""

    def __new__(cls) -> "DeviceManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized: bool = True
        self._serial: str = ""
        """当前连接的设备序列号"""
        self._u2: Optional[U2Controller] = None
        """uiautomator2 控制器实例"""
        self._adb: Optional[ADBController] = None
        """ADB 控制器实例"""
        self._screen_size: tuple[int, int] = (1080, 2400)
        """屏幕尺寸 (宽, 高)，默认可通过 update_screen_size 刷新"""
        logger.info("DeviceManager 单例初始化完成")

    def list_devices(self) -> list[DeviceInfo]:
        """
        通过 adb devices -l 列出所有已连接的设备。

        返回
        -------
        list[DeviceInfo]
            设备信息列表，包含序列号、型号和在线状态。
        """
        devices: list[DeviceInfo] = []
        try:
            result = subprocess.run(
                [settings.device.adb_path, "devices", "-l"],
                capture_output=True, text=True, timeout=10,
            )
            lines = result.stdout.strip().split("\n")
            logger.debug("adb devices 输出: %d 行", len(lines))

            for line in lines[1:]:
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                serial = parts[0]
                online = "device" in line
                model = ""
                for p in parts:
                    if p.startswith("model:"):
                        model = p.split(":")[1] if ":" in p else ""
                devices.append(DeviceInfo(serial=serial, model=model, online=online))

            logger.info("发现 %d 台设备，其中 %d 台在线",
                         len(devices), sum(1 for d in devices if d.online))
            return devices
        except subprocess.TimeoutExpired:
            logger.error("adb devices 命令超时")
            return devices
        except FileNotFoundError:
            logger.error("ADB 可执行文件未找到: %s", settings.device.adb_path)
            return devices
        except Exception as exc:
            logger.error("列出设备失败: %s", exc)
            return devices

    def connect(self, serial: str = "") -> bool:
        """
        连接到指定设备（或自动选择首个在线设备）。

        连接策略：优先初始化 uiautomator2 会话，若失败则仅启用 ADB fallback。
        连接成功后自动获取屏幕尺寸信息。

        参数
        ----------
        serial : str
            目标设备序列号。留空时自动选择首个在线设备。

        返回
        -------
        bool
            True 表示连接成功。

        异常
        ------
        DeviceConnectionError
            未发现任何在线设备时抛出。
        RuntimeError
            ADB 控制器初始化失败时抛出。
        """
        if not serial:
            devices = self.list_devices()
            online = [d for d in devices if d.online]
            if not online:
                raise DeviceConnectionError("未发现在线设备")
            serial = online[0].serial
            logger.info("未指定设备，自动选择: %s", serial)

        logger.info("正在连接设备: %s", serial)

        # 优先初始化 uiautomator2
        u2_success = False
        try:
            self._u2 = U2Controller(serial)
            u2_success = True
            logger.info("uiautomator2 连接成功: %s", serial)
        except Exception as exc:
            self._u2 = None
            logger.warning("uiautomator2 连接失败，启用 ADB fallback: %s", exc)

        # 始终初始化 ADB 控制器
        try:
            self._adb = ADBController(serial, max_retries=settings.device.connect_retries)
        except Exception as exc:
            logger.error("ADB 控制器初始化失败: %s", exc)
            raise RuntimeError(f"ADB 控制器初始化失败: {exc}") from exc

        self._serial = serial
        self._update_screen_size()

        if u2_success:
            logger.info("设备连接完成（u2 + ADB）: %s", serial)
        else:
            logger.warning("设备连接完成（仅 ADB fallback）: %s", serial)
        return True

    def disconnect(self) -> None:
        """
        断开当前设备连接，释放所有控制器资源。

        调用后 get_u2() 和 get_adb() 将抛出异常，直到重新 connect()。
        """
        serial = self._serial
        self._u2 = None
        self._adb = None
        self._serial = ""
        logger.info("设备断开连接: %s", serial)

    def health_check(self) -> bool:
        """
        检查当前设备连接是否健康。

        优先检查 uiautomator2 会话；若异常则自动触发重连流程，
        重连次数由 settings.device.connect_retries 控制。

        返回
        -------
        bool
            True 表示设备连接正常。
        """
        if not self._serial:
            logger.warning("健康检查失败：未连接任何设备")
            return False

        # u2 会话检查
        if self._u2 is not None:
            try:
                if self._u2.health_check():
                    logger.debug("设备健康检查通过: %s", self._serial)
                    return True
            except Exception as exc:
                logger.warning("uiautomator2 健康检查异常: %s", exc)
            self._u2 = None
            logger.info("uiautomator2 会话已失效，准备重连: %s", self._serial)

        # 自动重连
        max_retries = settings.device.connect_retries
        for attempt in range(1, max_retries + 1):
            try:
                logger.info("重连尝试 %d/%d: %s", attempt, max_retries, self._serial)
                self.connect(self._serial)
                if self._u2 is not None:
                    logger.info("重连成功: %s", self._serial)
                    return True
            except Exception as exc:
                logger.warning("重连尝试 %d 失败: %s", attempt, exc)
            if attempt < max_retries:
                time.sleep(2 * attempt)

        logger.error("设备重连失败: %s", self._serial)
        return False

    def get_u2(self) -> U2Controller:
        """
        获取 uiautomator2 控制器实例。

        返回
        -------
        U2Controller
            uiautomator2 控制器。

        异常
        ------
        RuntimeError
            当前未连接或 uiautomator2 未初始化时抛出。
        """
        if self._u2 is None:
            raise RuntimeError("uiautomator2 未连接，请先调用 connect()")
        return self._u2

    def get_adb(self) -> ADBController:
        """
        获取 ADB 控制器实例。

        返回
        -------
        ADBController
            ADB 控制器。

        异常
        ------
        RuntimeError
            当前未连接时抛出。
        """
        if self._adb is None:
            raise RuntimeError("ADB 未连接，请先调用 connect()")
        return self._adb

    def get_screen_size(self) -> tuple[int, int]:
        """
        获取设备屏幕尺寸。

        返回
        -------
        tuple[int, int]
            (屏幕宽度, 屏幕高度)，单位像素。
        """
        return self._screen_size

    def get_serial(self) -> str:
        """
        获取当前连接的设备序列号。

        返回
        -------
        str
            设备序列号，未连接时返回空字符串。
        """
        return self._serial

    def _update_screen_size(self) -> None:
        """
        从设备获取并缓存屏幕尺寸信息。

        优先使用 uiautomator2 的 get_device_info() 获取 displayWidth/displayHeight；
        若不可用则 fallback 到 ADB shell wm size 命令解析。
        """
        if self._u2 is not None:
            try:
                info = self._u2.get_device_info()
                width = info.get("displayWidth", 0)
                height = info.get("displayHeight", 0)
                if width > 0 and height > 0:
                    self._screen_size = (width, height)
                    logger.debug("屏幕尺寸（u2）: %dx%d", width, height)
                    return
            except Exception as exc:
                logger.warning("通过 u2 获取屏幕尺寸失败: %s", exc)

        if self._adb is not None:
            try:
                stdout, _ = self._adb.shell("wm size")
                match = re.search(r"(\d+)x(\d+)", stdout)
                if match:
                    self._screen_size = (int(match.group(1)), int(match.group(2)))
                    logger.debug("屏幕尺寸（ADB）: %dx%d", *self._screen_size)
                    return
            except Exception as exc:
                logger.warning("通过 ADB 获取屏幕尺寸失败: %s", exc)

        logger.warning("无法获取设备屏幕尺寸，使用默认值: %dx%d", *self._screen_size)
