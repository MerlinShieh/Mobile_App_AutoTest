"""
弹窗检测与处理器 —— PopupHandler。

以 UI 树节点匹配为主弹窗检测手段，支持三种检测策略：
  1. Dialog 关键词节点匹配（resource-id / class-name 含 dialog 等）
  2. 覆盖层检测（控件面积 > 屏幕 60%）
  3. 特征文本匹配（"允许"、"拒绝"、"确定" 等按钮文本）

检测到弹窗后根据预置规则库（PatternRules）确定处理策略，
自动执行允许、拒绝、关闭等操作。未知类型弹窗上报 LLM 决策。
"""

from typing import Optional

from ..config import settings
from ..device.device_manager import DeviceManager
from ..logger import get_logger
from ..models.enums import PopupStrategy, PopupType
from ..models.perception import UINode, UITree
from .models import PopupDetectResult, PopupRule
from .pattern_rules import PatternRules

MAX_HANDLE_ATTEMPTS: int = 2
"""同一弹窗自动处理失败的最大尝试次数，超过后交由 LLM 决策，避免死循环。"""

logger = get_logger(__name__)


class PopupHandler:
    """
    弹窗检测与处理器。

    通过 UI 树节点特征匹配预置规则库，快速检测并自动处理常见弹窗。
    未知弹窗返回检测结果，由 StepRunner 决定是否上报 LLM。

    参数
    ----------
    device_manager : DeviceManager
        设备管理器实例，用于执行弹窗关闭操作。
    """

    DIALOG_KEYWORDS: set[str] = {"dialog", "alert", "dialogroot"}
    """节点 resource-id 或 class-name 中包含这些关键词时视为弹窗关联节点。

    注意：已移除 "popup"，因为 class_name 中的 PopupWindow / PopupMenu 等
    非弹窗控件是最大误报源（此类控件在正常页面中大量存在）。
    """

    FEATURE_TEXTS: set[str] = {
        "允许", "拒绝", "确定", "取消", "同意",
        "allow", "deny", "cancel", "ok", "agree",
    }
    """匹配弹窗按钮的特征文本集合。"""

    OVERLAY_AREA_RATIO: float = 0.85
    """覆盖层检测阈值：控件面积超过屏幕面积的此比例时视为覆盖层。

    注意：桌面的 Launcher 工作区或 Widget 容器面积可能超过 60%，
    提高阈值至 85% 以减少误报。真实的系统级弹窗覆盖层通常覆盖
    90%~100% 的屏幕面积。
    """

    _NON_OVERLAY_CLASSES: set[str] = {"android.widget.frame", "android.view.viewgroup"}
    """根容器 class_name 黑名单（小写前缀匹配）。

    页面根布局（FrameLayout / ViewGroup 及其子类）即使面积接近全屏且可点击，
    也属于正常页面结构而非弹窗覆盖层，检测时按前缀排除。
    """

    def __init__(self, device_manager: DeviceManager) -> None:
        """
        初始化 PopupHandler。

        参数
        ----------
        device_manager : DeviceManager
            设备管理器实例。
        """
        self._dm: DeviceManager = device_manager
        self._rules: PatternRules = PatternRules()
        self._popup_fingerprints: dict[str, int] = {}
        """弹窗指纹 -> 已尝试自动处理次数。用于跟踪同一弹窗的处理失败情况。"""
        logger.debug("PopupHandler 初始化完成")

    def _fingerprint(self, nodes: list[UINode]) -> str:
        """
        生成弹窗节点的稳定指纹。

        基于节点集合的 bounds 与 text 计算，用于识别"是否是同一个弹窗"。
        节点顺序不影响结果（对特征排序后拼接）。

        参数
        ----------
        nodes : list[UINode]
            弹窗关联的节点列表。

        返回
        -------
        str
            弹窗指纹字符串。
        """
        if not nodes:
            return ""
        features = sorted(
            (str(n.bounds), n.text or "") for n in nodes
        )
        return "|".join(f"{b}:{t}" for b, t in features)

    def _can_auto_handle(self, nodes: list[UINode]) -> bool:
        """
        判断该弹窗是否仍允许自动处理。

        同一弹窗（指纹相同）自动处理失败次数累计达到上限后，
        返回 False 表示不再自动处理，交由调用方决定（如上报 LLM）。

        参数
        ----------
        nodes : list[UINode]
            弹窗关联的节点列表。

        返回
        -------
        bool
            True 表示仍可自动处理，False 表示已达失败上限。
        """
        fp: str = self._fingerprint(nodes)
        if not fp:
            return True
        return self._popup_fingerprints.get(fp, 0) < MAX_HANDLE_ATTEMPTS

    def _record_handle_failure(self, nodes: list[UINode]) -> None:
        """
        记录一次自动处理失败。

        按弹窗指纹累计失败次数。成功后调用 _clear_fingerprint 重置。

        参数
        ----------
        nodes : list[UINode]
            弹窗关联的节点列表。
        """
        fp: str = self._fingerprint(nodes)
        if not fp:
            return
        self._popup_fingerprints[fp] = self._popup_fingerprints.get(fp, 0) + 1
        logger.debug("弹窗自动处理失败累计: fingerprint=%s, attempts=%d",
                     fp, self._popup_fingerprints[fp])

    def _clear_fingerprint(self, nodes: list[UINode]) -> None:
        """
        清空弹窗指纹的失败计数（处理成功后调用）。

        参数
        ----------
        nodes : list[UINode]
            弹窗关联的节点列表。
        """
        fp: str = self._fingerprint(nodes)
        if fp and fp in self._popup_fingerprints:
            self._popup_fingerprints.pop(fp, None)
            logger.debug("弹窗指纹失败计数已清除: %s", fp)

    def detect(self, tree: UITree) -> Optional[PopupDetectResult]:
        """
        在 UI 树中检测是否存在弹窗。

        按三种策略依次检测：Dialog 关键词 > 覆盖层 > 特征文本。
        任意策略匹配即返回检测结果。

        参数
        ----------
        tree : UITree
            当前页面的 UI 树对象。

        返回
        -------
        Optional[PopupDetectResult]
            检测到弹窗时返回 PopupDetectResult，否则返回 None。
        """
        if not settings.popup.enabled:
            logger.debug("弹窗检测已禁用，跳过")
            return None

        if not tree or not tree.local_index:
            logger.debug("UI 树为空，无法检测弹窗")
            return None

        dialog_nodes: list[UINode] = self._find_dialog_nodes(tree)
        if dialog_nodes:
            popup_type: PopupType = self._classify_by_nodes(dialog_nodes)
            logger.info("弹窗检测命中 Dialog 关键词: type=%s, nodes=%d",
                        popup_type.value, len(dialog_nodes))
            return PopupDetectResult(
                detected=True, popup_type=popup_type,
                dialog_nodes=dialog_nodes, confidence=0.85,
                auto_handlable=self._can_auto_handle(dialog_nodes),
            )

        overlay_nodes: list[UINode] = self._find_overlay(tree)
        if overlay_nodes:
            logger.info("弹窗检测命中覆盖层: nodes=%d", len(overlay_nodes))
            return PopupDetectResult(
                detected=True, popup_type=PopupType.UNKNOWN,
                dialog_nodes=overlay_nodes, confidence=0.7,
                auto_handlable=self._can_auto_handle(overlay_nodes),
            )

        text_match_nodes: list[UINode] = self._find_by_feature_text(tree)
        if text_match_nodes:
            logger.info("弹窗检测命中特征文本: nodes=%d", len(text_match_nodes))
            return PopupDetectResult(
                detected=True, popup_type=PopupType.UNKNOWN,
                dialog_nodes=text_match_nodes, confidence=0.6,
                auto_handlable=self._can_auto_handle(text_match_nodes),
            )

        logger.debug("弹窗检测未发现弹窗")
        return None

    def handle(self, detect_result: PopupDetectResult) -> bool:
        """
        处理检测到的弹窗。

        根据弹窗类型从规则库获取处理策略并执行。
        REPORT_TO_LLM 策略返回 False，由调用方决定上报 LLM。

        参数
        ----------
        detect_result : PopupDetectResult
            弹窗检测结果。

        返回
        -------
        bool
            True 表示弹窗已成功处理，False 表示需要上报 LLM 或处理失败。
        """
        if not detect_result.detected:
            return False

        strategy: PopupStrategy = self._rules.get_strategy(detect_result.popup_type)
        logger.info("处理弹窗: type=%s, strategy=%s", detect_result.popup_type.value, strategy.value)

        try:
            if strategy == PopupStrategy.ALLOW:
                ok = self._click_button_by_texts(["允许", "同意", "确定", "allow", "agree", "ok"])
            elif strategy == PopupStrategy.DENY:
                ok = self._click_button_by_texts(["拒绝", "deny", "禁止"])
            elif strategy == PopupStrategy.DISMISS:
                ok = self._dismiss_popup()
            elif strategy == PopupStrategy.CANCEL:
                ok = self._click_button_by_texts(["取消", "稍后", "later", "cancel"])
            elif strategy == PopupStrategy.REPORT_TO_LLM:
                logger.info("弹窗类型 %s 需上报 LLM 决策", detect_result.popup_type.value)
                return False
            else:
                logger.warning("未知的处理策略: %s", strategy)
                return False

            if ok:
                self._clear_fingerprint(detect_result.dialog_nodes)
            else:
                self._record_handle_failure(detect_result.dialog_nodes)
            return ok
        except Exception as exc:
            logger.error("弹窗处理异常: type=%s, error=%s", detect_result.popup_type.value, exc)
            self._record_handle_failure(detect_result.dialog_nodes)
            return False

    def _find_dialog_nodes(self, tree: UITree) -> list[UINode]:
        """
        通过 Dialog 关键词匹配查找弹窗相关节点。

        检查所有节点的 resource-id 和 class-name 是否包含 Dialog 关键词。

        参数
        ----------
        tree : UITree
            UI 树对象。

        返回
        -------
        list[UINode]
            匹配的弹窗节点列表。
        """
        results: list[UINode] = []
        for node in tree.local_index.values():
            rid: str = node.resource_id.lower()
            cls: str = node.class_name.lower()
            if any(k in rid or k in cls for k in self.DIALOG_KEYWORDS):
                results.append(node)
        return results

    def _find_overlay(self, tree: UITree) -> list[UINode]:
        """
        检测面积超过阈值比例的覆盖层节点。

        覆盖层通常是半透明背景或全屏弹窗的容器。
        额外过滤：不可点击且无文本的大面积节点被视为背景容器，跳过。

        参数
        ----------
        tree : UITree
            UI 树对象。

        返回
        -------
        list[UINode]
            覆盖层节点列表。
        """
        screen_w, screen_h = self._dm.get_screen_size()
        # 防御：get_screen_size 返回 (0,0) 时（设备未连接/ADB 失败），
        # screen_area=0 会导致所有非零面积节点被误判为覆盖层（弹窗误报死循环根因）。
        if screen_w <= 0 or screen_h <= 0:
            logger.warning("弹窗覆盖层检测跳过: 屏幕尺寸无效 (%d x %d)", screen_w, screen_h)
            return []
        screen_area: int = screen_w * screen_h
        return [
            n for n in tree.local_index.values()
            if n.area() > screen_area * self.OVERLAY_AREA_RATIO
            and (n.clickable or n.text)
            and not any(n.class_name.lower().startswith(p) for p in self._NON_OVERLAY_CLASSES)
        ]

    def _find_by_feature_text(self, tree: UITree) -> list[UINode]:
        """
        通过特征文本匹配查找弹窗按钮节点。

        检查节点的 text 是否在弹窗特征文本集合中。
        要求至少匹配到 2 个不同的特征文本（如"确定"+"取消"同时出现），
        防止单个"确定"/"取消"按钮在设置表单等正常页面中被误判为弹窗。

        参数
        ----------
        tree : UITree
            UI 树对象。

        返回
        -------
        list[UINode]
            匹配的按钮节点列表，不足 2 种不同文本时返回空列表。
        """
        matched = [
            n for n in tree.local_index.values()
            if n.text and n.text.strip().lower() in self.FEATURE_TEXTS
        ]
        unique_texts = {n.text.strip().lower() for n in matched}
        if len(unique_texts) >= 2:
            # 空间聚集度检查：真实弹窗的按钮通常聚集在同一区域；
            # 若匹配节点在水平或垂直方向的跨度超过屏幕尺寸的 60%，
            # 说明按钮分散在页面各处（更像正常表单页布局），判定非弹窗。
            # 屏幕尺寸无效 (0,0) 时跳过该检查，保留原有行为。
            screen_w, screen_h = self._dm.get_screen_size()
            if screen_w > 0 and screen_h > 0:
                centers = [n.center() for n in matched]
                xs = [c[0] for c in centers]
                ys = [c[1] for c in centers]
                span_x: int = max(xs) - min(xs)
                span_y: int = max(ys) - min(ys)
                if span_x > screen_w * 0.6 or span_y > screen_h * 0.6:
                    logger.debug("特征文本节点空间分散（span_x=%d, span_y=%d），判定非弹窗",
                                 span_x, span_y)
                    return []
            return matched
        return []

    def _classify_by_nodes(self, nodes: list[UINode]) -> PopupType:
        """
        根据弹窗节点集合的文本内容分类弹窗类型。

        通过关键词匹配判断弹窗类型，匹配关键词最多的类型作为结果。

        参数
        ----------
        nodes : list[UINode]
            弹窗关联的节点列表。

        返回
        -------
        PopupType
            分类得出的弹窗类型，无法分类时返回 UNKNOWN。
        """
        all_texts: set[str] = set()
        for n in nodes:
            if n.text:
                all_texts.add(n.text.strip().lower())

        keyword_map: dict[PopupType, set[str]] = {
            PopupType.PERMISSION_DIALOG: {"允许", "拒绝", "allow", "deny", "while using the app"},
            PopupType.UPDATE_DIALOG: {"更新", "升级", "update", "later", "稍后"},
            PopupType.AGREEMENT_DIALOG: {"用户协议", "隐私政策", "同意", "agree"},
            PopupType.AD_POPUP: {"广告", "ad", "skip", "跳过", "关闭"},
        }

        best_match: PopupType = PopupType.UNKNOWN
        best_score: int = 0

        for ptype, keywords in keyword_map.items():
            score: int = sum(1 for kw in keywords if kw in all_texts)
            if score > best_score:
                best_score = score
                best_match = ptype

        logger.debug("弹窗分类结果: type=%s, score=%d", best_match.value, best_score)
        return best_match

    def _click_button_by_texts(self, texts: list[str]) -> bool:
        """
        通过文本点击弹窗按钮。

        依次尝试 each 文本，任一成功即返回 True。

        参数
        ----------
        texts : list[str]
            按钮文本候选列表。

        返回
        -------
        bool
            是否成功点击了某个按钮。
        """
        try:
            try:
                u2 = self._dm.get_u2()
            except RuntimeError:
                logger.warning("u2 未初始化，无法通过文本点击弹窗")
                return False
            for text in texts:
                if u2.click_by_text(text, exact=False):
                    logger.info("弹窗按钮点击成功: text=%s", text)
                    return True
            logger.warning("未找到匹配的弹窗按钮: texts=%s", texts)
            return False
        except Exception as exc:
            logger.error("弹窗按钮点击失败: %s", exc)
            return False

    def _dismiss_popup(self) -> bool:
        """
        关闭弹窗。

        优先尝试点击「关闭」「X」等关闭按钮，失败后回退到系统返回键。

        返回
        -------
        bool
            弹窗是否已关闭。
        """
        try:
            try:
                u2 = self._dm.get_u2()
            except RuntimeError:
                logger.warning("u2 未初始化，无法关闭弹窗")
                return False
            for kw in ["关闭", "close", "x", "dismiss"]:
                if u2.click_by_text(kw, exact=False):
                    logger.info("弹窗关闭成功: keyword=%s", kw)
                    return True
            u2.press_back()
            logger.info("弹窗已通过返回键关闭")
            return True
        except Exception as exc:
            logger.error("弹窗关闭失败: %s", exc)
            return False
