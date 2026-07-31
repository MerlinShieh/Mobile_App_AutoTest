"""
操作指令数据模型。

定义 Action 和 ActionParams 两个数据类，分别表示一个完整的操作指令
及其参数。核心设计理念是 element_id 优先定位：
LLM 输出 element_id（如 "#1"），系统从本地索引查询完整信息后执行。
"""

from dataclasses import dataclass, field
from typing import Optional

from .enums import ActionType
from ..logger import get_logger

logger = get_logger(__name__)


@dataclass
class ActionParams:
    """
    操作参数字段集合。

    不同 ActionType 使用不同的字段组合。element_id 是 LLM 首选的定位方式，
    (x, y) 坐标作为后备定位方案。

    参数
    ----------
    element_id : Optional[str]
        LLM 从结构化摘要中选择的元素编号，格式如 "#1"。
    x : Optional[int]
        像素坐标 X（px），与 element_id 二选一。
    y : Optional[int]
        像素坐标 Y（px），与 element_id 二选一。
    ui_element : Optional[str]
        UI 树中的元素标识，如 resource-id 或 text。
    text : Optional[str]
        文本输入操作（TYPE）时需要填入的文本内容。
    points : Optional[list[tuple[int, int]]]
        滑动轨迹的坐标点列表，用于 SWIPE_POINT。
    direction : Optional[str]
        滚动方向，可选 "up" / "down" / "left" / "right"。
    distance_ratio : float
        滚动距离占屏幕尺寸的比例，默认 0.6（60%）。
    duration_ms : int
        WAIT 操作的等待持续时间（毫秒）。
    package_name : Optional[str]
        应用包名，用于 OPEN_APP / CLOSE_APP。
    display_id : int
        多屏场景下目标显示器 ID。
    max_retries : int
        单步最大重试次数，由 StepRunner 设置。
    retry_interval_ms : int
        重试间隔时间（毫秒）。
    """
    element_id: Optional[str] = None
    x: Optional[int] = None
    y: Optional[int] = None
    ui_element: Optional[str] = None
    text: Optional[str] = None
    points: Optional[list[tuple[int, int]]] = None
    direction: Optional[str] = None
    distance_ratio: float = 0.6
    duration_ms: int = 1500
    package_name: Optional[str] = None
    display_id: int = 0
    max_retries: int = 3
    retry_interval_ms: int = 2000
    match: bool = False
    """验证操作的匹配结果（true=匹配/验证通过, false=不匹配/验证失败），用于 VERIFY 动作。"""

    def to_dict(self) -> dict:
        """
        将参数序列化为字典，跳过值为 None 的字段。
        元组列表会被转为嵌套列表以支持 JSON 序列化。

        返回
        -------
        dict
            序列化后的参数字典。
        """
        result: dict = {}
        for k, v in self.__dict__.items():
            if v is not None:
                if isinstance(v, list) and len(v) > 0 and isinstance(v[0], tuple):
                    result[k] = [[int(x), int(y)] for x, y in v]
                else:
                    result[k] = v
        return result


@dataclass
class Action:
    """
    完整的操作指令。

    包含操作类型、参数、理由和执行超时时间。
    使用前应调用 validate() 方法校验参数完整性。

    参数
    ----------
    action_type : ActionType
        操作类型，决定哪些 params 字段是必须的。
    params : ActionParams
        操作参数集合。
    reason : str
        LLM 给出的操作理由，用于日志和调试追踪。
    timeout_ms : int
        本步骤执行的超时时间（毫秒）。
    """
    action_type: ActionType
    params: ActionParams
    reason: str = ""
    timeout_ms: int = 10000

    def validate(self) -> list[str]:
        """
        根据 action_type 校验必要参数，返回所有缺失字段的提示列表。

        校验规则
        --------
        - CLICK / DOUBLE_CLICK / LONG_CLICK：需要 element_id 或 (x, y)
        - TYPE：需要 text 以及 element_id 或 (x, y)
        - SWIPE / SWIPE_POINT：需要至少 2 个轨迹点
        - SCROLL：需要 direction 字段
        - OPEN_APP：需要 package_name

        返回
        -------
        list[str]
            缺失字段的描述列表，为空表示参数完整。
        """
        missing: list[str] = []
        p = self.params
        click_types = (ActionType.CLICK, ActionType.DOUBLE_CLICK, ActionType.LONG_CLICK)

        if self.action_type in click_types:
            if not p.element_id and (p.x is None or p.y is None):
                missing.append("element_id 或 (x, y) 至少提供其一")
        elif self.action_type == ActionType.TYPE:
            if not p.text:
                missing.append("text")
            if not p.element_id and (p.x is None or p.y is None):
                missing.append("element_id 或 (x, y) 用于聚焦目标")
        elif self.action_type == ActionType.SWIPE:
            if not p.points and not p.direction:
                missing.append("direction（up/down/left/right）或 points（至少需要 2 个点）")
        elif self.action_type == ActionType.SWIPE_POINT:
            if not p.points or len(p.points) < 2:
                missing.append("points（至少需要 2 个点）")
        elif self.action_type == ActionType.SCROLL:
            if not p.direction:
                missing.append("direction（up/down/left/right）")
        elif self.action_type == ActionType.OPEN_APP:
            if not p.package_name:
                missing.append("package_name")

        if missing:
            logger.warning("Action 参数校验未通过: %s", missing)
        return missing

    def to_dict(self) -> dict:
        """
        将完整操作指令序列化为字典，用于日志记录和历史存储。

        返回
        -------
        dict
            包含 action_type、params、reason、timeout_ms 的字典。
        """
        return {
            "action_type": self.action_type.value,
            "params": self.params.to_dict(),
            "reason": self.reason,
            "timeout_ms": self.timeout_ms,
        }
