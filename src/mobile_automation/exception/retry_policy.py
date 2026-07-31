"""
重试策略工具模块。

提供基于指数退避的重试装饰器，用于包装可能临时失败的操作，
如设备连接、LLM API 调用、截图获取等。
"""

import time
from functools import wraps
from typing import Any, Callable, Optional, Tuple, Type

from ..logger import get_logger

logger = get_logger(__name__)


def retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None,
) -> Callable:
    """
    重试装饰器 —— 使用指数退避策略重试被装饰函数。

    当函数抛出指定的异常类型时，自动按指数退避策略等待后重试。
    适用于设备连接、LLM API 调用、文件写入等可能临时失败的操作。

    参数
    ----------
    max_retries : int
        最大重试次数（不含首次执行），默认 3。
    base_delay : float
        首次重试前的基础等待时间（秒），默认 1.0。
    backoff : float
        退避倍数，每次重试等待时间 = base_delay * (backoff ^ attempt)，
        默认 2.0（即 1s, 2s, 4s, ...）。
    exceptions : Tuple[Type[Exception], ...]
        需要捕获并重试的异常类型元组，默认捕获所有 Exception。
    on_retry : Optional[Callable[[Exception, int], None]]
        每次重试前的回调函数，接收异常对象和当前重试次数，
        可用于自定义日志或状态更新。

    返回
    -------
    Callable
        包装后的函数，保持原有签名和返回值。

    异常
    ------
    Exception
        所有重试均失败后抛出最后一次捕获的异常。

    使用示例
    --------
    >>> @retry(max_retries=3, base_delay=1.0, backoff=2.0)
    ... def fetch_data(url: str) -> str:
    ...     return requests.get(url).text

    >>> @retry(max_retries=2, exceptions=(ConnectionError, TimeoutError))
    ... def connect_device(serial: str) -> bool:
    ...     return adb.connect(serial)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Optional[Exception] = None
            func_name = func.__qualname__

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exception = exc

                    if attempt < max_retries:
                        delay = base_delay * (backoff ** attempt)
                        logger.warning(
                            "%s 第 %d/%d 次重试失败: %s，%.1f 秒后重试",
                            func_name, attempt + 1, max_retries + 1, exc, delay,
                        )
                        if on_retry is not None:
                            on_retry(exc, attempt + 1)
                        time.sleep(delay)
                    else:
                        logger.error(
                            "%s 已达最大重试次数 %d，最终失败: %s",
                            func_name, max_retries + 1, exc,
                        )

            if last_exception is not None:
                raise last_exception

            return None

        return wrapper

    return decorator
