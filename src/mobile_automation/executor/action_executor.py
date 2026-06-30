"""
动作分发执行器 —— 解析 Action 指令并分发到对应的子执行器。

ActionExecutor 接收一个完整的 Action 对象，先校验参数合法性，
然后根据 action_type 将执行委托给 ClickExecutor / TypeExecutor /
SwipeExecutor / WaitExecutor。系统级操作（BACK / HOME / OPEN_APP 等）
直接通过 U2Controller 执行。

element_id 优先定位流程：
  1. LLM 输出 element_id（如 "#3"）
  2. StepRunner._resolve_element_id 查询本地索引
  3. 解析出 resource-id 或坐标后填入 Action.params
  4. ActionExecutor 优先使用 ui_element（resource-id）定位
  5. 失败后回退到 (x, y) 坐标点击
"""

from typing import Optional

from ..config import settings
from ..device.device_manager import DeviceManager
from ..logger import get_logger
from ..models.action import Action, ActionParams
from ..models.enums import ActionType
from .click_executor import ClickExecutor
from .swipe_executor import SwipeExecutor
from .type_executor import TypeExecutor
from .wait_executor import WaitExecutor

logger = get_logger(__name__)


class ActionExecutor:
    """
    动作分发执行器。

    根据 Action.action_type 将执行委托给对应的子执行器。
    对于 BACK / HOME / RECENT_APPS / OPEN_APP / CLOSE_APP / TERMINATE
    等系统级操作，直接通过 U2Controller 处理，无需子执行器。

    参数
    ----------
    device_manager : DeviceManager
        设备管理器实例，用于获取 U2Controller 和 ADBController。
    """

    def __init__(self, device_manager: DeviceManager) -> None:
        """
        初始化 ActionExecutor。

        参数
        ----------
        device_manager : DeviceManager
            设备管理器实例。
        """
        self._dm: DeviceManager = device_manager
        self._executors: dict[ActionType, object] = {
            ActionType.CLICK: ClickExecutor(device_manager),
            ActionType.DOUBLE_CLICK: ClickExecutor(device_manager),
            ActionType.LONG_CLICK: ClickExecutor(device_manager),
            ActionType.TYPE: TypeExecutor(device_manager),
            ActionType.CLEAR_TEXT: TypeExecutor(device_manager),
            ActionType.SWIPE: SwipeExecutor(device_manager),
            ActionType.SWIPE_POINT: SwipeExecutor(device_manager),
            ActionType.SCROLL: SwipeExecutor(device_manager),
            ActionType.WAIT: WaitExecutor(device_manager),
        }
        logger.debug("ActionExecutor 初始化完成，已注册 %d 个子执行器", len(self._executors))

    def execute(self, action: Action) -> bool:
        """
        执行一个操作指令。

        先校验参数合法性，再根据 action_type 分发执行。
        对于点击操作，优先使用 ui_element（resource-id / text）定位。

        参数
        ----------
        action : Action
            待执行的操作指令。

        返回
        -------
        bool
            执行是否成功。

        异常
        ------
        ValueError
            参数校验未通过时抛出，包含缺失字段详情。
        """
        missing: list[str] = action.validate()
        if missing:
            logger.error("Action 参数校验失败: %s", missing)
            raise ValueError(f"参数校验失败: {', '.join(missing)}")

        logger.info("执行 Action: type=%s, element_id=%s, reason=%s",
                     action.action_type.value, action.params.element_id, action.reason)

        try:
            if settings.coordinate_tuning.enable_tuning:
                self._apply_tuning(action.params)

            if action.params.ui_element and action.action_type == ActionType.CLICK:
                try:
                    u2 = self._dm.get_u2()
                    if u2.click_by_text(action.params.ui_element, exact=False):
                        logger.info("通过 ui_element(%s) 点击成功", action.params.ui_element)
                        return True
                except Exception as exc:
                    logger.warning("通过 ui_element(%s) 点击失败: %s，回退到坐标", action.params.ui_element, exc)

            executor = self._executors.get(action.action_type)
            if executor is None:
                return self._execute_system_action(action)

            result: bool = executor.execute(action)
            logger.info("Action 执行%s: type=%s", "成功" if result else "失败", action.action_type.value)
            return result

        except Exception as exc:
            logger.error("Action 执行异常: type=%s, error=%s", action.action_type.value, exc)
            raise

    def _execute_system_action(self, action: Action) -> bool:
        """
        执行系统级操作（BACK / HOME / RECENT_APPS / OPEN_APP / CLOSE_APP / TERMINATE / VERIFY）。

        参数
        ----------
        action : Action
            系统操作指令。

        返回
        -------
        bool
            执行是否成功。
        """
        try:
            u2 = self._dm.get_u2()
            system_actions: dict[ActionType, callable] = {
                ActionType.BACK: u2.press_back,
                ActionType.HOME: u2.press_home,
                ActionType.RECENT_APPS: u2.press_recent,
                ActionType.OPEN_APP: lambda: u2.app_start(action.params.package_name or ""),
                ActionType.CLOSE_APP: lambda: u2.app_stop(action.params.package_name or ""),
                ActionType.SCREENSHOT: lambda: self._capture_screenshot(),
                ActionType.TERMINATE: lambda: None,
                ActionType.VERIFY: lambda: None,
            }
            handler = system_actions.get(action.action_type)
            if handler is None:
                logger.warning("未知的系统操作类型: %s", action.action_type)
                return False
            handler()
            logger.info("系统操作执行成功: type=%s", action.action_type.value)
            return True
        except Exception as exc:
            logger.error("系统操作执行失败: type=%s, error=%s", action.action_type.value, exc)
            return False

    @staticmethod
    def _apply_tuning(params: ActionParams) -> None:
        """
        对坐标参数应用微调偏移。

        当 enable_tuning 启用时，对 (x, y) 坐标分别加上配置的偏移量。

        参数
        ----------
        params : ActionParams
            待微调的操作参数，会直接修改其中的 x, y 值。
        """
        if params.x is not None:
            old_x: int = params.x
            params.x += settings.coordinate_tuning.offset_x
            logger.debug("坐标微调 X: %d -> %d (offset=%d)", old_x, params.x, settings.coordinate_tuning.offset_x)
        if params.y is not None:
            old_y: int = params.y
            params.y += settings.coordinate_tuning.offset_y
            logger.debug("坐标微调 Y: %d -> %d (offset=%d)", old_y, params.y, settings.coordinate_tuning.offset_y)

    def _capture_screenshot(self) -> None:
        """
        执行截图操作。通过 ADB 截图并缓存到日志。

        screenshot 动作本身不返回数据，由 StepRunner 执行后的二次感知
        归档操作后截图。此方法仅确保截图动作有实际含义的执行行为。
        """
        try:
            u2 = self._dm.get_u2()
            data = u2.screenshot()
            logger.info("截图执行成功: 大小=%d 字节", len(data))
        except Exception as exc:
            logger.warning("截图执行失败(尝试 ADB): %s", exc)
            try:
                adb = self._dm.get_adb()
                data = adb.screenshot()
                logger.info("ADB 截图执行成功: 大小=%d 字节", len(data))
            except Exception as adb_exc:
                logger.error("截图执行完全失败: %s", adb_exc)
