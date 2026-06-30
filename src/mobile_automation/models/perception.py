"""
屏幕感知数据模型。

定义 UI 节点、UI 树（含三份本地数据）、空间索引和感知结果等
与屏幕状态感知相关的核心数据结构。
"""

from dataclasses import dataclass, field
from typing import Optional

from ..logger import get_logger

logger = get_logger(__name__)


@dataclass
class UINode:
    """
    UI 树中的单个节点。

    element_id 由 UITreeExtractor 自动分配，格式为 "#1", "#2", ...
    作为 LLM 与本地全量索引之间的桥梁标识。

    参数
    ----------
    element_id : str
        节点唯一编号，如 "#1"。
    resource_id : str
        Android resource-id，如 "com.example:id/btn_ok"。
    class_name : str
        控件类名，如 "android.widget.Button"。
    text : str
        控件显示的文本内容。
    content_desc : str
        无障碍描述内容（content-desc 属性）。
    bounds : tuple[int, int, int, int]
        控件边界 (left, top, right, bottom)。
    clickable : bool
        是否可点击。
    enabled : bool
        是否启用。
    focused : bool
        是否获得焦点。
    selected : bool
        是否被选中。
    checkable : bool
        是否可勾选。
    focusable : bool
        是否可获得焦点。
    scrollable : bool
        是否可滚动。
    long_clickable : bool
        是否可长按。
    password : bool
        是否为密码输入框。
    package : str
        所属应用包名。
    children : list[UINode]
        子节点列表。
    parent_id : str
        父节点的 element_id。
    index_path : str
        节点的 XML 层级路径，如 "0/1/3"。
    """
    element_id: str = ""
    resource_id: str = ""
    class_name: str = ""
    text: str = ""
    content_desc: str = ""
    bounds: tuple[int, int, int, int] = (0, 0, 0, 0)
    clickable: bool = False
    enabled: bool = True
    focused: bool = False
    selected: bool = False
    checkable: bool = False
    focusable: bool = False
    scrollable: bool = False
    long_clickable: bool = False
    password: bool = False
    package: str = ""
    children: list["UINode"] = field(default_factory=list)
    parent_id: str = ""
    index_path: str = ""

    def center(self) -> tuple[int, int]:
        """
        计算控件中心坐标。

        返回
        -------
        tuple[int, int]
            中心点 (x, y) 坐标。
        """
        left, top, right, bottom = self.bounds
        return ((left + right) // 2, (top + bottom) // 2)

    def area(self) -> int:
        """
        计算控件面积（像素平方）。

        返回
        -------
        int
            控件的像素面积。
        """
        left, top, right, bottom = self.bounds
        return (right - left) * (bottom - top)

    def is_visible(self) -> bool:
        """
        判断控件是否在屏幕上可见。

        可见条件：bounds 不为零且 enabled 为 True。

        返回
        -------
        bool
            是否可见。
        """
        return self.bounds != (0, 0, 0, 0) and self.enabled

    def has_text(self) -> bool:
        """
        判断控件是否包含文本信息（text 或 content-desc）。

        返回
        -------
        bool
            是否包含文本。
        """
        return bool(self.text or self.content_desc)

    def is_interactive(self) -> bool:
        """
        判断控件是否可交互（可点击 / 可获得焦点 / 可长按）。

        返回
        -------
        bool
            是否可交互。
        """
        return self.clickable or self.focusable or self.long_clickable


@dataclass
class UITree:
    """
    完整的 UI 树数据结构，包含三份本地数据。

    三份数据说明
    ------------
    - local_index：全量索引，存储所有节点的完整属性字典。
    - structured_summary：压缩的结构化文本摘要，仅含 LLM 决策所需信息。
    - spatial_index：基于网格的空间索引，支持坐标反查。

    参数
    ----------
    root : UINode
        UI 树的根节点。
    source : str
        数据来源，如 "uiautomator2"。
    raw_xml : str
        原始 XML dump 字符串。
    local_index : dict[str, UINode]
        按 element_id 索引的全量节点字典。
    structured_summary : str
        发送给 LLM 的结构化摘要文本。
    spatial_index : Optional[UISpatialIndex]
        空间索引实例，用于坐标反查。
    """
    root: UINode
    source: str = "uiautomator2"
    raw_xml: str = ""
    local_index: dict[str, UINode] = field(default_factory=dict)
    structured_summary: str = ""
    spatial_index: Optional["UISpatialIndex"] = None

    def get_clickable_elements(self) -> list[UINode]:
        """
        获取所有可点击且已启用的元素列表。

        返回
        -------
        list[UINode]
            可点击元素列表。
        """
        return [n for n in self.local_index.values() if n.clickable and n.enabled]

    def find_by_resource_id(self, rid: str) -> Optional[UINode]:
        """
        根据 resource-id 查找元素。

        参数
        ----------
        rid : str
            要查找的 resource-id。

        返回
        -------
        Optional[UINode]
            找到的节点，未找到时返回 None。
        """
        for n in self.local_index.values():
            if n.resource_id == rid:
                return n
        return None

    def find_by_text(self, text: str, partial: bool = False) -> list[UINode]:
        """
        根据文本内容查找元素。

        参数
        ----------
        text : str
            要匹配的文本。
        partial : bool
            是否使用部分匹配模式（包含即匹配）。

        返回
        -------
        list[UINode]
            匹配的节点列表，可能为空。
        """
        if partial:
            return [n for n in self.local_index.values() if text in n.text]
        return [n for n in self.local_index.values() if n.text == text]

    def get_by_element_id(self, element_id: str) -> Optional[UINode]:
        """
        根据 element_id 从本地索引中查找元素。

        这是 element_id 优先定位流程的核心查询方法。

        参数
        ----------
        element_id : str
            元素编号，如 "#3"。

        返回
        -------
        Optional[UINode]
            对应的节点，未找到时返回 None。
        """
        return self.local_index.get(element_id)


@dataclass
class UISpatialIndex:
    """
    空间索引：基于网格分组的坐标范围查询。

    将屏幕划分为 GRID_SIZE x GRID_SIZE 的网格，每个元素根据其 bounds
    落入一个或多个网格。支持通过 (x, y) 坐标快速反查覆盖该位置的所有元素 ID。

    参数
    ----------
    screen_width : int
        屏幕宽度（像素）。
    screen_height : int
        屏幕高度（像素）。
    """

    GRID_SIZE: int = 100

    def __init__(self, screen_width: int = 1080, screen_height: int = 2400):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.cols = (screen_width + self.GRID_SIZE - 1) // self.GRID_SIZE
        self.rows = (screen_height + self.GRID_SIZE - 1) // self.GRID_SIZE
        self._grid: dict[tuple[int, int], list[str]] = {}

    def insert(self, element_id: str, bounds: tuple[int, int, int, int]) -> None:
        """
        将一个元素插入空间索引网格。

        参数
        ----------
        element_id : str
            元素编号。
        bounds : tuple[int, int, int, int]
            元素边界 (left, top, right, bottom)。
        """
        left, top, right, bottom = bounds
        col_start = left // self.GRID_SIZE
        col_end = (right - 1) // self.GRID_SIZE
        row_start = top // self.GRID_SIZE
        row_end = (bottom - 1) // self.GRID_SIZE
        for r in range(row_start, row_end + 1):
            for c in range(col_start, col_end + 1):
                key = (r, c)
                if key not in self._grid:
                    self._grid[key] = []
                self._grid[key].append(element_id)

    def query(self, x: int, y: int) -> list[str]:
        """
        根据坐标查询覆盖该位置的所有元素 ID。

        参数
        ----------
        x : int
            查询点 X 坐标。
        y : int
            查询点 Y 坐标。

        返回
        -------
        list[str]
            覆盖该坐标的元素 ID 列表。
        """
        col = x // self.GRID_SIZE
        row = y // self.GRID_SIZE
        key = (row, col)
        return self._grid.get(key, [])

    def build(self, local_index: dict[str, UINode]) -> None:
        """
        从本地全量索引批量构建空间索引。

        参数
        ----------
        local_index : dict[str, UINode]
            按 element_id 索引的节点字典。
        """
        for eid, node in local_index.items():
            self.insert(eid, node.bounds)
        logger.debug("空间索引构建完成，共 %d 个网格、%d 个元素", len(self._grid), len(local_index))


@dataclass
class PerceptualResult:
    """
    一次完整的感知操作结果。

    包含截图数据、UI 树、页面稳定状态、变化评分和时间戳。

    参数
    ----------
    screenshot_base64 : str
        Base64 编码的截图数据。
    screenshot_format : str
        截图格式，如 "jpeg" / "png"。
    ui_tree : Optional[UITree]
        UI 树对象，可能为 None。
    page_stable : bool
        页面是否处于稳定状态。
    change_score : float
        页面变化评分，0~1 之间。
    timestamp_ms : int
        感知操作的时间戳（毫秒）。
    """
    screenshot_base64: str
    screenshot_format: str = "jpeg"
    ui_tree: Optional[UITree] = None
    page_stable: bool = True
    change_score: float = 0.0
    timestamp_ms: int = 0

    def get_screenshot_token_estimate(self) -> int:
        """
        估算当前截图在 LLM 上下文中消耗的 Token 数。

        估算逻辑：Base64 原始字节数的一半作为 Token 近似值。

        返回
        -------
        int
            估计的 Token 消耗数。
        """
        raw_bytes = len(self.screenshot_base64) * 3 / 4
        return int(raw_bytes / 2)


@dataclass
class PageChangeResult:
    """
    页面变化检测结果。

    综合 UI 树结构差异和图像 SSIM 差异两种检测手段的输出。

    参数
    ----------
    has_changed : bool
        页面是否发生了显著变化。
    structural_diff_score : float
        基于 UI 树的结构差异评分（0~1）。
    visual_diff_score : float
        基于 SSIM 的视觉差异评分（0~1）。
    changed_nodes : list[UINode]
        发生变化的节点列表。
    final_verdict : str
        检测结论的文字说明。
    """
    has_changed: bool
    structural_diff_score: float
    visual_diff_score: float
    changed_nodes: list[UINode]
    final_verdict: str
