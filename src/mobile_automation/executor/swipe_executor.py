"""
滑动动作执行器 —— 处理 SWIPE / SWIPE_POINT / SCROLL 三类滑动操作。

通过 U2Controller 调用 uiautomator2 的滑动接口。
SWIPE：沿指定方向从屏幕中心滑动一段距离。
SWIPE_POINT：沿指定的坐标轨迹滑动。
SCROLL：在可滚动控件内沿指定方向滚动。
"""

from ..device.device_manager import DeviceManager
from ..logger import get_logger
from ..models.action import Action
from ..models.enums import ActionType

logger = get_logger(__name__)


class SwipeExecutor:
    """
    滑动动作执行器。

    支持 SWIPE（方向滑动）、SWIPE_POINT（轨迹滑动）和 SCROLL（滚动）三类操作。
    自动从 DeviceManager 获取屏幕尺寸用于计算滑动的起止坐标。

    参数
    ----------
    device_manager : DeviceManager
        设备管理器实例。
    """

    DIRECTION_VECTORS: dict[str, tuple[float, float]] = {
        "up": (0.0, -0.6),
        "down": (0.0, 0.6),
        "left": (-0.6, 0.0),
        "right": (0.6, 0.0),
    }
    """方向名称到 (x_ratio, y_ratio) 的映射，ratio 为相对屏幕尺寸的比例。"""

    def __init__(self, device_manager: DeviceManager) -> None:
        """
        初始化 SwipeExecutor。

        参数
        ----------
        device_manager : DeviceManager
            设备管理器实例。
        """
        self._dm: DeviceManager = device_manager
        logger.debug("SwipeExecutor 初始化完成")

    def execute(self, action: Action) -> bool:
        """
        执行滑动操作。

        根据 action_type 分发到对应的滑动逻辑。

        参数
        ----------
        action : Action
            滑动操作指令。

        返回
        -------
        bool
            滑动是否成功。
        """
        try:
            if action.action_type == ActionType.SCROLL:
                return self._execute_scroll(action)
            elif action.action_type == ActionType.SWIPE_POINT:
                return self._execute_swipe_point(action)
            else:
                return self._execute_swipe(action)

        except Exception as exc:
            logger.error("滑动操作执行异常: type=%s, error=%s", action.action_type.value, exc)
            return False

    def _execute_swipe(self, action: Action) -> bool:
        """
        执行方向滑动操作。

        根据 direction 从屏幕中心沿指定方向滑动一定的距离比例。

        参数
        ----------
        action : Action
            包含 direction 和 distance_ratio 的操作指令。

        返回
        -------
        bool
            滑动是否成功。
        """
        direction: str = action.params.direction or "up"
        distance_ratio: float = action.params.distance_ratio

        vector = self.DIRECTION_VECTORS.get(direction)
        if vector is None:
            logger.warning("不支持的滑动方向: %s，使用默认方向 up", direction)
            vector = self.DIRECTION_VECTORS["up"]

        screen_w, screen_h = self._dm.get_screen_size()
        cx, cy = screen_w // 2, screen_h // 2

        dx: int = int(vector[0] * screen_w * distance_ratio)
        dy: int = int(vector[1] * screen_h * distance_ratio)

        fx: int = cx
        fy: int = cy
        tx: int = cx + dx
        ty: int = cy + dy

        u2 = self._dm.get_u2()
        u2.swipe(fx, fy, tx, ty)
        logger.info("方向滑动成功: direction=%s, (%d,%d) -> (%d,%d)", direction, fx, fy, tx, ty)
        return True

    def _execute_swipe_point(self, action: Action) -> bool:
        """
        执行坐标轨迹滑动操作。

        沿 points 列表中的坐标点依次滑动。至少需要 2 个点。

        参数
        ----------
        action : Action
            包含 points 坐标点列表的操作指令。

        返回
        -------
        bool
            轨迹滑动是否成功。
        """
        points = action.params.points
        if not points or len(points) < 2:
            logger.warning("SWIPE_POINT 至少需要 2 个坐标点，当前 points=%s", points)
            return False

        fx, fy = points[0]
        tx, ty = points[-1]

        u2 = self._dm.get_u2()
        u2.swipe(fx, fy, tx, ty)
        logger.info("轨迹滑动成功: 起点(%d,%d) -> 终点(%d,%d)，途经 %d 个点",
                     fx, fy, tx, ty, len(points))
        return True

    SCROLL_STEPS: int = 55
    """滚动操作的滑动步数。值越小滑动越快，55 步约 0.3s，比拖拽快但比 fling 柔和。"""

    def _execute_scroll(self, action: Action) -> bool:
        """
        执行滚动操作。

        从屏幕中心沿指定方向滑动一定距离，方向语义：
          - "up"（向上滚动）= 手指从屏幕中心向上推 → 内容向上移 → 露出列表底部的条目
          - "down"（向下滚动）= 手指从屏幕中心向下拉 → 内容向下移 → 露出列表顶部的条目

        参数
        ----------
        action : Action
            包含 direction 和 distance_ratio 的操作指令。

        返回
        -------
        bool
            滚动是否成功。
        """
        direction: str = action.params.direction or "up"
        distance_ratio: float = action.params.distance_ratio

        vector = self.DIRECTION_VECTORS.get(direction)
        if vector is None:
            logger.warning("不支持的滚动方向: %s，使用默认方向 up", direction)
            vector = self.DIRECTION_VECTORS["up"]

        screen_w, screen_h = self._dm.get_screen_size()
        cx, cy = screen_w // 2, screen_h // 2

        dx: int = int(vector[0] * screen_w * distance_ratio)
        dy: int = int(vector[1] * screen_h * distance_ratio)

        fx, fy = cx, cy
        tx, ty = cx + dx, cy + dy

        u2 = self._dm.get_u2()
        u2.swipe(fx, fy, tx, ty, steps=self.SCROLL_STEPS)
        logger.info("滚动操作成功: direction=%s, (%d,%d) -> (%d,%d), steps=%d",
                     direction, fx, fy, tx, ty, self.SCROLL_STEPS)
        return True
