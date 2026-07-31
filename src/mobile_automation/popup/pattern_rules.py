"""
弹窗模式规则库 —— PatternRules。

预置常见弹窗的处理规则，支持按优先级排序匹配。
每类弹窗（权限、更新、广告、协议等）定义了匹配关键词
和对应的处理策略（允许、拒绝、关闭、上报 LLM 等）。

规则优先级：权限(10) > 协议(10) > 更新(8) > 广告(5) > 未知(0)
"""

from ..logger import get_logger
from ..models.enums import PopupStrategy, PopupType
from .models import PopupRule

logger = get_logger(__name__)


class PatternRules:
    """
    弹窗模式规则库。

    管理一组 PopupRule，根据弹窗类型返回对应的处理策略。
    规则按 priority 降序匹配，优先级高的规则优先。

    使用方式
    --------
    >>> rules = PatternRules()
    >>> strategy = rules.get_strategy(PopupType.PERMISSION_DIALOG)
    >>> strategy.value
    'allow'
    """

    def __init__(self) -> None:
        """
        初始化 PatternRules，加载预置规则列表。

        内置 5 类规则：权限(10)、协议(10)、更新(8)、广告(5)、未知(0)。
        """
        self._rules: list[PopupRule] = [
            PopupRule(
                popup_type=PopupType.PERMISSION_DIALOG,
                matching_texts=["允许", "拒绝", "allow", "deny"],
                strategy=PopupStrategy.ALLOW,
                priority=10,
            ),
            PopupRule(
                popup_type=PopupType.UPDATE_DIALOG,
                matching_texts=["更新", "升级", "update", "later"],
                strategy=PopupStrategy.CANCEL,
                priority=8,
            ),
            PopupRule(
                popup_type=PopupType.AGREEMENT_DIALOG,
                matching_texts=["用户协议", "隐私政策", "同意"],
                strategy=PopupStrategy.ALLOW,
                priority=10,
            ),
            PopupRule(
                popup_type=PopupType.AD_POPUP,
                matching_texts=["广告", "ad", "skip"],
                strategy=PopupStrategy.DISMISS,
                priority=5,
            ),
            PopupRule(
                popup_type=PopupType.UNKNOWN,
                matching_texts=[],
                strategy=PopupStrategy.REPORT_TO_LLM,
                priority=0,
            ),
        ]
        logger.debug("PatternRules 初始化完成，共 %d 条规则", len(self._rules))

    def get_strategy(self, popup_type: PopupType) -> PopupStrategy:
        """
        根据弹窗类型返回对应的处理策略。

        按 priority 降序匹配第一条符合类型的规则。
        未匹配时默认返回 REPORT_TO_LLM 策略。

        参数
        ----------
        popup_type : PopupType
            待匹配的弹窗类型。

        返回
        -------
        PopupStrategy
            匹配到的处理策略，默认 REPORT_TO_LLM。
        """
        sorted_rules: list[PopupRule] = sorted(self._rules, key=lambda r: -r.priority)
        for rule in sorted_rules:
            if rule.popup_type == popup_type:
                logger.debug("规则匹配: type=%s -> strategy=%s", popup_type.value, rule.strategy.value)
                return rule.strategy

        logger.warning("未找到弹窗类型 %s 的规则，使用默认策略 REPORT_TO_LLM", popup_type.value)
        return PopupStrategy.REPORT_TO_LLM

    def add_rule(self, rule: PopupRule) -> None:
        """
        动态添加一条新规则。

        参数
        ----------
        rule : PopupRule
            待添加的弹窗规则。
        """
        self._rules.append(rule)
        logger.info("添加弹窗规则: type=%s, strategy=%s, priority=%d",
                     rule.popup_type.value, rule.strategy.value, rule.priority)

    def remove_rule(self, popup_type: PopupType) -> bool:
        """
        移除指定弹窗类型的所有规则。

        参数
        ----------
        popup_type : PopupType
            要移除的弹窗类型。

        返回
        -------
        bool
            是否移除了至少一条规则。
        """
        before: int = len(self._rules)
        self._rules = [r for r in self._rules if r.popup_type != popup_type]
        removed: int = before - len(self._rules)
        if removed > 0:
            logger.info("移除弹窗规则: type=%s, 共 %d 条", popup_type.value, removed)
        return removed > 0
