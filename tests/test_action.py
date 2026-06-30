"""Action 数据模型测试。

测试 Action 的参数校验逻辑、序列化方法和 ActionParams 的 to_dict 行为。
"""

import pytest

from mobile_automation.models.action import Action, ActionParams
from mobile_automation.models.enums import ActionType


class TestActionValidation:
    """测试 Action.validate() 参数合法性校验。"""

    def test_click_with_element_id_passes(self):
        """CLICK 操作提供 element_id 时校验通过。"""
        action = Action(ActionType.CLICK, ActionParams(element_id="#1"))
        missing = action.validate()
        assert missing == []

    def test_click_with_xy_passes(self):
        """CLICK 操作提供 (x, y) 坐标时校验通过。"""
        action = Action(ActionType.CLICK, ActionParams(x=100, y=200))
        missing = action.validate()
        assert missing == []

    def test_click_without_element_id_and_xy_fails(self):
        """CLICK 操作缺少 element_id 且缺少 (x, y) 时校验失败。"""
        action = Action(ActionType.CLICK, ActionParams())
        missing = action.validate()
        assert len(missing) == 1
        assert "element_id" in missing[0]

    def test_double_click_validation(self):
        """DOUBLE_CLICK 使用与 CLICK 相同的校验规则。"""
        action = Action(ActionType.DOUBLE_CLICK, ActionParams(element_id="#2"))
        assert action.validate() == []

    def test_long_click_validation(self):
        """LONG_CLICK 使用与 CLICK 相同的校验规则。"""
        action = Action(ActionType.LONG_CLICK, ActionParams(x=300, y=400))
        assert action.validate() == []

    def test_type_without_text_fails(self):
        """TYPE 操作缺少 text 时校验失败。"""
        action = Action(ActionType.TYPE, ActionParams(element_id="#1"))
        missing = action.validate()
        assert "text" in missing

    def test_type_with_text_and_element_id_passes(self):
        """TYPE 操作同时提供 text 和 element_id 时校验通过。"""
        action = Action(ActionType.TYPE, ActionParams(element_id="#1", text="hello"))
        missing = action.validate()
        assert missing == []

    def test_type_with_text_and_xy_passes(self):
        """TYPE 操作提供 text 和 (x, y) 时校验通过。"""
        action = Action(ActionType.TYPE, ActionParams(x=100, y=200, text="hello"))
        missing = action.validate()
        assert missing == []

    def test_type_with_text_but_no_focus_target_fails(self):
        """TYPE 操作有 text 但缺少 element_id 和 (x, y) 时校验失败。"""
        action = Action(ActionType.TYPE, ActionParams(text="hello"))
        missing = action.validate()
        assert len(missing) == 1
        assert "聚焦目标" in missing[0]

    def test_swipe_without_points_fails(self):
        """SWIPE 操作缺少 points 时校验失败。"""
        action = Action(ActionType.SWIPE, ActionParams())
        missing = action.validate()
        assert "points" in missing[0]

    def test_swipe_accepts_direction_as_alternative_to_points(self):
        """SWIPE 操作接受 direction 作为 points 的替代。"""
        action_pts = Action(ActionType.SWIPE, ActionParams(points=[(100, 200)]))
        action_dir = Action(ActionType.SWIPE, ActionParams(direction="up"))
        assert action_pts.validate() == []
        assert action_dir.validate() == []

    def test_swipe_point_requires_two_points(self):
        """SWIPE_POINT 操作至少需要 2 个点。"""
        action = Action(ActionType.SWIPE_POINT, ActionParams(points=[(100, 200)]))
        missing = action.validate()
        assert "points" in missing[0]

    def test_swipe_with_two_points_passes(self):
        """SWIPE 操作提供至少 2 个点时校验通过。"""
        action = Action(ActionType.SWIPE, ActionParams(points=[(100, 200), (300, 400)]))
        missing = action.validate()
        assert missing == []

    def test_scroll_without_direction_fails(self):
        """SCROLL 操作缺少 direction 时校验失败。"""
        action = Action(ActionType.SCROLL, ActionParams())
        missing = action.validate()
        assert "direction" in missing[0]

    def test_scroll_with_direction_passes(self):
        """SCROLL 操作提供 direction 时校验通过。"""
        action = Action(ActionType.SCROLL, ActionParams(direction="down"))
        missing = action.validate()
        assert missing == []

    def test_open_app_without_package_fails(self):
        """OPEN_APP 操作缺少 package_name 时校验失败。"""
        action = Action(ActionType.OPEN_APP, ActionParams())
        missing = action.validate()
        assert "package_name" in missing[0]

    def test_open_app_with_package_passes(self):
        """OPEN_APP 操作提供 package_name 时校验通过。"""
        action = Action(ActionType.OPEN_APP, ActionParams(package_name="com.example"))
        missing = action.validate()
        assert missing == []

    def test_back_needs_no_params(self):
        """BACK 等系统操作不需要额外参数校验。"""
        for at in [ActionType.BACK, ActionType.HOME, ActionType.WAIT, ActionType.SCREENSHOT,
                   ActionType.TERMINATE, ActionType.RECENT_APPS]:
            action = Action(at, ActionParams())
            assert action.validate() == []


class TestActionToDict:
    """测试 Action.to_dict() 序列化。"""

    def test_basic_serialization(self):
        """验证 to_dict 包含所有必要字段。"""
        action = Action(ActionType.CLICK, ActionParams(element_id="#1"), reason="test")
        d = action.to_dict()
        assert d["action_type"] == "click"
        assert d["params"]["element_id"] == "#1"
        assert d["reason"] == "test"
        assert d["timeout_ms"] == 10000

    def test_params_none_fields_skipped(self):
        """验证 to_dict 序列化时跳过 None 值的字段。"""
        action = Action(ActionType.WAIT, ActionParams())
        d = action.to_dict()
        params = d["params"]
        assert "element_id" not in params
        assert "x" not in params
        assert "y" not in params

    def test_params_points_tuple_conversion(self):
        """验证 points 中的 tuple 被转为 list。"""
        action = Action(ActionType.SWIPE, ActionParams(points=[(100, 200), (300, 400)]))
        d = action.to_dict()
        assert d["params"]["points"] == [[100, 200], [300, 400]]
