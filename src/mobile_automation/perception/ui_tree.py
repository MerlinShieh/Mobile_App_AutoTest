"""
UI 树提取与解析模块 —— UITreeExtractor（核心模块）。

将 uiautomator2 的 XML dump 解析为结构化的 UINode 树，并构建三份本地数据：
- local_index：全量索引，保留所有节点的完整属性
- structured_summary：压缩的结构化文本摘要，发送给 LLM
- spatial_index：基于网格的坐标反查索引

六步数据流：
Step 1: u2.dump_hierarchy() -> 原始 XML
Step 2: lxml 解析 -> UINode 树
Step 3: 展平与过滤 -> 跳过容器节点
Step 4A: 构建本地索引 -> 分配 element_id
Step 4B: 构建空间索引 -> 网格分组
Step 5: 构建结构化摘要 -> 按区域分组 + 重叠集群
Step 6: LLM 返回 element_id -> 本地索引查 resource-id -> u2 执行
"""

import re
from typing import Any, Optional

import lxml.etree as ET

from ..config import settings
from ..device.device_manager import DeviceManager
from ..logger import get_logger
from ..models.perception import UINode, UITree, UISpatialIndex

logger = get_logger(__name__)


class UITreeExtractor:
    """
    UI 树提取与解析器。

    通过 uiautomator2 获取当前界面的 XML dump，经过解析、展平、
    索引构建和摘要生成四个阶段，产出包含三份本地数据的 UITree 对象。

    参数
    ----------
    device_manager : DeviceManager
        设备管理器实例，通过依赖注入传入。
    """

    CONTAINER_CLASSES: frozenset = frozenset({
        "LinearLayout", "FrameLayout", "RelativeLayout", "ViewGroup",
        "ViewStub", "Space", "GridLayout", "TableLayout",
        "android.widget.LinearLayout", "android.widget.FrameLayout",
        "android.widget.RelativeLayout", "android.view.ViewGroup",
        "androidx.constraintlayout.widget.ConstraintLayout",
        "androidx.cardview.widget.CardView",
    })
    """展平时跳过（仅保留子节点）的纯容器类名集合"""

    def __init__(self, device_manager: DeviceManager) -> None:
        self._dm = device_manager
        logger.debug("UITreeExtractor 初始化完成")

    def extract(self) -> UITree:
        """
        执行完整的 UI 树提取流程。

        六步流程：
        1. 通过 u2 获取原始 XML
        2. lxml 解析 XML 为 UINode 树
        3. 展平树结构，跳过纯容器节点
        4. 构建本地全量索引（分配 element_id）
        5. 构建空间索引（网格分组）
        6. 构建结构化摘要（按区域 + 重叠集群）

        返回
        -------
        UITree
            包含三份本地数据的 UI 树对象。
        """
        u2 = self._dm.get_u2()
        raw_xml = u2.dump_ui()
        logger.debug("原始 XML 长度: %d 字符", len(raw_xml))

        root = self._parse_xml(raw_xml)

        tree = UITree(root=root, raw_xml=raw_xml, source="uiautomator2")

        flattened = self._flatten(root)
        logger.debug("展平后节点数: %d", len(flattened))

        tree.local_index = self._build_local_index(flattened)
        logger.debug("本地索引构建完成: %d 个节点", len(tree.local_index))

        screen_w, screen_h = self._dm.get_screen_size()
        tree.spatial_index = UISpatialIndex(screen_width=screen_w, screen_height=screen_h)
        tree.spatial_index.build(tree.local_index)

        tree.structured_summary = self._build_summary(tree.local_index)
        logger.debug("结构化摘要构建完成，长度: %d 字符", len(tree.structured_summary))

        return tree

    def _parse_xml(self, xml_str: str) -> UINode:
        """
        将 XML 字符串解析为 UINode 树。

        使用 lxml 快速解析 XML，递归遍历每个节点并提取属性。

        参数
        ----------
        xml_str : str
            uiautomator2 dump 输出的原始 XML 字符串。

        返回
        -------
        UINode
            解析后的 UI 树根节点。
        """
        try:
            root_elem = ET.fromstring(xml_str.encode("utf-8"))
        except Exception as exc:
            logger.error("XML 解析失败: %s", exc)
            raise

        def _parse_recursive(elem: Any, index_path: str) -> UINode:
            bounds = self._parse_bounds(elem.get("bounds", "[0,0][0,0]"))
            node = UINode(
                resource_id=elem.get("resource-id", ""),
                class_name=elem.get("class", ""),
                text=elem.get("text", ""),
                content_desc=elem.get("content-desc", ""),
                bounds=bounds,
                clickable=elem.get("clickable", "false") == "true",
                enabled=elem.get("enabled", "true") == "true",
                focused=elem.get("focused", "false") == "true",
                selected=elem.get("selected", "false") == "false",
                checkable=elem.get("checkable", "false") == "true",
                focusable=elem.get("focusable", "false") == "true",
                scrollable=elem.get("scrollable", "false") == "true",
                long_clickable=elem.get("long-clickable", "false") == "true",
                password=elem.get("password", "false") == "true",
                package=elem.get("package", ""),
                index_path=index_path,
            )
            for i, child_elem in enumerate(elem):
                child_path = f"{index_path}/{i}"
                child_node = _parse_recursive(child_elem, child_path)
                child_node.parent_id = node.element_id
                node.children.append(child_node)
            return node

        return _parse_recursive(root_elem, "0")

    @staticmethod
    def _parse_bounds(bounds_str: str) -> tuple[int, int, int, int]:
        """
        解析 bounds 属性字符串为整数元组。

        参数
        ----------
        bounds_str : str
            bounds 字符串，格式如 "[10,20][100,200]"。

        返回
        -------
        tuple[int, int, int, int]
            (left, top, right, bottom) 坐标元组。
        """
        nums = re.findall(r"\d+", bounds_str)
        if len(nums) >= 4:
            return (int(nums[0]), int(nums[1]), int(nums[2]), int(nums[3]))
        logger.warning("bounds 解析失败: %s，返回 (0,0,0,0)", bounds_str)
        return (0, 0, 0, 0)

    def _flatten(self, node: UINode) -> list[UINode]:
        """
        递归展平 UINode 树，跳过纯容器节点。

        容器节点（如 LinearLayout、FrameLayout）本身不保留，
        仅将其子节点提升到父级层级。

        参数
        ----------
        node : UINode
            当前遍历的节点。

        返回
        -------
        list[UINode]
            展平后的非容器节点列表。
        """
        result: list[UINode] = []
        if not (node.children and node.class_name in self.CONTAINER_CLASSES):
            result.append(node)
        for child in node.children:
            result.extend(self._flatten(child))
        return result

    def _build_local_index(self, nodes: list[UINode]) -> dict[str, UINode]:
        """
        构建本地全量索引，为每个节点分配 element_id。

        按元素面积从小到大排序后分配 element_id（格式 "#1"、"#2"...），
        确保编号顺序在多次提取间相对稳定。

        参数
        ----------
        nodes : list[UINode]
            展平后的所有节点列表。

        返回
        -------
        dict[str, UINode]
            以 element_id 为键、UINode 为值的全量索引字典。
        """
        local_index: dict[str, UINode] = {}
        sorted_nodes = sorted(nodes, key=lambda n: n.area())

        for idx, node in enumerate(sorted_nodes, start=1):
            eid = f"#{idx}"
            node.element_id = eid
            local_index[eid] = node

        logger.debug("本地索引分配 %d 个 element_id", len(local_index))
        return local_index

    def _build_summary(self, local_index: dict[str, UINode]) -> str:
        """
        构建发送给 LLM 的结构化摘要文本。

        按区域分组（DIALOG / TOP_BAR / FEED / BOTTOM_NAV）后，
        对每组内的重叠元素进行聚类展示。仅包含可交互或有文本的节点。

        参数
        ----------
        local_index : dict[str, UINode]
            本地全量索引字典。

        返回
        -------
        str
            结构化的文本摘要，LLM 据此选择 element_id。
        """
        lines: list[str] = []
        groups = self._group_by_region(local_index)

        for region_name, node_ids in groups:
            lines.append(f"\n[{region_name}]")
            valid: list[UINode] = []
            for eid in node_ids:
                node = local_index[eid]
                if self._should_include_in_summary(node):
                    valid.append(node)

            if not valid:
                continue

            clusters = self._detect_overlap_clusters(valid)
            for cluster in clusters:
                if len(cluster) > 1:
                    primary = cluster[0]
                    lines.append(f"   重叠区域 [{len(cluster)}] bounds={list(primary.bounds)}")
                    for sn in cluster:
                        lines.append(f"    ├─ {self._format_node_line(sn)}")
                else:
                    lines.append(f"   {self._format_node_line(cluster[0])}")

        return "\n".join(lines)

    @staticmethod
    def _should_include_in_summary(node: UINode) -> bool:
        """
        判断节点是否应包含在结构化摘要中。

        过滤条件：bounds 为零的无效节点、密码输入框。
        只要节点满足以下任一条件即保留：
        - 可交互（clickable / focusable / long_clickable / checkable）
        - 有可见文本（text）
        - 有内容描述（content_desc）
        - 有 resource-id

        参数
        ----------
        node : UINode
            待判断的节点。

        返回
        -------
        bool
            True 表示应包含在摘要中。
        """
        if node.bounds == (0, 0, 0, 0) or node.password:
            return False
        is_interactive = node.clickable or node.focusable or node.long_clickable or node.checkable
        has_label = bool(node.text or node.content_desc)
        has_rid = bool(node.resource_id)
        if not is_interactive and not has_label and not has_rid:
            return False
        return True

    @staticmethod
    def _format_node_line(node: UINode) -> str:
        """
        将单个节点格式化为单行摘要文本。

        格式示例：
            #3 [clickable] 提交 id=com.example:id/btn_ok bounds=[100,200,300,400]

        参数
        ----------
        node : UINode
            待格式化的节点。

        返回
        -------
        str
            格式化的节点文本行。
        """
        attrs_list: list[str] = []
        if node.clickable:
            attrs_list.append("可点")
        if node.focusable:
            attrs_list.append("可聚焦")
        if node.long_clickable:
            attrs_list.append("可长按")
        if node.checkable:
            attrs_list.append("可勾选")
        if node.scrollable:
            attrs_list.append("可滚动")
        attrs = f"[{' '.join(attrs_list)}]" if attrs_list else ""

        text = node.text or node.content_desc or ""
        rid = f" id={node.resource_id}" if node.resource_id else ""
        return f"{node.element_id} {attrs} {text}{rid}".strip()

    def _group_by_region(self, local_index: dict[str, UINode]) -> list[tuple[str, list[str]]]:
        """
        将节点按屏幕区域分组。

        分组规则：
        - DIALOG：面积超过屏幕 60% 的节点
        - TOP_BAR：底部边界在屏幕顶部 10% 以内
        - BOTTOM_NAV：顶部边界在屏幕底部 10% 以内
        - FEED：中间区域的普通内容
        - UNKNOWN：无法归类的节点

        参数
        ----------
        local_index : dict[str, UINode]
            本地全量索引字典。

        返回
        -------
        list[tuple[str, list[str]]]
            [(区域名, element_id 列表), ...] 按优先级顺序排列。
        """
        _, screen_h = self._dm.get_screen_size()
        screen_area = self._dm.get_screen_size()[0] * screen_h

        groups: dict[str, list[str]] = {
            "DIALOG": [],
            "TOP_BAR": [],
            "FEED": [],
            "BOTTOM_NAV": [],
            "UNKNOWN": [],
        }

        for eid, node in local_index.items():
            _, top, _, bottom = node.bounds
            area = node.area()

            if area > screen_area * 0.6:
                groups["DIALOG"].append(eid)
            elif bottom <= int(screen_h * 0.1):
                groups["TOP_BAR"].append(eid)
            elif top >= int(screen_h * 0.9):
                groups["BOTTOM_NAV"].append(eid)
            else:
                groups["FEED"].append(eid)

        priority_order = ["DIALOG", "TOP_BAR", "FEED", "BOTTOM_NAV", "UNKNOWN"]
        return [(r, groups[r]) for r in priority_order if groups[r]]

    @staticmethod
    def _detect_overlap_clusters(nodes: list[UINode]) -> list[list[UINode]]:
        """
        检测并聚类 bounds 高度重叠的元素。

        重叠判定标准：两个节点的交集面积占较小节点面积 50% 以上。
        聚类后每个集群按 (clickable, 有文本, 有 resource-id, 子节点数) 排序，
        将最"重要"的元素排在首位。

        参数
        ----------
        nodes : list[UINode]
            待检测的节点列表。

        返回
        -------
        list[list[UINode]]
            重叠集群列表，每个集群内元素按重要性降序排列。
        """
        def _overlap_ratio(ba: tuple[int, int, int, int], bb: tuple[int, int, int, int]) -> float:
            ax1, ay1, ax2, ay2 = ba
            bx1, by1, bx2, by2 = bb
            ox1, oy1 = max(ax1, bx1), max(ay1, by1)
            ox2, oy2 = min(ax2, bx2), min(ay2, by2)
            if ox1 >= ox2 or oy1 >= oy2:
                return 0.0
            overlap_area = (ox2 - ox1) * (oy2 - oy1)
            a_area = (ax2 - ax1) * (ay2 - ay1)
            return overlap_area / a_area if a_area > 0 else 0.0

        def _priority_key(n: UINode) -> tuple:
            return (
                -int(n.clickable),
                -int(bool(n.text)),
                -int(bool(n.resource_id)),
                len(n.children),
            )

        assigned: set[str] = set()
        clusters: list[list[UINode]] = []

        for na in nodes:
            if na.element_id in assigned:
                continue
            cluster: list[UINode] = [na]
            assigned.add(na.element_id)

            for nb in nodes:
                if nb.element_id in assigned:
                    continue
                if _overlap_ratio(na.bounds, nb.bounds) > 0.5:
                    cluster.append(nb)
                    assigned.add(nb.element_id)

            if len(cluster) > 1:
                cluster.sort(key=_priority_key)
            clusters.append(cluster)

        return clusters
