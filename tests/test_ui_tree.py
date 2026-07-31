"""UI 树提取模块测试。

使用模拟 XML 样本测试 UITreeExtractor 的 XML 解析、树展平、
element_id 分配、结构化摘要生成和空间索引构建。
"""

import pytest

from mobile_automation.models.perception import UINode
from mobile_automation.perception.ui_tree import UITreeExtractor

SAMPLE_XML = """<?xml version="1.0" encoding="utf-8"?>
<hierarchy rotation="0">
  <node bounds="[0,0][1080,2400]" class="android.widget.LinearLayout" package="com.example">
    <node bounds="[0,0][1080,200]" class="android.widget.LinearLayout" package="com.example">
      <node bounds="[20,40][200,160]" class="android.widget.Button" resource-id="com.example:id/back_btn"
            text="返回" clickable="true" enabled="true" focusable="true"/>
      <node bounds="[440,20][640,180]" class="android.widget.TextView" resource-id="com.example:id/title"
            text="设置" clickable="false" enabled="true"/>
    </node>
    <node bounds="[0,200][1080,2200]" class="android.widget.FrameLayout" package="com.example">
      <node bounds="[50,300][1030,500]" class="android.widget.Button" resource-id="com.example:id/btn_wifi"
            text="Wi-Fi" clickable="true" enabled="true"/>
      <node bounds="[50,550][1030,750]" class="android.widget.Button" resource-id="com.example:id/btn_bt"
            text="蓝牙" clickable="true" enabled="true"/>
      <node bounds="[50,800][1030,1000]" class="android.widget.Button" text="飞行模式" clickable="true" enabled="true"/>
    </node>
    <node bounds="[0,2200][1080,2400]" class="android.widget.LinearLayout" package="com.example">
      <node bounds="[40,2250][200,2350]" class="android.widget.TextView" text="首页" clickable="true" enabled="true"/>
      <node bounds="[440,2250][640,2350]" class="android.widget.TextView" text="我的" clickable="true" enabled="true"/>
    </node>
  </node>
</hierarchy>
"""

SAMPLE_XML_WITH_OVERLAP = """<?xml version="1.0" encoding="utf-8"?>
<hierarchy rotation="0">
  <node bounds="[0,0][1080,2400]" class="android.widget.LinearLayout" package="com.example">
    <node bounds="[100,100][500,500]" class="android.widget.Button" text="大按钮" clickable="true" enabled="true"/>
    <node bounds="[150,150][450,450]" class="android.widget.Button" text="小按钮" clickable="true" enabled="true"/>
    <node bounds="[600,600][800,800]" class="android.widget.Button" text="独立按钮" clickable="true" enabled="true"/>
  </node>
</hierarchy>
"""


class TestUITreeExtractor:
    """测试 UITreeExtractor 的 XML 解析与三份数据生成。"""

    def test_parse_xml_creates_tree(self, mocker):
        """验证 XML 解析创建完整的 UINode 树，根为 hierarchy。"""
        mock_dm = mocker.MagicMock()
        mock_dm.get_screen_size.return_value = (1080, 2400)
        mock_u2 = mocker.MagicMock()
        mock_u2.dump_ui.return_value = SAMPLE_XML
        mock_dm.get_u2.return_value = mock_u2

        extractor = UITreeExtractor(mock_dm)
        tree = extractor.extract()

        assert tree.root is not None
        # hierarchy 标签没有 class 属性，class_name 为空字符串
        assert tree.root.class_name == ""
        assert len(tree.root.children) == 1
        # 子节点是 LinearLayout
        assert tree.root.children[0].class_name == "android.widget.LinearLayout"

    def test_parse_bounds_valid(self):
        """验证 bounds 字符串正确解析为整数元组。"""
        result = UITreeExtractor._parse_bounds("[10,20][100,200]")
        assert result == (10, 20, 100, 200)

    def test_parse_bounds_invalid(self):
        """验证无效 bounds 返回 (0,0,0,0)。"""
        result = UITreeExtractor._parse_bounds("invalid")
        assert result == (0, 0, 0, 0)

    def test_extract_creates_local_index(self, mocker):
        """验证 extract 构建本地索引。"""
        mock_dm = mocker.MagicMock()
        mock_dm.get_screen_size.return_value = (1080, 2400)
        mock_u2 = mocker.MagicMock()
        mock_u2.dump_ui.return_value = SAMPLE_XML
        mock_dm.get_u2.return_value = mock_u2

        extractor = UITreeExtractor(mock_dm)
        tree = extractor.extract()

        assert len(tree.local_index) > 0
        for eid, node in tree.local_index.items():
            assert eid.startswith("#")
            assert isinstance(node, UINode)

    def test_extract_assignes_element_ids(self, mocker):
        """验证 element_id 从 #1 开始递增分配。"""
        mock_dm = mocker.MagicMock()
        mock_dm.get_screen_size.return_value = (1080, 2400)
        mock_u2 = mocker.MagicMock()
        mock_u2.dump_ui.return_value = SAMPLE_XML
        mock_dm.get_u2.return_value = mock_u2

        extractor = UITreeExtractor(mock_dm)
        tree = extractor.extract()

        eids = sorted(tree.local_index.keys())
        assert eids[0] == "#1"
        for i, eid in enumerate(eids, start=1):
            assert eid == f"#{i}"

    def test_extract_creates_structured_summary(self, mocker):
        """验证 extract 生成结构化摘要字符串。"""
        mock_dm = mocker.MagicMock()
        mock_dm.get_screen_size.return_value = (1080, 2400)
        mock_u2 = mocker.MagicMock()
        mock_u2.dump_ui.return_value = SAMPLE_XML
        mock_dm.get_u2.return_value = mock_u2

        extractor = UITreeExtractor(mock_dm)
        tree = extractor.extract()

        assert isinstance(tree.structured_summary, str)
        assert len(tree.structured_summary) > 0

    def test_extract_creates_spatial_index(self, mocker):
        """验证 extract 构建空间索引。"""
        mock_dm = mocker.MagicMock()
        mock_dm.get_screen_size.return_value = (1080, 2400)
        mock_u2 = mocker.MagicMock()
        mock_u2.dump_ui.return_value = SAMPLE_XML
        mock_dm.get_u2.return_value = mock_u2

        extractor = UITreeExtractor(mock_dm)
        tree = extractor.extract()

        assert tree.spatial_index is not None
        assert tree.spatial_index.cols > 0
        assert tree.spatial_index.rows > 0

    def test_container_classes_filtered_in_flatten(self, mocker):
        """验证容器类节点在展平中被过滤。"""
        mock_dm = mocker.MagicMock()
        mock_dm.get_screen_size.return_value = (1080, 2400)
        mock_u2 = mocker.MagicMock()
        mock_u2.dump_ui.return_value = SAMPLE_XML
        mock_dm.get_u2.return_value = mock_u2

        extractor = UITreeExtractor(mock_dm)
        tree = extractor.extract()

        for node in tree.local_index.values():
            assert node.class_name not in extractor.CONTAINER_CLASSES

    def test_flatten_preserves_non_container(self):
        """验证非容器节点被保留。"""
        container = UINode(class_name="android.widget.LinearLayout", children=[
            UINode(class_name="android.widget.Button", clickable=True),
        ])
        extractor = UITreeExtractor.__new__(UITreeExtractor)
        flattened = extractor._flatten(container)
        assert len(flattened) == 1
        assert flattened[0].class_name == "android.widget.Button"

    def test_summary_with_overlap_detection(self, mocker):
        """验证重叠节点在摘要中正确聚类。"""
        mock_dm = mocker.MagicMock()
        mock_dm.get_screen_size.return_value = (1080, 2400)
        mock_u2 = mocker.MagicMock()
        mock_u2.dump_ui.return_value = SAMPLE_XML_WITH_OVERLAP
        mock_dm.get_u2.return_value = mock_u2

        extractor = UITreeExtractor(mock_dm)
        tree = extractor.extract()

        assert "重叠区域" in tree.structured_summary

    def test_group_by_region(self, mocker):
        """验证区域分组逻辑。"""
        mock_dm = mocker.MagicMock()
        mock_dm.get_screen_size.return_value = (1080, 2400)

        extractor = UITreeExtractor(mock_dm)
        extractor._dm = mock_dm

        node1 = UINode(element_id="#1", bounds=(0, 0, 100, 100))
        node2 = UINode(element_id="#2", bounds=(0, 2200, 100, 2350))
        node3 = UINode(element_id="#3", bounds=(0, 0, 1000, 2000))
        local_index = {"#1": node1, "#2": node2, "#3": node3}
        groups = extractor._group_by_region(local_index)

        region_map = dict(groups)
        assert "#1" in region_map.get("TOP_BAR", []) or "#1" in region_map.get("FEED", [])
        assert "#2" in region_map.get("BOTTOM_NAV", [])
