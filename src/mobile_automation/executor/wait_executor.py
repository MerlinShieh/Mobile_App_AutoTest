"""
等待动作执行器 —— 处理 WAIT 操作。

WAIT 操作用于等待页面稳定或等待指定时长。
通过 U2Controller.wait_stable 检测页面是否不再变化来判断稳定状态。
"""

import time

from ..device.device_manager import DeviceManager
from ..logger import get_logger
from ..models.action import Action

logger = get_logger(__name__)


class WaitExecutor:
    """
    等待动作执行器。

    处理 WAIT 操作，等待页面稳定或等待指定时长。
    通过反复检测 UI 树是否变化来判断页面稳定性。

    参数
    ----------
    device_manager : DeviceManager
        设备管理器实例。
    """

    def __init__(self, device_manager: DeviceManager) -> None:
        """
        初始化 WaitExecutor。

        参数
        ----------
        device_manager : DeviceManager
            设备管理器实例。
        """
        self._dm: DeviceManager = device_manager
        logger.debug("WaitExecutor 初始化完成")

    def execute(self, action: Action) -> bool:
        """
        执行等待操作。

        优先使用 duration_ms 作为等待时长。
        若未指定时长，则使用 U2Controller 的 wait_stable 方法检测页面稳定。

        参数
        ----------
        action : Action
            等待操作指令。

        返回
        -------
        bool
            等待是否完成。页面稳定或指定时长耗尽时返回 True，超时返回 False。
        """
        duration_ms: int = action.params.duration_ms

        if duration_ms > 0:
            return self._wait_duration(duration_ms)

        return self._wait_stable()

    def _wait_duration(self, duration_ms: int) -> bool:
        """
        等待指定的时长。

        参数
        ----------
        duration_ms : int
            等待时长（毫秒）。

        返回
        -------
        bool
            始终返回 True。
        """
        seconds: float = duration_ms / 1000.0
        logger.info("WAIT 操作: 等待 %d 毫秒", duration_ms)
        time.sleep(seconds)
        logger.debug("WAIT 操作完成: 已等待 %d 毫秒", duration_ms)
        return True

    def _wait_stable(self) -> bool:
        """
        等待页面稳定。

        通过 U2Controller 的 wait_stable 方法检测页面是否不再变化。
        默认超时时间为 5 秒。

        返回
        -------
        bool
            页面是否在超时前稳定下来。
        """
        try:
            u2 = self._dm.get_u2()
            logger.info("WAIT 操作: 等待页面稳定")
            stable: bool = u2.wait_stable(timeout_ms=5000)
            if stable:
                logger.debug("WAIT 操作: 页面已稳定")
            else:
                logger.warning("WAIT 操作: 页面稳定等待超时")
            return stable
        except Exception as exc:
            logger.error("WAIT 操作异常: %s", exc)
            return False
