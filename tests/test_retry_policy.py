"""重试策略模块测试。

测试 retry 装饰器的重试次数、指数退避和异常类型过滤功能。
"""

import time

import pytest

from mobile_automation.exception.retry_policy import retry


class TestRetryDecorator:
    """测试 retry 装饰器的核心功能。"""

    def test_success_on_first_try(self):
        """验证函数首次执行成功时不重试。"""
        call_count = 0

        @retry(max_retries=3)
        def func():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = func()
        assert result == "ok"
        assert call_count == 1

    def test_retry_until_success(self):
        """验证失败后重试直到成功。"""
        call_count = 0

        @retry(max_retries=3)
        def func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("temp error")
            return "success"

        result = func()
        assert result == "success"
        assert call_count == 3

    def test_retry_exhausted_raises(self):
        """验证重试耗尽后抛出最后一次异常。"""
        call_count = 0

        @retry(max_retries=2)
        def func():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("persistent error")

        with pytest.raises(RuntimeError, match="persistent error"):
            func()
        assert call_count == 3

    def test_exception_filter_specific(self):
        """验证只捕获指定异常类型，其他异常直接抛出。"""
        @retry(max_retries=2, exceptions=(ValueError,))
        def func():
            raise TypeError("not caught")

        with pytest.raises(TypeError, match="not caught"):
            func()

    def test_exception_filter_caught(self):
        """验证指定异常类型被捕获并重试。"""
        call_count = 0

        @retry(max_retries=2, exceptions=(ValueError,))
        def func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("caught")
            return "ok"

        result = func()
        assert result == "ok"
        assert call_count == 2

    def test_on_retry_callback(self):
        """验证 on_retry 回调在每次重试时被调用。"""
        retry_records = []

        @retry(max_retries=2, on_retry=lambda exc, attempt: retry_records.append((exc, attempt)))
        def func():
            raise ValueError("error")

        with pytest.raises(ValueError):
            func()
        assert len(retry_records) == 2
        assert isinstance(retry_records[0][0], ValueError)
        assert retry_records[0][1] == 1
        assert retry_records[1][1] == 2

    def test_max_retries_zero(self):
        """验证 max_retries=0 时最多执行一次，失败不重试。"""
        call_count = 0

        @retry(max_retries=0)
        def func():
            nonlocal call_count
            call_count += 1
            raise ValueError("no retry")

        with pytest.raises(ValueError):
            func()
        assert call_count == 1

    def test_backoff_delay_increases(self):
        """验证每次重试的延迟按指数增长（粗略验证）。"""
        delays = []

        original_sleep = time.sleep

        def mock_sleep(delay):
            delays.append(delay)
            original_sleep(0)

        time.sleep = mock_sleep

        try:
            @retry(max_retries=3, base_delay=0.01, backoff=2.0)
            def func():
                raise ValueError("error")

            with pytest.raises(ValueError):
                func()
            assert len(delays) == 3
            assert delays[0] == 0.01
            assert delays[1] == 0.02
            assert delays[2] == 0.04
        finally:
            time.sleep = original_sleep

    def test_function_with_arguments(self):
        """验证装饰器正确处理函数参数。"""
        @retry(max_retries=1)
        def add(a, b):
            return a + b

        assert add(1, 2) == 3

    def test_function_with_kwargs(self):
        """验证装饰器正确处理关键字参数。"""
        @retry(max_retries=1)
        def greet(name, greeting="Hello"):
            return f"{greeting}, {name}"

        assert greet("World", greeting="Hi") == "Hi, World"
