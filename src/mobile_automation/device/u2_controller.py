"""
uiautomator2 控制器封装模块。

提供对 uiautomator2 设备对象的轻量封装，统一截图、UI dump、
点击、输入、滑动、系统按键和应用管理等操作接口。
"""

from typing import Optional

import uiautomator2 as u2

from ..logger import get_logger

logger = get_logger(__name__)


class U2Controller:
    """
    uiautomator2 控制器封装。

    对 uiautomator2 的设备对象做一层轻量包装，使得调用方无需直接
    依赖 u2 库的 API 细节。所有操作均委托给内部的 u2.Device 实例。

    参数
    ----------
    serial : str
        目标设备的序列号，传给 u2.connect() 用于建立连接。
    """

    def __init__(self, serial: str) -> None:
        self._serial: str = serial
        self._device: u2.Device = u2.connect(serial)
        info = self._device.info
        if info is None:
            raise RuntimeError(f"uiautomator2 连接失败，设备序列号: {serial}")
        logger.info("U2Controller 初始化成功，设备: %s", serial)

    def health_check(self) -> bool:
        """
        检查 uiautomator2 会话是否仍然存活。

        返回
        -------
        bool
            True 表示会话正常，False 表示会话已断开。
        """
        try:
            info = self._device.info
            alive = info is not None
            if alive:
                logger.debug("U2Controller 健康检查通过，设备: %s", self._serial)
            else:
                logger.warning("U2Controller 健康检查失败，设备: %s", self._serial)
            return alive
        except Exception as exc:
            logger.error("U2Controller 健康检查异常: %s", exc)
            return False

    def window_size(self) -> tuple[int, int]:
        """
        获取屏幕宽高。

        返回
        -------
        tuple[int, int]
            (宽度, 高度)，单位像素。
        """
        try:
            w, h = self._device.window_size()
            logger.debug("屏幕尺寸: %dx%d", w, h)
            return w, h
        except Exception as exc:
            logger.error("获取屏幕尺寸失败: %s", exc)
            return 1080, 1920

    def get_device_info(self) -> dict:
        """
        获取设备信息字典。

        包含 displayWidth、displayHeight、productName、sdkInt 等字段。

        返回
        -------
        dict
            设备属性字典，连接异常时返回空字典。
        """
        try:
            info = self._device.info
            return info or {}
        except Exception as exc:
            logger.error("获取设备信息失败: %s", exc)
            return {}

    def screenshot(self, quality: int = 85) -> bytes:
        """
        截取当前设备屏幕。

        参数
        ----------
        quality : int
            JPEG 压缩质量，取值范围 1~100，默认 85。

        返回
        -------
        bytes
            PNG 格式的原始图片字节数据，由调用方负责格式转换。
        """
        try:
            data: bytes = self._device.screenshot()
            logger.debug("u2 截图成功，大小: %d 字节", len(data))
            return data
        except Exception as exc:
            logger.error("uiautomator2 截图失败: %s", exc)
            raise

    def dump_ui(self) -> str:
        """
        获取当前界面的 UI 层次结构 XML 字符串。

        返回
        -------
        str
            包含所有 UI 节点信息的 XML 字符串。
        """
        try:
            xml_str: str = self._device.dump_hierarchy()
            logger.debug("UI dump 成功，XML 长度: %d 字符", len(xml_str))
            return xml_str
        except Exception as exc:
            logger.error("uiautomator2 UI dump 失败: %s", exc)
            raise

    def click(self, x: int, y: int) -> None:
        """
        在屏幕指定坐标处执行点击。

        参数
        ----------
        x : int
            点击位置的 X 坐标（像素）。
        y : int
            点击位置的 Y 坐标（像素）。
        """
        try:
            self._device.click(x, y)
            logger.debug("点击坐标 (%d, %d)", x, y)
        except Exception as exc:
            logger.error("点击坐标 (%d, %d) 失败: %s", x, y, exc)
            raise

    def click_by_rid(self, resource_id: str) -> bool:
        """
        根据 resource-id 点击元素。

        参数
        ----------
        resource_id : str
            目标元素的 resource-id，如 "com.example:id/btn_ok"。

        返回
        -------
        bool
            是否成功点击到目标元素。
        """
        try:
            clicked: bool = self._device(resourceId=resource_id).click_exists(timeout=3)
            if clicked:
                logger.debug("通过 resource-id 点击成功: %s", resource_id)
            else:
                logger.warning("通过 resource-id 未找到元素: %s", resource_id)
            return clicked
        except Exception as exc:
            logger.error("通过 resource-id 点击异常: %s", exc)
            return False

    def click_by_text(self, text: str, exact: bool = True) -> bool:
        """
        根据文本内容点击元素。

        参数
        ----------
        text : str
            目标元素的显示文本。
        exact : bool
            True 表示精确匹配，False 表示包含匹配。

        返回
        -------
        bool
            是否成功点击到目标元素。
        """
        try:
            if exact:
                clicked = self._device(text=text).click_exists(timeout=3)
            else:
                clicked = self._device(textContains=text).click_exists(timeout=3)
            if clicked:
                logger.debug("通过文本点击成功: %s (精确=%s)", text, exact)
            else:
                logger.warning("通过文本未找到元素: %s (精确=%s)", text, exact)
            return clicked
        except Exception as exc:
            logger.error("通过文本点击异常: %s", exc)
            return False

    def click_by_multiple_selectors(
        self,
        resource_id: str = "",
        text: str = "",
        class_name: str = "",
        instance: int = 0,
    ) -> bool:
        """
        通过多个选择器组合定位并点击元素。

        参数
        ----------
        resource_id : str
            元素 resource-id，可留空。
        text : str
            元素文本，可留空。
        class_name : str
            元素类名，可留空。
        instance : int
            命中多个元素时的实例索引，默认 0。

        返回
        -------
        bool
            是否成功点击到目标元素。
        """
        try:
            selector = self._device
            if resource_id:
                selector = selector(resourceId=resource_id)
            if text:
                selector = selector(text=text)
            if class_name:
                selector = selector(className=class_name)
            clicked = selector[instance].click_exists(timeout=3)
            if clicked:
                logger.debug("组合选择器点击成功: rid=%s text=%s cls=%s", resource_id, text, class_name)
            else:
                logger.warning("组合选择器未找到元素: rid=%s text=%s cls=%s", resource_id, text, class_name)
            return clicked
        except Exception as exc:
            logger.error("组合选择器点击异常: %s", exc)
            return False

    def send_text(self, text: str) -> None:
        """
        向当前聚焦的输入框发送文本。

        参数
        ----------
        text : str
            要输入的文本内容。
        """
        try:
            self._device.send_keys(text)
            logger.debug("文本输入成功，长度: %d 字符", len(text))
        except Exception as exc:
            logger.error("文本输入失败: %s", exc)
            raise

    def clear_text(self) -> None:
        """
        清空当前聚焦输入框的文本内容。
        """
        try:
            self._device.clear_text()
            logger.debug("清空文本成功")
        except Exception as exc:
            logger.error("清空文本失败: %s", exc)
            raise

    def swipe(self, fx: int, fy: int, tx: int, ty: int, steps: int = 100) -> None:
        """
        从起点到终点执行滑动操作。

        参数
        ----------
        fx : int
            起点 X 坐标。
        fy : int
            起点 Y 坐标。
        tx : int
            终点 X 坐标。
        ty : int
            终点 Y 坐标。
        steps : int
            滑动步数，值越小滑动越快（产生 fling 效果），默认 100（约 0.5s 的慢速拖拽）。
            滚动操作建议 20~30 步以实现快速 fling。
        """
        try:
            self._device.swipe(fx, fy, tx, ty, steps=steps)
            logger.debug("滑动 (%d,%d) -> (%d,%d), steps=%d", fx, fy, tx, ty, steps)
        except Exception as exc:
            logger.error("滑动失败: %s", exc)
            raise

    def scroll(self, direction: str = "forward") -> None:
        """
        执行滚动操作。

        通过坐标滑动模拟滚动，direction 支持 "up" / "down" / "left" / "right"。
          - "up"（向上滚动）= 手指从屏幕中心向上推 → 露出列表底部内容
          - "down"（向下滚动）= 手指从屏幕中心向下拉 → 露出列表顶部内容

        参数
        ----------
        direction : str
            滚动方向。
        """
        _direction_map: dict[str, int] = {
            "up": -1,    # 手指向上推，露出底部
            "down": 1,   # 手指向下拉，露出顶部
            "forward": 1,
            "backward": -1,
        }
        sign = _direction_map.get(direction, 0)
        try:
            w, h = self.window_size()
            cx, cy = w // 2, h // 2
            offset = int(h * 0.5)
            ty = cy + sign * offset
            self.swipe(cx, cy, cx, ty, steps=55)
            logger.debug("滚动操作成功: direction=%s, (中心) -> (%d,%d)", direction, cx, ty)
        except Exception as exc:
            logger.error("滚动操作失败: %s", exc)
            raise

    def press_back(self) -> None:
        """按下系统返回键。"""
        try:
            self._device.press("back")
            logger.debug("按下返回键")
        except Exception as exc:
            logger.error("按下返回键失败: %s", exc)
            raise

    def press_home(self) -> None:
        """按下系统 Home 键，回到桌面。"""
        try:
            self._device.press("home")
            logger.debug("按下 Home 键")
        except Exception as exc:
            logger.error("按下 Home 键失败: %s", exc)
            raise

    def press_recent(self) -> None:
        """按下最近任务键，打开多任务切换界面。"""
        try:
            self._device.press("recent")
            logger.debug("按下最近任务键")
        except Exception as exc:
            logger.error("按下最近任务键失败: %s", exc)
            raise

    def app_start(self, package_name: str) -> None:
        """
        启动指定应用。

        参数
        ----------
        package_name : str
            目标应用的包名。
        """
        try:
            self._device.app_start(package_name)
            logger.info("启动应用: %s", package_name)
        except Exception as exc:
            logger.error("启动应用失败: %s", exc)
            raise

    def app_stop(self, package_name: str) -> None:
        """
        停止指定应用。

        参数
        ----------
        package_name : str
            目标应用的包名。
        """
        try:
            self._device.app_stop(package_name)
            logger.info("停止应用: %s", package_name)
        except Exception as exc:
            logger.error("停止应用失败: %s", exc)
            raise

    def wait_stable(self, timeout_ms: int = 5000) -> bool:
        """
        等待页面 UI 树稳定（连续两次 dump 内容一致）。

        参数
        ----------
        timeout_ms : int
            最大等待时间（毫秒），默认 5000。

        返回
        -------
        bool
            True 表示在超时前页面已稳定，False 表示超时。
        """
        import time

        deadline = time.time() + timeout_ms / 1000.0
        prev_dump: Optional[str] = None
        sleep_interval = 0.5

        while time.time() < deadline:
            try:
                current_dump = self.dump_ui()
                if prev_dump is not None and current_dump == prev_dump:
                    logger.debug("页面已稳定，耗时: %.1f 秒", time.time() - (deadline - timeout_ms / 1000.0))
                    return True
                prev_dump = current_dump
            except Exception as exc:
                logger.warning("等待稳定期间 UI dump 失败: %s", exc)
            time.sleep(sleep_interval)

        logger.warning("等待页面稳定超时 (%d ms)", timeout_ms)
        return False
