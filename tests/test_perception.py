"""感知层数据模型测试。

测试 UINode 的快捷方法、UITree 的查询接口和 UISpatialIndex 的网格索引。
"""

import pytest

from mobile_automation.models.perception import UINode, UITree, UISpatialIndex, PerceptualResult


class TestUINode:
    """测试 UINode 节点的核心方法。"""

    def test_center(self, sample_ui_node):
        """验证 center() 正确计算控件中心坐标。"""
        cx, cy = sample_ui_node.center()
        assert cx == (100 + 300) // 2
        assert cy == (200 + 400) // 2

    def test_area(self, sample_ui_node):
        """验证 area() 正确计算控件面积。"""
        area = sample_ui_node.area()
        assert area == (300 - 100) * (400 - 200)

    def test_is_visible_with_valid_bounds(self, sample_ui_node):
        """验证有效边界的节点可见。"""
        assert sample_ui_node.is_visible() is True

    def test_is_visible_with_zero_bounds(self):
        """验证零边界节点不可见。"""
        node = UINode(bounds=(0, 0, 0, 0), enabled=True)
        assert node.is_visible() is False

    def test_is_visible_disabled(self, sample_ui_node):
        """验证禁用节点不可见。"""
        node = UINode(bounds=(10, 10, 100, 100), enabled=False)
        assert node.is_visible() is False

    def test_has_text_true(self, sample_ui_node):
        """验证包含文本的节点返回 True。"""
        assert sample_ui_node.has_text() is True

    def test_has_text_false(self):
        """验证无文本节点返回 False。"""
        node = UINode(text="", content_desc="")
        assert node.has_text() is False

    def test_has_text_with_content_desc(self):
        """验证只有 content_desc 时也返回 True。"""
        node = UINode(text="", content_desc="描述内容")
        assert node.has_text() is True

    def test_is_interactive_clickable(self, sample_ui_node):
        """验证 clickable 节点可交互。"""
        assert sample_ui_node.is_interactive() is True

    def test_is_interactive_focusable(self):
        """验证 focusable 节点可交互。"""
        node = UINode(clickable=False, focusable=True, long_clickable=False)
        assert node.is_interactive() is True

    def test_is_interactive_false(self):
        """验证不可交互节点。"""
        node = UINode(clickable=False, focusable=False, long_clickable=False)
        assert node.is_interactive() is False


class TestUITree:
    """测试 UITree 的查询和数据管理方法。"""

    def test_get_clickable_elements(self, sample_ui_node):
        """验证获取所有可点击元素的过滤逻辑。"""
        node2 = UINode(element_id="#2", clickable=False, enabled=True)
        node3 = UINode(element_id="#3", clickable=True, enabled=False)
        root = UINode()
        tree = UITree(root=root, local_index={"#1": sample_ui_node, "#2": node2, "#3": node3})
        clickable = tree.get_clickable_elements()
        assert len(clickable) == 1
        assert clickable[0].element_id == "#1"

    def test_find_by_resource_id(self, sample_ui_node):
        """验证按 resource-id 查找节点。"""
        root = UINode()
        tree = UITree(root=root, local_index={"#1": sample_ui_node})
        node = tree.find_by_resource_id("com.example:id/btn_ok")
        assert node is not None
        assert node.element_id == "#1"

    def test_find_by_resource_id_not_found(self):
        """验证不存在的 resource-id 返回 None。"""
        root = UINode()
        tree = UITree(root=root, local_index={})
        assert tree.find_by_resource_id("not_exist") is None

    def test_find_by_text_exact(self, sample_ui_node):
        """验证精确文本搜索。"""
        root = UINode()
        tree = UITree(root=root, local_index={"#1": sample_ui_node})
        nodes = tree.find_by_text("确定", partial=False)
        assert len(nodes) == 1

    def test_find_by_text_exact_no_match(self, sample_ui_node):
        """验证精确搜索不匹配时不返回。"""
        root = UINode()
        tree = UITree(root=root, local_index={"#1": sample_ui_node})
        nodes = tree.find_by_text("取消", partial=False)
        assert nodes == []

    def test_find_by_text_partial(self, sample_ui_node):
        """验证模糊文本搜索。"""
        root = UINode()
        tree = UITree(root=root, local_index={"#1": sample_ui_node})
        nodes = tree.find_by_text("确", partial=True)
        assert len(nodes) == 1

    def test_get_by_element_id(self, sample_ui_node):
        """验证按 element_id 查询。"""
        root = UINode()
        tree = UITree(root=root, local_index={"#1": sample_ui_node})
        node = tree.get_by_element_id("#1")
        assert node is not None
        assert node.resource_id == "com.example:id/btn_ok"

    def test_get_by_element_id_not_found(self):
        """验证不存在的 element_id 返回 None。"""
        root = UINode()
        tree = UITree(root=root, local_index={})
        assert tree.get_by_element_id("#999") is None


class TestUISpatialIndex:
    """测试 UISpatialIndex 空间索引的网格管理。"""

    def test_insert_and_query(self):
        """验证插入节点后可通过坐标查询到。"""
        idx = UISpatialIndex(screen_width=1080, screen_height=2400)
        idx.insert("#1", (50, 50, 150, 150))
        results = idx.query(100, 100)
        assert "#1" in results

    def test_query_outside_grid_returns_empty(self):
        """验证查询超出屏幕范围的坐标返回空列表。"""
        idx = UISpatialIndex(screen_width=1080, screen_height=2400)
        results = idx.query(-1, -1)
        assert results == []

    def test_build_from_local_index(self, sample_ui_node):
        """验证从 local_index 批量构建索引。"""
        idx = UISpatialIndex(screen_width=1080, screen_height=2400)
        local_index = {"#1": sample_ui_node}
        idx.build(local_index)
        results = idx.query(200, 300)
        assert "#1" in results

    def test_multi_cell_element(self):
        """验证跨越多个网格的元素在多个格子中都可查到。"""
        idx = UISpatialIndex(screen_width=1080, screen_height=2400)
        idx.insert("#1", (0, 0, 250, 250))
        assert "#1" in idx.query(50, 50)
        assert "#1" in idx.query(220, 220)

    def test_grid_dimensions(self):
        """验证网格行列数计算正确。"""
        idx = UISpatialIndex(screen_width=1080, screen_height=2400)
        assert idx.cols == 11
        assert idx.rows == 24


class TestPerceptualResult:
    """测试 PerceptualResult 的方法。"""

    def test_screenshot_token_estimate(self):
        """验证截图 Token 估算逻辑。"""
        b64 = "A" * 100
        result = PerceptualResult(screenshot_base64=b64)
        estimate = result.get_screenshot_token_estimate()
        raw_bytes = len(b64) * 3 / 4
        assert estimate == int(raw_bytes / 2)
