"""
自定义异常类型定义。

按照异常分类（连接、感知、LLM、执行、死循环、超时）定义
层次化的自定义异常类，所有异常均继承自 MobileAutomationError。
"""

from ..logger import get_logger

logger = get_logger(__name__)


class MobileAutomationError(Exception):
    """
    框架基础异常。

    所有框架自定义异常的基类，便于上层统一捕获。

    参数
    ----------
    message : str
        异常描述信息。
    """
    def __init__(self, message: str = "移动自动化框架异常") -> None:
        self.message = message
        super().__init__(self.message)


class DeviceConnectionError(MobileAutomationError):
    """
    设备连接异常。

    在设备离线、ADB 断开、uiautomator2 初始化失败等场景抛出。

    参数
    ----------
    message : str
        异常描述信息。
    serial : str
        发生异常的设备序列号，便于定位问题设备。
    """
    def __init__(self, message: str = "设备连接异常", serial: str = "") -> None:
        self.serial = serial
        detail = f"[设备: {serial}] {message}" if serial else message
        super().__init__(detail)
        logger.error("设备连接异常: %s", detail)


class PerceptionError(MobileAutomationError):
    """
    感知异常。

    在 UI dump 失败、截图获取失败等感知层操作异常时抛出。

    参数
    ----------
    message : str
        异常描述信息。
    """
    def __init__(self, message: str = "感知操作异常") -> None:
        super().__init__(message)
        logger.error("感知异常: %s", message)


class LLMServiceError(MobileAutomationError):
    """
    LLM 服务异常。

    在 LLM API 调用超时、响应格式错误、Token 超限等场景抛出。

    参数
    ----------
    message : str
        异常描述信息。
    provider : str
        发生异常的 LLM 提供商名称。
    """
    def __init__(self, message: str = "LLM 服务异常", provider: str = "") -> None:
        self.provider = provider
        detail = f"[提供商: {provider}] {message}" if provider else message
        super().__init__(detail)
        logger.error("LLM 服务异常: %s", detail)


class ActionExecutionError(MobileAutomationError):
    """
    动作执行异常。

    在元素未找到、点击无响应、参数校验失败等执行层异常时抛出。

    参数
    ----------
    message : str
        异常描述信息。
    """
    def __init__(self, message: str = "动作执行异常") -> None:
        super().__init__(message)
        logger.error("动作执行异常: %s", message)


class LoopDetectedError(MobileAutomationError):
    """
    死循环检测异常。

    当连续相同操作超过配置阈值时由 Orchestrator 抛出，终止当前任务。

    参数
    ----------
    message : str
        异常描述信息。
    """
    def __init__(self, message: str = "检测到死循环，任务已终止") -> None:
        super().__init__(message)
        logger.warning("死循环检测异常: %s", message)


class TimeoutError(MobileAutomationError):
    """
    超时异常。

    在页面加载超时、任务总执行时长超限等场景抛出。

    参数
    ----------
    message : str
        异常描述信息。
    timeout_ms : int
        触发超时的阈值时间（毫秒）。
    """
    def __init__(self, message: str = "操作超时", timeout_ms: int = 0) -> None:
        self.timeout_ms = timeout_ms
        detail = f"[超时: {timeout_ms}ms] {message}" if timeout_ms else message
        super().__init__(detail)
        logger.error("超时异常: %s", detail)
