"""页面变化检测模块测试。

测试 PageChangeDetector 的结构 diff、视觉 diff 和等待页面稳定功能。
"""

import pytest

from mobile_automation.models.perception import UINode, UITree, PageChangeResult
from mobile_automation.perception.page_diff import PageChangeDetector


class TestPageChangeDetector:
    """测试 PageChangeDetector 的页面变化检测能力。"""

    def test_first_comparison_returns_changed(self):
        """验证首次比较始终返回已变化。"""
        detector = PageChangeDetector()
        root = UINode()
        tree = UITree(root=root, local_index={})
        result = detector.compare(tree, "base64_string")
        assert result.has_changed is True
        assert result.structural_diff_score == 1.0

    def test_no_changes_returns_low_score(self):
        """验证两次相同页面比较返回低变化分。"""
        detector = PageChangeDetector()
        node = UINode(element_id="#1", bounds=(0, 0, 100, 100), clickable=True)
        root = UINode()
        tree = UITree(root=root, local_index={"#1": node})

        detector.compare(tree, "b64_1")
        result = detector.compare(tree, "b64_1")
        assert result.structural_diff_score == 0.0

    def test_new_node_detected(self):
        """验证新增节点被正确检测。"""
        detector = PageChangeDetector()
        root = UINode()
        tree1 = UITree(root=root, local_index={"#1": UINode(element_id="#1", bounds=(0, 0, 50, 50))})
        tree2 = UITree(root=root, local_index={
            "#1": UINode(element_id="#1", bounds=(0, 0, 50, 50)),
            "#2": UINode(element_id="#2", bounds=(100, 100, 200, 200)),
        })

        detector.compare(tree1, "b64_1")
        result = detector.compare(tree2, "b64_2")
        assert result.has_changed is True
        assert result.structural_diff_score > 0

    def test_removed_node_detected(self):
        """验证删除节点被正确检测（变化得分超过阈值 0.35）。"""
        detector = PageChangeDetector()
        root = UINode()
        # 2 个节点删除 1 个 = 0.5 结构得分
        # combined = 0.5*0.7 + 0*0.3 = 0.35，刚好等于阈值
        # 用 3 个节点删除 2 个 = 0.667 结构得分，combined = 0.467 > 0.35
        tree1 = UITree(root=root, local_index={
            "#1": UINode(element_id="#1", bounds=(0, 0, 50, 50)),
            "#2": UINode(element_id="#2", bounds=(100, 100, 200, 200)),
            "#3": UINode(element_id="#3", bounds=(50, 50, 100, 100)),
        })
        tree2 = UITree(root=root, local_index={
            "#1": UINode(element_id="#1", bounds=(0, 0, 50, 50)),
        })

        detector.compare(tree1, "b64_1")
        result = detector.compare(tree2, "b64_2")
        assert result.has_changed is True
        assert len(result.changed_nodes) == 2

    def test_bounds_change_detected(self):
        """验证节点位置变化被正确检测。"""
        detector = PageChangeDetector()
        root = UINode()
        tree1 = UITree(root=root, local_index={"#1": UINode(element_id="#1", bounds=(0, 0, 50, 50))})
        tree2 = UITree(root=root, local_index={"#1": UINode(element_id="#1", bounds=(10, 10, 60, 60))})

        detector.compare(tree1, "b64_1")
        result = detector.compare(tree2, "b64_2")
        assert result.structural_diff_score > 0
        assert len(result.changed_nodes) == 1

    def test_visual_diff_returns_zero_without_opencv(self, mocker):
        """验证未安装 opencv 时视觉差异返回 0。"""
        detector = PageChangeDetector()
        root = UINode()
        tree = UITree(root=root, local_index={})
        detector.compare(tree, "b64_1")
        result = detector.compare(tree, "b64_2")
        assert result.visual_diff_score == 0.0

    def test_reset_clears_state(self):
        """验证 reset 清空历史状态。"""
        detector = PageChangeDetector()
        root = UINode()
        tree = UITree(root=root, local_index={})
        detector.compare(tree, "b64_1")
        assert detector._prev_tree is not None
        detector.reset()
        assert detector._prev_tree is None
        assert detector._prev_screenshot is None

    def test_changed_nodes_list_includes_all_changes(self):
        """验证 changed_nodes 包含所有变化的节点。"""
        detector = PageChangeDetector()
        root = UINode()
        tree1 = UITree(root=root, local_index={
            "#1": UINode(element_id="#1", bounds=(0, 0, 50, 50)),
        })
        tree2 = UITree(root=root, local_index={
            "#1": UINode(element_id="#1", bounds=(0, 0, 50, 50)),
            "#2": UINode(element_id="#2", bounds=(100, 100, 200, 200)),
        })

        detector.compare(tree1, "b64_1")
        result = detector.compare(tree2, "b64_2")
        assert len(result.changed_nodes) == 1
        assert result.changed_nodes[0].element_id == "#2"

    def test_wait_stable_timeout(self, mocker):
        """验证 wait_stable 超时后返回 False。"""
        detector = PageChangeDetector()
        mock_extractor = mocker.MagicMock()

        mock_extractor.extract.side_effect = [
            UITree(root=UINode(), local_index={"#1": UINode(element_id=f"#{i}", bounds=(0, 0, 50, 50))})
            for i in range(10)
        ]

        result = detector.wait_stable(mock_extractor, timeout_ms=100, poll_ms=50)
        assert result is False

    def test_combined_score_below_threshold(self):
        """验证综合变化分低于阈值时 has_changed 为 False。"""
        detector = PageChangeDetector()
        root = UINode()
        tree = UITree(root=root, local_index={})

        detector.compare(tree, "b64_1")
        result = detector.compare(tree, "b64_1")

        identical_tree = UITree(root=root, local_index={})
        result2 = detector.compare(identical_tree, "b64_1")
        assert result2.has_changed is False

    def test_compare_returns_page_change_result(self):
        """验证 compare 返回 PageChangeResult 类型。"""
        detector = PageChangeDetector()
        root = UINode()
        tree = UITree(root=root, local_index={})
        result = detector.compare(tree, "b64_1")
        assert isinstance(result, PageChangeResult)
