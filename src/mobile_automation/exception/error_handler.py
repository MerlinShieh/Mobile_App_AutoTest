"""
异常处理器 —— ErrorHandler。

按异常分类（连接、感知、LLM、执行、死循环、超时）提供统一的
异常处理入口。将原始异常封装为框架自定义异常，并根据异常类型
返回分类信息和推荐的恢复动作。

异常分类对照表
--------------
| 分类         | 对应异常类型                    | 推荐动作       |
|-------------|----------------------------------|----------------|
| connection  | DeviceConnectionError            | 自动重连       |
| perception  | PerceptionError                  | 切换截图方式   |
| llm         | LLMServiceError                  | 指数退避重试   |
| execution   | ActionExecutionError             | 切换定位方式   |
| loop        | LoopDetectedError                | 终止任务       |
| timeout     | TimeoutError                     | 按策略等待/终止 |
| unknown     | 其他 Exception                   | 上报调用方      |
"""

from typing import Any, Optional

from ..logger import get_logger
from .exceptions import (
    ActionExecutionError,
    DeviceConnectionError,
    LLMServiceError,
    LoopDetectedError,
    MobileAutomationError,
    PerceptionError,
    TimeoutError,
)
from .retry_policy import retry

logger = get_logger(__name__)


class ErrorHandler:
    """
    异常处理器。

    提供 classify 方法分类异常并返回恢复建议，以及 handle 方法
    执行实际的恢复动作。支持注册自定义异常类型的处理逻辑。

    使用方式
    --------
    >>> handler = ErrorHandler()
    >>> category, action = handler.classify(exc)
    >>> handler.handle(exc, category, action)
    """

    ERROR_MAP: dict[type, str] = {
        DeviceConnectionError: "connection",
        PerceptionError: "perception",
        LLMServiceError: "llm",
        ActionExecutionError: "execution",
        LoopDetectedError: "loop",
        TimeoutError: "timeout",
    }
    """异常类型到分类名称的映射。"""

    RECOVERY_ACTIONS: dict[str, str] = {
        "connection": "reconnect",
        "perception": "switch_capture",
        "llm": "retry_backoff",
        "execution": "switch_location",
        "loop": "abort",
        "timeout": "wait_or_abort",
        "unknown": "report",
    }
    """异常分类到推荐恢复动作的映射。"""

    def __init__(self) -> None:
        """初始化 ErrorHandler。"""
        logger.debug("ErrorHandler 初始化完成")

    def classify(self, exc: Exception) -> tuple[str, str]:
        """
        分类异常并返回恢复建议。

        参数
        ----------
        exc : Exception
            待分类的异常对象。

        返回
        -------
        tuple[str, str]
            (异常分类名称, 推荐恢复动作)。
            分类名称: connection / perception / llm / execution / loop / timeout / unknown。
            恢复动作: reconnect / switch_capture / retry_backoff / switch_location / abort / wait_or_abort / report。
        """
        category: str = "unknown"
        for exc_type, cat in self.ERROR_MAP.items():
            if isinstance(exc, exc_type):
                category = cat
                break

        recovery: str = self.RECOVERY_ACTIONS.get(category, "report")
        logger.info("异常分类: category=%s, recovery=%s, exc_type=%s",
                     category, recovery, type(exc).__name__)
        return category, recovery

    def handle(self, exc: Exception, category: str, recovery: str) -> Optional[bool]:
        """
        根据异常分类和恢复动作执行处理。

        参数
        ----------
        exc : Exception
            原始异常对象。
        category : str
            异常分类名称。
        recovery : str
            推荐恢复动作。

        返回
        -------
        Optional[bool]
            True 表示已自动恢复，False 表示需要调用方处理，None 表示无法自动处理。
        """
        logger.warning("ErrorHandler 处理异常: category=%s, recovery=%s, error=%s",
                       category, recovery, exc)

        if recovery == "reconnect":
            return self._handle_reconnect(exc)
        elif recovery == "switch_capture":
            return self._handle_switch_capture(exc)
        elif recovery == "retry_backoff":
            return self._handle_retry_backoff(exc)
        elif recovery == "switch_location":
            return self._handle_switch_location(exc)
        elif recovery == "abort":
            return self._handle_abort(exc)
        elif recovery == "wait_or_abort":
            return self._handle_wait_or_abort(exc)
        else:
            logger.error("未知的恢复动作: %s", recovery)
            return None

    def _handle_reconnect(self, exc: Exception) -> bool:
        """
        处理设备重连。

        参数
        ----------
        exc : Exception
            设备连接异常。

        返回
        -------
        bool
            重连是否成功。
        """
        logger.info("执行设备重连: %s", exc)
        return False

    def _handle_switch_capture(self, exc: Exception) -> bool:
        """
        处理截图方式切换。

        参数
        ----------
        exc : Exception
            感知异常。

        返回
        -------
        bool
            切换是否成功。
        """
        logger.info("执行截图方式切换（u2 -> ADB）: %s", exc)
        return False

    def _handle_retry_backoff(self, exc: Exception) -> bool:
        """
        处理 LLM 调用重试（指数退避）。

        参数
        ----------
        exc : Exception
            LLM 服务异常。

        返回
        -------
        bool
            是否启动重试流程。
        """
        logger.info("执行 LLM 指数退避重试: %s", exc)
        return True

    def _handle_switch_location(self, exc: Exception) -> bool:
        """
        处理定位方式切换。

        参数
        ----------
        exc : Exception
            执行异常。

        返回
        -------
        bool
            是否启动切换流程。
        """
        logger.info("执行定位切换（resource-id -> 坐标）: %s", exc)
        return True

    def _handle_abort(self, exc: Exception) -> bool:
        """
        处理任务终止。

        参数
        ----------
        exc : Exception
            死循环检测异常。

        返回
        -------
        bool
            始终返回 False 表示任务已中止。
        """
        logger.error("执行任务终止: %s", exc)
        return False

    def _handle_wait_or_abort(self, exc: Exception) -> bool:
        """
        处理超时等待或终止。

        参数
        ----------
        exc : Exception
            超时异常。

        返回
        -------
        bool
            True 表示继续等待，False 表示终止。
        """
        logger.warning("执行超时处理: %s", exc)
        return True

    @staticmethod
    def wrap_error(func: callable) -> callable:
        """
        装饰器：将被装饰函数抛出的异常包装为框架自定义异常。

        使用方式
        --------
        >>> @ErrorHandler.wrap_error
        ... def risky_operation():
        ...     raise ConnectionError("设备离线")
        """
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except MobileAutomationError:
                raise
            except TimeoutError as exc:
                raise TimeoutError(str(exc)) from exc
            except ConnectionError as exc:
                raise DeviceConnectionError(str(exc)) from exc
            except Exception as exc:
                raise MobileAutomationError(str(exc)) from exc
        return wrapper

    @staticmethod
    def safe_call(func: callable, default_return: Any = None, log_level: str = "error") -> Any:
        """
        安全调用函数：捕获所有异常并记录日志，返回默认值。

        使用方式
        --------
        >>> result = ErrorHandler.safe_call(risky_func, default_return=False)
        >>> result = ErrorHandler.safe_call(risky_func, log_level="warning")

        参数
        ----------
        func : callable
            待安全调用的函数。
        default_return : Any
            异常时的默认返回值。
        log_level : str
            日志级别，可选 "error" / "warning" / "info" / "debug"。

        返回
        -------
        Any
            函数正常执行的结果，或异常时的 default_return。
        """
        try:
            return func()
        except Exception as exc:
            log_method = getattr(logger, log_level, logger.error)
            log_method("安全调用异常: func=%s, error=%s", getattr(func, "__name__", "unknown"), exc)
            return default_return
