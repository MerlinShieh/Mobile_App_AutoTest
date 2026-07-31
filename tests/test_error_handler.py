"""异常处理器模块测试。

验证 ErrorHandler 的异常分类、恢复动作（重连/指数退避/终止）、
wrap_error 装饰器和 safe_call 安全调用功能。
"""

import time

import pytest

from mobile_automation.exception.error_handler import ErrorHandler
from mobile_automation.exception.exceptions import (
    DeviceConnectionError,
    LLMServiceError,
    LoopDetectedError,
    MobileAutomationError,
    TimeoutError,
)


class TestErrorHandlerClassify:
    """测试异常分类。"""

    def test_classify_connection(self):
        handler = ErrorHandler()
        category, recovery = handler.classify(DeviceConnectionError("离线"))
        assert category == "connection"
        assert recovery == "reconnect"

    def test_classify_llm(self):
        handler = ErrorHandler()
        category, recovery = handler.classify(LLMServiceError("超时", provider="mimo"))
        assert category == "llm"
        assert recovery == "retry_backoff"

    def test_classify_loop(self):
        handler = ErrorHandler()
        category, recovery = handler.classify(LoopDetectedError())
        assert category == "loop"
        assert recovery == "abort"

    def test_classify_unknown(self):
        handler = ErrorHandler()
        category, recovery = handler.classify(ValueError("普通错误"))
        assert category == "unknown"
        assert recovery == "report"


class TestErrorHandlerRecovery:
    """测试恢复动作。"""

    def test_reconnect_with_device_manager(self, mocker):
        """验证注入 DeviceManager 后重连成功。"""
        mock_dm = mocker.MagicMock()
        mock_dm.get_serial.return_value = "test-device"
        mock_dm.connect.return_value = True
        handler = ErrorHandler(device_manager=mock_dm)
        assert handler._handle_reconnect(DeviceConnectionError("离线")) is True
        mock_dm.connect.assert_called_once_with("test-device")

    def test_reconnect_without_device_manager(self):
        """验证未注入 DeviceManager 时重连失败。"""
        handler = ErrorHandler()
        assert handler._handle_reconnect(DeviceConnectionError("离线")) is False

    def test_reconnect_failure_returns_false(self, mocker):
        """验证重连抛异常时返回 False。"""
        mock_dm = mocker.MagicMock()
        mock_dm.connect.side_effect = RuntimeError("adb 不可用")
        handler = ErrorHandler(device_manager=mock_dm)
        assert handler._handle_reconnect(DeviceConnectionError("离线")) is False

    def test_retry_backoff_sleeps(self, mocker):
        """验证指数退避执行等待并返回 True。"""
        mock_sleep = mocker.patch("mobile_automation.exception.error_handler.time.sleep")
        handler = ErrorHandler()
        assert handler._handle_retry_backoff(LLMServiceError("超时", provider="mimo")) is True
        mock_sleep.assert_called_once()
        # 第一次退避为基础延迟
        assert mock_sleep.call_args[0][0] == handler.RETRY_BASE_DELAY

    def test_retry_backoff_capped(self, mocker):
        """验证退避延迟不超过最大上限。"""
        mock_sleep = mocker.patch("mobile_automation.exception.error_handler.time.sleep")
        handler = ErrorHandler()
        # 模拟多次重试使指数增长超过上限
        for _ in range(10):
            handler._handle_retry_backoff(LLMServiceError("超时", provider="mimo"))
        assert mock_sleep.call_args[0][0] == handler.RETRY_MAX_DELAY

    def test_abort_returns_false(self):
        """验证终止动作返回 False。"""
        handler = ErrorHandler()
        assert handler._handle_abort(LoopDetectedError()) is False

    def test_switch_capture_returns_false(self):
        """验证截图切换交由上层决策（返回 False）。"""
        handler = ErrorHandler()
        assert handler._handle_switch_capture(Exception("感知失败")) is False

    def test_switch_location_returns_false(self):
        """验证定位切换交由上层决策（返回 False）。"""
        handler = ErrorHandler()
        assert handler._handle_switch_location(Exception("执行失败")) is False


class TestErrorHandlerWrap:
    """测试 wrap_error 装饰器。"""

    def test_wrap_connection_error(self):
        """验证 ConnectionError 被包装为 DeviceConnectionError。"""

        @ErrorHandler.wrap_error
        def risky():
            raise ConnectionError("设备离线")

        with pytest.raises(DeviceConnectionError):
            risky()

    def test_wrap_builtin_timeout(self):
        """验证内置 TimeoutError 被包装为自定义 TimeoutError。"""

        @ErrorHandler.wrap_error
        def risky():
            raise TimeoutError("连接超时")

        with pytest.raises(TimeoutError):
            risky()

    def test_wrap_generic_error(self):
        """验证普通异常被包装为 MobileAutomationError。"""

        @ErrorHandler.wrap_error
        def risky():
            raise ValueError("参数错误")

        with pytest.raises(MobileAutomationError):
            risky()

    def test_wrap_preserves_metadata(self):
        """验证装饰器保留函数元数据（functools.wraps）。"""

        @ErrorHandler.wrap_error
        def risky_operation():
            """文档字符串。"""
            return "ok"

        assert risky_operation.__name__ == "risky_operation"
        assert risky_operation.__doc__ == "文档字符串。"

    def test_wrap_success_passthrough(self):
        """验证正常返回值透传。"""

        @ErrorHandler.wrap_error
        def ok():
            return "success"

        assert ok() == "success"


class TestErrorHandlerSafeCall:
    """测试 safe_call 安全调用。"""

    def test_safe_call_success(self):
        assert ErrorHandler.safe_call(lambda: 42) == 42

    def test_safe_call_exception_returns_default(self):
        def boom():
            raise ValueError("爆炸")

        assert ErrorHandler.safe_call(boom, default_return=False) is False
