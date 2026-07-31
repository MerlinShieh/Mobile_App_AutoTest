"""
弹窗数据模型定义。

定义弹窗检测结果（PopupDetectResult）和弹窗匹配规则（PopupRule）两个数据类。
PopupDetectResult 描述一次弹窗检测的输出，PopupRule 定义某类弹窗的处理策略。
"""

from dataclasses import dataclass, field

from ..logger import get_logger
from ..models.enums import PopupStrategy, PopupType

logger = get_logger(__name__)


@dataclass
class PopupDetectResult:
    """
    弹窗检测结果。

    承载一次弹窗检测的全部输出信息，包括是否检测到弹窗、
    弹窗类型、关联的 UI 节点列表和检测置信度。

    参数
    ----------
    detected : bool
        是否检测到弹窗。
    popup_type : PopupType
        弹窗类型，默认 PopupType.UNKNOWN。
    dialog_nodes : list
        与弹窗关联的 UI 节点列表。
    confidence : float
        检测结果的置信度，范围 0.0~1.0。
    """

    detected: bool
    popup_type: PopupType = PopupType.UNKNOWN
    dialog_nodes: list = field(default_factory=list)
    confidence: float = 0.0

    def __post_init__(self) -> None:
        """初始化完成后记录日志。"""
        if self.detected:
            logger.debug("弹窗检测结果: type=%s, confidence=%.2f, nodes=%d",
                         self.popup_type.value, self.confidence, len(self.dialog_nodes))


@dataclass
class PopupRule:
    """
    弹窗匹配规则。

    定义一类弹窗的匹配关键词和处理策略。
    规则按 priority 降序匹配，优先级高的规则优先匹配。

    参数
    ----------
    popup_type : PopupType
        规则对应的弹窗类型。
    matching_texts : list[str]
        用于匹配弹窗的关键词列表。
    strategy : PopupStrategy
        匹配成功后的处理策略。
    priority : int
        规则优先级，数值越大优先级越高，默认 5。
    """

    popup_type: PopupType
    matching_texts: list[str]
    strategy: PopupStrategy
    priority: int = 5

    def __post_init__(self) -> None:
        """初始化完成后记录日志。"""
        logger.debug("弹窗规则加载: type=%s, strategy=%s, priority=%d, keywords=%s",
                     self.popup_type.value, self.strategy.value, self.priority, self.matching_texts)
