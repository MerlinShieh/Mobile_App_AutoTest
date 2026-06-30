"""
点击动作执行器 —— 处理 CLICK / DOUBLE_CLICK / LONG_CLICK 三类点击操作。

通过 DeviceManager 获取 U2Controller 调用 uiautomator2 的点击接口。
定位优先级：ui_element（resource-id / text）> (x, y) 坐标。
所有异常均捕获并记录日志，不向外传播。
"""

from typing import Optional

from ..device.device_manager import DeviceManager
from ..logger import get_logger
from ..models.action import Action
from ..models.enums import ActionType

logger = get_logger(__name__)


class ClickExecutor:
    """
    点击动作执行器。

    支持单击、双击、长按三种点击类型。通过 U2Controller 完成操作。

    参数
    ----------
    device_manager : DeviceManager
        设备管理器实例。
    """

    def __init__(self, device_manager: DeviceManager) -> None:
        """
        初始化 ClickExecutor。

        参数
        ----------
        device_manager : DeviceManager
            设备管理器实例。
        """
        self._dm: DeviceManager = device_manager
        logger.debug("ClickExecutor 初始化完成")

    def execute(self, action: Action) -> bool:
        """
        执行点击操作。

        根据 action_type 分发到单击 / 双击 / 长按逻辑。
        定位顺序：ui_element > (x, y) 坐标。

        参数
        ----------
        action : Action
            点击操作指令，需包含 element_id 或 (x, y) 坐标。

        返回
        -------
        bool
            点击是否成功。
        """
        try:
            u2 = self._dm.get_u2()
            x, y = self._resolve_coordinates(action)

            if x is None or y is None:
                logger.error("ClickExecutor 无法解析坐标: element_id=%s", action.params.element_id)
                return False

            if action.action_type == ActionType.DOUBLE_CLICK:
                return self._double_click(u2, x, y)
            elif action.action_type == ActionType.LONG_CLICK:
                return self._long_click(u2, x, y)
            else:
                return self._single_click(u2, x, y, action)

        except Exception as exc:
            logger.error("点击执行异常: type=%s, error=%s", action.action_type.value, exc)
            return False

    def _resolve_coordinates(self, action: Action) -> tuple[Optional[int], Optional[int]]:
        """
        从 Action 参数中解析点击坐标。

        优先使用 ui_element（resource-id），其次使用 (x, y) 坐标。

        参数
        ----------
        action : Action
            操作指令。

        返回
        -------
        tuple[Optional[int], Optional[int]]
            解析出的 (x, y) 坐标，无法解析时返回 (None, None)。
        """
        if action.params.x is not None and action.params.y is not None:
            return action.params.x, action.params.y

        if action.params.element_id:
            logger.debug("ClickExecutor 需要 StepRunner 解析 element_id=%s", action.params.element_id)

        return action.params.x, action.params.y

    def _single_click(self, u2, x: int, y: int, action: Action) -> bool:
        """
        执行单次点击。

        优先使用 ui_element 的 resource-id 或 text 定位。
        若失败则回退到坐标点击。

        参数
        ----------
        u2 : U2Controller
            U2Controller 实例。
        x : int
            点击 X 坐标。
        y : int
            点击 Y 坐标。
        action : Action
            操作指令。

        返回
        -------
        bool
            点击是否成功。
        """
        try:
            if action.params.ui_element:
                clicked: bool = u2.click_by_text(action.params.ui_element, exact=False)
                if clicked:
                    logger.debug("通过 ui_element(%s) 单击成功", action.params.ui_element)
                    return True

            u2.click(x, y)
            logger.debug("坐标单击成功: (%d, %d)", x, y)
            return True
        except Exception as exc:
            logger.error("单击失败: (%d, %d), error=%s", x, y, exc)
            return False

    def _double_click(self, u2, x: int, y: int) -> bool:
        """
        执行双击操作。

        通过连续两次单击模拟双击行为。

        参数
        ----------
        u2 : U2Controller
            U2Controller 实例。
        x : int
            点击 X 坐标。
        y : int
            点击 Y 坐标。

        返回
        -------
        bool
            双击是否成功。
        """
        try:
            u2.click(x, y)
            u2.click(x, y)
            logger.debug("坐标双击成功: (%d, %d)", x, y)
            return True
        except Exception as exc:
            logger.error("双击失败: (%d, %d), error=%s", x, y, exc)
            return False

    def _long_click(self, u2, x: int, y: int) -> bool:
        """
        执行长按操作。

        通过 uiautomator2 的长按接口实现。

        参数
        ----------
        u2 : U2Controller
            U2Controller 实例。
        x : int
            长按 X 坐标。
        y : int
            长按 Y 坐标。

        返回
        -------
        bool
            长按是否成功。
        """
        try:
            u2._device.long_click(x, y)
            logger.debug("坐标长按成功: (%d, %d)", x, y)
            return True
        except Exception as exc:
            logger.error("长按失败: (%d, %d), error=%s", x, y, exc)
            return False
