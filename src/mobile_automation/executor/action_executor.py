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

from typing import Callable, Optional

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

# 系统级查询动作集合：不改变页面，仅读取系统信息（短信/剪贴板/通知/通话状态）。
# 查询结果由执行器写入 action.params.result，供编排层收集并注入下一轮 LLM 决策。
_QUERY_ACTION_TYPES: frozenset[ActionType] = frozenset({
    ActionType.READ_SMS,
    ActionType.GET_CLIPBOARD,
    ActionType.GET_NOTIFICATIONS,
    ActionType.GET_CALL_STATE,
})

# 查询动作默认参数（LLM 未指定时使用）
_QUERY_DEFAULT_LIMIT: int = 20
_SMS_TYPES: tuple[str, ...] = ("inbox", "sent")


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
        self._executors: dict[ActionType, ClickExecutor | TypeExecutor | SwipeExecutor | WaitExecutor] = {
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
                if action.action_type in _QUERY_ACTION_TYPES:
                    return self._execute_query_action(action)
                return self._execute_system_action(action)

            result: bool = executor.execute(action)
            logger.info("Action 执行%s: type=%s", "成功" if result else "失败", action.action_type.value)
            return result

        except Exception as exc:
            logger.error("Action 执行异常: type=%s, error=%s", action.action_type.value, exc)
            raise

    def _execute_query_action(self, action: Action) -> bool:
        """
        执行系统级查询动作（READ_SMS / GET_CLIPBOARD / GET_NOTIFICATIONS / GET_CALL_STATE）。

        通过 ADB 控制器读取系统信息（短信 / 剪贴板 / 通知 / 通话状态），
        查询结果写入 action.params.result 供编排层收集；参数缺失或非法时
        回退默认值（sms_type=inbox / limit=20），保证 LLM 输出宽松。
        查询动作不改变页面，成功即返回 True。

        参数
        ----------
        action : Action
            系统查询指令，执行成功后其 params.result 携带查询结果。

        返回
        -------
        bool
            执行是否成功（查询命令执行成功即 True；ADB 层对内容解析失败
            已容错返回空值，此处不视为失败）。
        """
        try:
            adb = self._dm.get_adb()

            if action.action_type == ActionType.READ_SMS:
                sms_type = action.params.sms_type
                if sms_type not in _SMS_TYPES:
                    if sms_type:
                        logger.warning("无效的短信类型 %r，回退默认 inbox", sms_type)
                    sms_type = "inbox"
                result = adb.get_sms_messages(
                    sms_type=sms_type,
                    limit=self._normalize_limit(action.params.limit),
                )
            elif action.action_type == ActionType.GET_CLIPBOARD:
                result = adb.get_clipboard()
            elif action.action_type == ActionType.GET_NOTIFICATIONS:
                result = adb.get_notifications(limit=self._normalize_limit(action.params.limit))
            elif action.action_type == ActionType.GET_CALL_STATE:
                result = adb.get_call_state()
            else:
                logger.warning("未知的查询动作类型: %s", action.action_type)
                return False

            action.params.result = result
            logger.info("系统查询执行成功: type=%s", action.action_type.value)
            return True
        except Exception as exc:
            logger.error("系统查询执行失败: type=%s, error=%s", action.action_type.value, exc)
            action.params.result = None
            return False

    @staticmethod
    def _normalize_limit(limit: object) -> int:
        """
        归一化查询条数上限：非正整数（含 None/字符串/0/负数）回退默认 20。

        参数
        ----------
        limit : object
            LLM 传入的 limit 参数（可能为 None / 非法字符串）。

        返回
        -------
        int
            合法正整数原样返回，否则返回默认 20。
        """
        try:
            value = int(limit)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return _QUERY_DEFAULT_LIMIT
        if value <= 0:
            return _QUERY_DEFAULT_LIMIT
        return value

    def _execute_system_action(self, action: Action) -> bool:
        """
        执行系统级操作（BACK / HOME / RECENT_APPS / OPEN_APP / CLOSE_APP /
        LOCK_SCREEN / OPEN_NOTIFICATIONS / ROTATE_SCREEN / VOLUME_UP / VOLUME_DOWN
        / TERMINATE / VERIFY 等）。

        部分操作（熄屏、通知栏、旋转、音量）通过 ADB 执行，其余通过 U2Controller。

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
            adb = self._dm.get_adb()
            system_actions: dict[ActionType, Callable] = {
                ActionType.BACK: u2.press_back,
                ActionType.HOME: u2.press_home,
                ActionType.RECENT_APPS: u2.press_recent,
                ActionType.OPEN_APP: lambda: u2.app_start(action.params.package_name or ""),
                ActionType.CLOSE_APP: lambda: u2.app_stop(action.params.package_name or ""),
                ActionType.SCREENSHOT: lambda: self._capture_screenshot(),
                ActionType.LOCK_SCREEN: adb.lock_screen,
                ActionType.OPEN_NOTIFICATIONS: adb.open_notifications,
                ActionType.ROTATE_SCREEN: lambda: adb.set_rotation(self._parse_rotation(action.params.direction)),
                ActionType.VOLUME_UP: adb.volume_up,
                ActionType.VOLUME_DOWN: adb.volume_down,
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
    def _parse_rotation(direction: str | None) -> int:
        """
        将方向字符串解析为旋转值。

        参数
        ----------
        direction : str | None
            方向描述，可选 "portrait" / "landscape" / "reverse_portrait" / "reverse_landscape"。

        返回
        -------
        int
            旋转值（0-3）。

        异常
        ------
        ValueError
            direction 为非空但不在已知映射中时抛出。
        """
        mapping: dict[str, int] = {
            "portrait": 0,
            "landscape": 1,
            "reverse_portrait": 2,
            "reverse_landscape": 3,
        }
        if not direction:
            return 0
        if direction not in mapping:
            raise ValueError(f"无效的旋转方向: {direction}，有效值: {list(mapping.keys())}")
        return mapping[direction]

    def _apply_tuning(self, params: ActionParams) -> None:
        """
        对坐标参数应用微调偏移。

        当 enable_tuning 启用时，对 (x, y) 坐标分别加上配置的偏移量，
        并将结果裁剪到屏幕有效范围内（防止负坐标或超出屏幕）。

        参数
        ----------
        params : ActionParams
            待微调的操作参数，会直接修改其中的 x, y 值。
        """
        screen_w, screen_h = self._dm.get_screen_size()
        if params.x is not None:
            old_x: int = params.x
            params.x = max(0, min(screen_w - 1, params.x + settings.coordinate_tuning.offset_x))
            logger.debug("坐标微调 X: %d -> %d (offset=%d)", old_x, params.x, settings.coordinate_tuning.offset_x)
        if params.y is not None:
            old_y: int = params.y
            params.y = max(0, min(screen_h - 1, params.y + settings.coordinate_tuning.offset_y))
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
