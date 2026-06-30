"""截图获取模块测试。

使用 mock 设备管理器测试 ScreenCapture 的截图获取、
Base64 编码和截图缩放功能。
"""

import pytest

from mobile_automation.perception.screen_capture import ScreenCapture


class TestScreenCapture:
    """测试 ScreenCapture 的截图功能。"""

    def test_capture_uses_u2_first(self, mocker):
        """验证 capture 优先使用 uiautomator2 截图。"""
        mock_dm = mocker.MagicMock()
        mock_u2 = mocker.MagicMock()
        mock_u2.screenshot.return_value = b"fake_u2_image"
        mock_dm.get_u2.return_value = mock_u2

        mocker.patch("mobile_automation.perception.screen_capture.compress_image",
                     side_effect=lambda img, quality, max_size: b"compressed")

        sc = ScreenCapture(mock_dm)
        result = sc.capture(max_size=720)
        assert result is not None
        mock_u2.screenshot.assert_called_once()

    def test_capture_fallback_to_adb(self, mocker):
        """验证 u2 失败后 fallback 到 ADB 截图。"""
        mock_dm = mocker.MagicMock()
        mock_u2 = mocker.MagicMock()
        mock_u2.screenshot.side_effect = Exception("u2 error")
        mock_dm.get_u2.return_value = mock_u2

        mock_adb = mocker.MagicMock()
        mock_adb.screenshot.return_value = b"fake_adb_image"
        mock_dm.get_adb.return_value = mock_adb

        mocker.patch("mobile_automation.perception.screen_capture.compress_image",
                     side_effect=lambda img, quality, max_size: b"compressed")

        sc = ScreenCapture(mock_dm)
        result = sc.capture(max_size=720)
        assert result is not None
        mock_adb.screenshot.assert_called_once()

    def test_capture_all_fail_raises(self, mocker):
        """验证所有截图方式失败时抛出异常。"""
        mock_dm = mocker.MagicMock()
        mock_u2 = mocker.MagicMock()
        mock_u2.screenshot.side_effect = Exception("u2 error")
        mock_dm.get_u2.return_value = mock_u2

        mock_adb = mocker.MagicMock()
        mock_adb.screenshot.side_effect = Exception("adb error")
        mock_dm.get_adb.return_value = mock_adb

        sc = ScreenCapture(mock_dm)
        with pytest.raises(RuntimeError, match="所有截图方式均失败"):
            sc.capture(max_size=720)

    def test_capture_base64_returns_string(self, mocker):
        """验证 capture_base64 返回 Base64 字符串。"""
        mock_dm = mocker.MagicMock()
        mock_u2 = mocker.MagicMock()
        mock_u2.screenshot.return_value = b"fake_image"
        mock_dm.get_u2.return_value = mock_u2

        mocker.patch("mobile_automation.perception.screen_capture.compress_image",
                     side_effect=lambda img, quality, max_size: b"compressed")
        mocker.patch("mobile_automation.perception.screen_capture.encode_base64",
                     side_effect=lambda x: "Y29tcHJlc3NlZA==")

        sc = ScreenCapture(mock_dm)
        result = sc.capture_base64(max_size=720)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_capture_with_ui_tree_returns_perceptual_result(self, mocker):
        """验证 capture_with_ui_tree 返回完整感知结果。"""
        mock_dm = mocker.MagicMock()
        mock_dm.get_screen_size.return_value = (1080, 2400)
        mock_u2 = mocker.MagicMock()
        mock_u2.screenshot.return_value = b"fake_image"
        mock_u2.dump_ui.return_value = "<node></node>"
        mock_dm.get_u2.return_value = mock_u2

        mocker.patch("mobile_automation.perception.screen_capture.compress_image",
                     side_effect=lambda img, quality, max_size: b"compressed")
        mocker.patch("mobile_automation.perception.screen_capture.encode_base64",
                     side_effect=lambda x: "Y29tcHJlc3NlZA==")

        sc = ScreenCapture(mock_dm)
        result = sc.capture_with_ui_tree(max_size=720)

        assert result.screenshot_base64 == "Y29tcHJlc3NlZA=="
        assert result.screenshot_format == "jpeg"
        assert result.ui_tree is not None
        assert result.timestamp_ms > 0
