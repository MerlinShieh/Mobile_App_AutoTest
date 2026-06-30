"""
页面变化检测模块 —— PageChangeDetector。

综合 UI 树结构差异和图像 SSIM 差异两种检测手段来判断页面是否发生变化。
结构差异权重 70%，视觉差异权重 30%，加权得分超过阈值判定为发生变化。
"""

import time
from typing import Optional

from ..config import settings
from ..logger import get_logger
from ..models.perception import UINode, UITree, PageChangeResult

logger = get_logger(__name__)


class PageChangeDetector:
    """
    页面变化检测器。

    通过对比前后两次感知结果判断页面是否发生显著变化。采用双通道检测：
    - 结构通道：对比 UI 树的节点增减和 bounds 变化（权重 70%）
    - 视觉通道：对比截图的 SSIM 结构相似性（权重 30%）

    同时提供 wait_stable() 方法等待页面稳定。

    使用示例
    --------
    >>> detector = PageChangeDetector()
    >>> tree1 = extractor.extract()
    >>> b64_1 = capture.capture_base64()
    >>> result = detector.compare(tree1, b64_1)
    >>> result.has_changed
    True
    """

    STRUCTURAL_WEIGHT: float = 0.7
    """结构差异在综合评分中的权重"""
    VISUAL_WEIGHT: float = 0.3
    """视觉差异在综合评分中的权重"""
    CHANGE_THRESHOLD: float = 0.45
    """综合变化判定阈值，超过此值认为页面发生了变化。同时要求结构差异评分至少达到此阈值的一半，
       防止时钟、通知等微小 UI 变化导致误判。"""

    def __init__(self) -> None:
        self._prev_tree: Optional[UITree] = None
        self._prev_screenshot: Optional[str] = None
        logger.debug("PageChangeDetector 初始化完成")

    def compare(self, current_tree: UITree, current_screenshot: str) -> PageChangeResult:
        """
        比较当前页面与上一次感知结果，返回变化检测结论。

        首次调用时无历史数据，直接保存当前感知结果并返回"已变化"。

        参数
        ----------
        current_tree : UITree
            当前页面的 UI 树（含 local_index）。
        current_screenshot : str
            当前页面的 Base64 截图字符串。

        返回
        -------
        PageChangeResult
            包含是否变化、结构评分、视觉评分、变化节点列表和判定的结果对象。
        """
        if self._prev_tree is None:
            self._prev_tree = current_tree
            self._prev_screenshot = current_screenshot
            logger.info("首次感知，保存页面快照")
            return PageChangeResult(
                has_changed=True,
                structural_diff_score=1.0,
                visual_diff_score=1.0,
                changed_nodes=[],
                final_verdict="首次感知，保存页面快照",
            )

        structural_score, changed_nodes = self._structural_diff(current_tree, self._prev_tree)
        visual_score = self._visual_diff(current_screenshot, self._prev_screenshot)

        combined = structural_score * self.STRUCTURAL_WEIGHT + visual_score * self.VISUAL_WEIGHT
        # 结构差异必须达到阈值的一半以上，防止时钟/通知等微小变化被误判为页面变化
        structural_min = self.CHANGE_THRESHOLD * 0.5
        has_changed = combined > self.CHANGE_THRESHOLD and structural_score > structural_min
        verdict = (
            f"结构差异({structural_score:.2f}) 视觉差异({visual_score:.2f}) 综合({combined:.2f})"
        )

        self._prev_tree = current_tree
        self._prev_screenshot = current_screenshot

        logger.debug("页面变化检测: %s -> %s", "有变化" if has_changed else "无变化", verdict)
        return PageChangeResult(
            has_changed=has_changed,
            structural_diff_score=structural_score,
            visual_diff_score=visual_score,
            changed_nodes=changed_nodes,
            final_verdict=verdict,
        )

    def _structural_diff(
        self,
        cur: UITree,
        prev: UITree,
    ) -> tuple[float, list[UINode]]:
        """
        对比前后 UI 树的节点变化，计算结构差异评分。

        检测三类变化：新增节点、删除节点、bounds 发生变化的节点。
        评分 = 变化节点数 / 前一次总节点数。

        参数
        ----------
        cur : UITree
            当前 UI 树。
        prev : UITree
            上一次 UI 树。

        返回
        -------
        tuple[float, list[UINode]]
            (结构差异评分 0~1, 发生变化的节点列表)。
        """
        cur_ids = set(cur.local_index.keys())
        prev_ids = set(prev.local_index.keys())

        new_ids = cur_ids - prev_ids
        removed_ids = prev_ids - cur_ids
        common_ids = cur_ids & prev_ids

        changed_nodes: list[UINode] = []
        changed_common: list[UINode] = []

        for eid in common_ids:
            cur_node = cur.local_index[eid]
            prev_node = prev.local_index[eid]
            if cur_node.bounds != prev_node.bounds:
                changed_common.append(cur_node)

        changed_nodes.extend(cur.local_index[eid] for eid in new_ids)
        changed_nodes.extend(prev.local_index[eid] for eid in removed_ids)
        changed_nodes.extend(changed_common)

        total = len(prev_ids) or 1
        change_count = len(new_ids) + len(removed_ids) + len(changed_common)
        score = min(1.0, change_count / total)

        if new_ids:
            logger.debug("新增 %d 个节点", len(new_ids))
        if removed_ids:
            logger.debug("删除 %d 个节点", len(removed_ids))
        if changed_common:
            logger.debug("bounds 变化 %d 个节点", len(changed_common))

        return score, changed_nodes

    def _visual_diff(self, cur_b64: str, prev_b64: str) -> float:
        """
        通过 SSIM 算法比较前后两张截图的视觉差异。

        返回 SSIM 指数（0~1），越接近 1 表示越相似。
        若 opencv 或 skimage 未安装则返回 0。

        参数
        ----------
        cur_b64 : str
            当前截图的 Base64 字符串。
        prev_b64 : str
            上一次截图的 Base64 字符串。

        返回
        -------
        float
            SSIM 结构相似性指数，0~1。
        """
        if not prev_b64 or not cur_b64:
            return 1.0

        try:
            import base64

            import cv2
            import numpy as np

            def b64_to_img(b64_str: str) -> np.ndarray:
                raw = np.frombuffer(base64.b64decode(b64_str), dtype=np.uint8)
                return cv2.imdecode(raw, cv2.IMREAD_GRAYSCALE)

            img1 = b64_to_img(cur_b64)
            img2 = b64_to_img(prev_b64)

            if img1.shape != img2.shape:
                img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))
                logger.debug("视觉差异检测：图片尺寸不一致，已调整")

            try:
                from skimage.metrics import structural_similarity as ssim
                similarity = float(ssim(img1, img2, full=True)[0])
                return similarity
            except ImportError:
                logger.warning("scikit-image 未安装，SSIM 计算不可用")
                return 0.0

        except ImportError:
            logger.warning("opencv-python 或 numpy 未安装，视觉差异检测不可用")
            return 0.0
        except Exception as exc:
            logger.error("视觉差异检测异常: %s", exc)
            return 0.0

    def wait_stable(
        self,
        extractor: "UITreeExtractor",
        timeout_ms: Optional[int] = None,
        poll_ms: Optional[int] = None,
    ) -> bool:
        """
        等待页面 UI 树结构稳定（连续两次结构差异低于阈值）。

        轮询提取 UI 树并与前一次比较，当结构差异评分连续两次
        低于阈值时判定页面已稳定。

        参数
        ----------
        extractor : UITreeExtractor
            UI 树提取器实例，用于轮询获取页面结构。
        timeout_ms : Optional[int]
            最大等待时间（毫秒），默认值来自配置。
        poll_ms : Optional[int]
            轮询间隔（毫秒），默认值来自配置。

        返回
        -------
        bool
            True 表示在超时前页面已稳定，False 表示超时。
        """
        if timeout_ms is None:
            timeout_ms = settings.execution.page_stable_wait_ms
        if poll_ms is None:
            poll_ms = settings.execution.page_stable_poll_ms

        deadline = time.time() + timeout_ms / 1000.0
        stable_count = 0
        required_stable = 2
        threshold = settings.perception.page_stable_structural_threshold

        logger.info("等待页面稳定，超时 %d ms，轮询间隔 %d ms", timeout_ms, poll_ms)

        while time.time() < deadline:
            try:
                current_tree = extractor.extract()
                if self._prev_tree is not None:
                    score, _ = self._structural_diff(current_tree, self._prev_tree)
                    if score < threshold:
                        stable_count += 1
                        logger.debug("页面稳定计数: %d/%d (diff=%.3f)",
                                      stable_count, required_stable, score)
                        if stable_count >= required_stable:
                            logger.info("页面已稳定")
                            return True
                    else:
                        stable_count = 0
                self._prev_tree = current_tree
            except Exception as exc:
                logger.warning("等待稳定期间提取 UI 树失败: %s", exc)

            time.sleep(poll_ms / 1000.0)

        logger.warning("等待页面稳定超时")
        return False

    def reset(self) -> None:
        """
        重置检测器状态，清空历史快照。

        在切换任务或设备后调用，避免新旧页面误比较。
        """
        self._prev_tree = None
        self._prev_screenshot = None
        logger.debug("PageChangeDetector 状态已重置")
