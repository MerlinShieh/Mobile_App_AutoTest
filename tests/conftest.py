"""pytest 共享 fixtures 定义。

提供所有测试模块共用的 mock fixtures，避免重复定义。
使用 pytest-mock 的 mocker fixture 创建 Mock 对象。
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock

import pytest

# 自动将 src 目录加入 Python 路径
_src_path = str(Path(__file__).resolve().parent.parent / "src")
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

# 在导入项目模块前 mock 第三方依赖，避免因缺少硬件/网络依赖导致导入失败
_imports_to_mock = {
    "uiautomator2": MagicMock(),
    "openai": MagicMock(),
    "anthropic": MagicMock(),
    "cv2": MagicMock(),
    "numpy": MagicMock(),
}
for _mod_name, _mod_val in _imports_to_mock.items():
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = _mod_val

from mobile_automation.models.action import Action, ActionParams
from mobile_automation.models.enums import ActionType, StepStatus
from mobile_automation.models.perception import UINode, UITree, UISpatialIndex


@pytest.fixture
def mock_device_manager(mocker):
    """mock DeviceManager 单例的 fixture。

    返回的 mock 对象默认提供 u2/adb 控制器、屏幕尺寸和设备序列号，
    各测试可按需覆盖具体方法的返回值。
    """
    dm = mocker.patch("mobile_automation.device.device_manager.DeviceManager", autospec=True)
    instance = dm.return_value
    instance.get_screen_size.return_value = (1080, 2400)
    instance.get_serial.return_value = "emulator-5554"
    instance.list_devices.return_value = []
    instance.connect.return_value = True
    instance.disconnect.return_value = None
    instance.health_check.return_value = True
    instance._serial = "emulator-5554"
    instance._screen_size = (1080, 2400)

    mock_u2 = mocker.MagicMock()
    mock_u2.health_check.return_value = True
    mock_u2.get_device_info.return_value = {"displayWidth": 1080, "displayHeight": 2400}
    mock_u2.dump_ui.return_value = "<node></node>"
    mock_u2.screenshot.return_value = b"fake_image_bytes"
    mock_u2.click.return_value = None
    mock_u2.click_by_text.return_value = True
    instance.get_u2.return_value = mock_u2

    mock_adb = mocker.MagicMock()
    mock_adb.shell.return_value = ("1080x2400", "")
    mock_adb.screenshot.return_value = b"fake_adb_image_bytes"
    instance.get_adb.return_value = mock_adb

    return instance


@pytest.fixture
def mock_u2(mocker):
    """mock U2Controller 实例的 fixture。"""
    u2 = mocker.MagicMock()
    u2.health_check.return_value = True
    u2.get_device_info.return_value = {"displayWidth": 1080, "displayHeight": 2400}
    u2.dump_ui.return_value = "<node></node>"
    u2.screenshot.return_value = b"fake_image_bytes"
    u2.click.return_value = None
    u2.click_by_rid.return_value = True
    u2.click_by_text.return_value = True
    u2.send_text.return_value = None
    u2.clear_text.return_value = None
    u2.swipe.return_value = None
    u2.scroll.return_value = None
    u2.press_back.return_value = None
    u2.press_home.return_value = None
    u2.press_recent.return_value = None
    u2.app_start.return_value = None
    u2.app_stop.return_value = None
    u2.wait_stable.return_value = True
    return u2


@pytest.fixture
def mock_adb(mocker):
    """mock ADBController 实例的 fixture。"""
    adb = mocker.MagicMock()
    adb.shell.return_value = ("1080x2400", "")
    adb.screenshot.return_value = b"fake_adb_image_bytes"
    adb.reconnect.return_value = True
    adb.wait_for_device.return_value = True
    return adb


@pytest.fixture
def mock_perception(mocker):
    """mock ScreenCapture 实例的 fixture。"""
    perception = mocker.MagicMock()
    perception.capture.return_value = b"fake_resized_bytes"
    perception.capture_base64.return_value = "ZmFrZV9iYXNlNjQ="
    perception.capture_with_ui_tree.return_value = mocker.MagicMock(
        screenshot_base64="ZmFrZV9iYXNlNjQ=",
        screenshot_format="jpeg",
        ui_tree=mocker.MagicMock(
            local_index={},
            structured_summary="",
            spatial_index=None,
            get_by_element_id=lambda eid: None,
        ),
        page_stable=True,
        change_score=0.0,
        timestamp_ms=1000,
    )
    return perception


@pytest.fixture
def mock_llm_service(mocker):
    """mock LLMService 实例的 fixture。"""
    llm = mocker.MagicMock()
    llm.chat.return_value = '{"action_type": "click", "params": {"element_id": "#1"}, "reason": "test"}'
    llm.count_tokens.return_value = 100
    llm.provider = "qwen"
    adapter = mocker.MagicMock()
    adapter.context_window = 32000
    llm.adapter = adapter
    return llm


@pytest.fixture
def sample_ui_node():
    """返回一个带典型属性的 UINode 实例。"""
    return UINode(
        element_id="#1",
        resource_id="com.example:id/btn_ok",
        class_name="android.widget.Button",
        text="确定",
        content_desc="",
        bounds=(100, 200, 300, 400),
        clickable=True,
        enabled=True,
        focused=False,
        selected=False,
        checkable=False,
        focusable=True,
        scrollable=False,
        long_clickable=False,
        password=False,
        package="com.example",
        children=[],
        parent_id="",
        index_path="0/1",
    )


@pytest.fixture
def sample_action():
    """返回一个标准的 CLICK Action 实例。"""
    return Action(
        action_type=ActionType.CLICK,
        params=ActionParams(element_id="#1", x=200, y=300),
        reason="测试点击操作",
        timeout_ms=10000,
    )
