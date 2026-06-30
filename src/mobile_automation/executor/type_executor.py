"""
文本输入执行器 —— 处理 TYPE / CLEAR_TEXT 两类文本操作。

通过 U2Controller 调用 uiautomator2 的文本输入和清空接口。
TYPE 操作先聚焦目标元素（点击），再填入文本。
CLEAR_TEXT 操作清空输入框内容。
"""

from ..device.device_manager import DeviceManager
from ..logger import get_logger
from ..models.action import Action
from ..models.enums import ActionType

logger = get_logger(__name__)


class TypeExecutor:
    """
    文本输入执行器。

    支持 TYPE（填入文本）和 CLEAR_TEXT（清空文本）两种操作。
    执行 TYPE 前会自动点击目标元素以获取焦点。

    参数
    ----------
    device_manager : DeviceManager
        设备管理器实例。
    """

    def __init__(self, device_manager: DeviceManager) -> None:
        """
        初始化 TypeExecutor。

        参数
        ----------
        device_manager : DeviceManager
            设备管理器实例。
        """
        self._dm: DeviceManager = device_manager
        logger.debug("TypeExecutor 初始化完成")

    def execute(self, action: Action) -> bool:
        """
        执行文本输入或清空操作。

        TYPE：先点击目标坐标聚焦，再填入指定文本。
        CLEAR_TEXT：直接清空当前焦点输入框的内容。

        参数
        ----------
        action : Action
            文本操作指令。TYPE 需提供 text 字段和元素定位信息。

        返回
        -------
        bool
            操作是否成功。
        """
        try:
            u2 = self._dm.get_u2()

            if action.action_type == ActionType.CLEAR_TEXT:
                return self._execute_clear(u2)

            if action.action_type == ActionType.TYPE:
                return self._execute_type(u2, action)

            logger.warning("TypeExecutor 遇到未知操作类型: %s", action.action_type)
            return False

        except Exception as exc:
            logger.error("文本操作执行异常: type=%s, error=%s", action.action_type.value, exc)
            return False

    def _execute_type(self, u2, action: Action) -> bool:
        """
        执行文本填入操作。

        先点击目标坐标确保输入框获焦，再通过 send_keys 填入文本。
        目标坐标优先使用 (x, y)，其次使用 ui_element。

        参数
        ----------
        u2 : U2Controller
            U2Controller 实例。
        action : Action
            包含 text 和坐标信息的操作指令。

        返回
        -------
        bool
            文本填入是否成功。
        """
        text: str = action.params.text or ""
        if not text:
            logger.warning("TypeExecutor 收到空的 text 参数")
            return False

        x, y = action.params.x, action.params.y

        if x is not None and y is not None:
            try:
                u2.click(x, y)
                logger.debug("已点击目标坐标 (%d, %d) 获取焦点", x, y)
            except Exception as exc:
                logger.warning("聚焦点击失败: (%d, %d), error=%s", x, y, exc)

        try:
            u2.send_text(text)
            logger.info("文本输入成功: text=%s", text[:50] + ("..." if len(text) > 50 else ""))
            return True
        except Exception as exc:
            logger.error("文本输入失败: text=%s, error=%s", text[:50], exc)
            return False

    def _execute_clear(self, u2) -> bool:
        """
        执行清空文本操作。

        调用 uiautomator2 的 clear_text 接口清空当前焦点输入框。

        参数
        ----------
        u2 : U2Controller
            U2Controller 实例。

        返回
        -------
        bool
            清空操作是否成功。
        """
        try:
            u2.clear_text()
            logger.info("文本清空成功")
            return True
        except Exception as exc:
            logger.error("文本清空失败: %s", exc)
            return False
