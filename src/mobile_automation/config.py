"""
统一配置管理模块（pydantic-settings）。

采用 pydantic-settings 实现按模块分组的类型安全配置体系。
支持 .env 文件、环境变量两种注入方式，嵌套配置项通过 "__" 分隔。

全局单例用法：
    >>> from src.mobile_automation.config import settings
    >>> settings.llm.provider
    'qwen'
    >>> settings.execution.max_steps_per_task
    30
"""

from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """LLM 提供商相关配置。"""
    provider: str = Field(default="qwen", description="LLM 提供商名称: qwen / openai / anthropic")
    api_key: str = Field(default="", description="API 密钥，对应 DashScope / OpenAI / Anthropic")
    base_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        description="API 请求基础地址（Qwen 默认 DashScope 兼容接口）",
    )
    model_name: str = Field(
        default="qwen-vl-max",
        description="模型名称，如 qwen-vl-max / qwen2.5-vl-72b-instruct / gpt-4o / claude-3-5-sonnet",
    )
    max_tokens: int = Field(default=4096, description="每次 LLM 请求的最大输出 Token 数")
    temperature: float = Field(default=0.1, ge=0, le=2, description="生成温度，值越低输出越确定性")
    top_p: float = Field(default=0.9, ge=0, le=1, description="核采样参数，控制候选词的概率累加阈值")
    request_timeout: int = Field(default=60, description="LLM API 请求超时时间（秒）")
    max_retries: int = Field(default=3, description="LLM API 调用最大重试次数")
    context_window: int = Field(default=32000, description="模型上下文窗口大小（Qwen-VL-Max: 32K）")


class DeviceSettings(BaseSettings):
    """移动端设备连接相关配置。"""
    serial: str = Field(default="", description="设备序列号，为空时自动选择首个在线设备")
    host: str = Field(default="127.0.0.1", description="ADB 服务主机地址")
    port: int = Field(default=5555, description="ADB 服务端口号")
    connect_retries: int = Field(default=3, description="设备连接失败后的最大重试次数")
    adb_path: str = Field(default="adb", description="ADB 可执行文件路径，可填绝对路径或仅命令名")
    u2_init_on_start: bool = Field(default=True, description="框架启动时是否自动初始化 uiautomator2 会话")


class ExecutionSettings(BaseSettings):
    """任务执行流程相关配置。"""
    max_steps_per_task: int = Field(default=30, description="单个任务允许执行的最大步数")
    max_retries_per_step: int = Field(default=3, description="单步操作失败后的最大重试次数")
    max_total_duration_seconds: int = Field(default=300, description="单个任务允许的最大耗时（秒）")
    retry_interval_ms: int = Field(default=2000, description="重试间隔时间（毫秒）")
    screenshot_max_size: int = Field(default=720, description="截图缩放后的最长边像素值")
    screenshot_quality: int = Field(default=85, ge=1, le=100, description="截图 JPEG 压缩质量，1~100")
    page_stable_wait_ms: int = Field(default=5000, description="等待页面稳定的最大超时时间（毫秒）")
    page_stable_poll_ms: int = Field(default=500, description="页面稳定检测的轮询间隔（毫秒）")


class PerceptionSettings(BaseSettings):
    """屏幕感知相关配置。"""
    ssim_threshold_stable: float = Field(default=0.98, ge=0, le=1, description="SSIM 页面稳定判断阈值，越接近 1 要求越严格")
    ui_tree_max_flattened_nodes: int = Field(default=150, description="UI 树展平后的最大节点数，超出部分丢弃")
    spatial_grid_size: int = Field(default=100, description="空间索引的网格像素大小")
    page_stable_structural_threshold: float = Field(default=0.05, ge=0, le=1, description="页面稳定检测的结构差异阈值，低于此值视为稳定")


class PopupSettings(BaseSettings):
    """弹窗检测与处理相关配置。"""
    enabled: bool = Field(default=True, description="是否启用弹窗自动检测与处理功能")
    permission_auto_allow: bool = Field(default=True, description="权限请求弹窗是否自动点击「允许」")
    ad_popup_auto_close: bool = Field(default=True, description="广告弹窗是否自动关闭")
    unknown_popup_report_to_llm: bool = Field(default=True, description="未知类型弹窗是否上报 LLM 决策")


class LoopDetectionSettings(BaseSettings):
    """死循环检测相关配置。"""
    max_same_actions: int = Field(default=3, description="连续相同操作的次数阈值，超过则判定为死循环")
    ssim_threshold: float = Field(default=0.95, ge=0, le=1, description="页面相似度 SSIM 阈值")
    max_history_size: int = Field(default=50, description="历史操作记录的最大留存条数")


class CoordinateTuningSettings(BaseSettings):
    """坐标微调相关配置，用于校准各设备间的点击偏移。"""
    offset_x: int = Field(default=0, description="X 轴方向偏移量（像素），正值向右偏移")
    offset_y: int = Field(default=0, description="Y 轴方向偏移量（像素），正值向下偏移")
    enable_tuning: bool = Field(default=False, description="是否启用坐标微调功能")


class LoggerSettings(BaseSettings):
    """日志系统相关配置。"""
    log_dir: str = Field(default="logs", description="日志文件输出目录")
    log_level: str = Field(default="DEBUG", description="日志级别: DEBUG / INFO / WARNING / ERROR / CRITICAL")
    log_rotation_mb: int = Field(default=10, description="单个日志文件的大小上限（MB），超出后自动轮转")
    log_retention_days: int = Field(default=7, description="日志文件保留天数")
    save_screenshots: bool = Field(default=True, description="是否保存操作过程中的截图证据链")


class Settings(BaseSettings):
    """
    全局配置根对象。

    所有子配置组作为嵌套字段挂载在根对象下，通过 .env 文件或环境变量注入。
    环境变量使用 "__" 作为嵌套分隔符，例如 "LLM__API_KEY"。
    """
    llm: LLMSettings = Field(default_factory=LLMSettings, description="LLM 配置组")
    device: DeviceSettings = Field(default_factory=DeviceSettings, description="设备配置组")
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings, description="执行配置组")
    perception: PerceptionSettings = Field(default_factory=PerceptionSettings, description="感知配置组")
    popup: PopupSettings = Field(default_factory=PopupSettings, description="弹窗配置组")
    loop_detection: LoopDetectionSettings = Field(default_factory=LoopDetectionSettings, description="死循环检测配置组")
    coordinate_tuning: CoordinateTuningSettings = Field(default_factory=CoordinateTuningSettings, description="坐标微调配置组")
    logger: LoggerSettings = Field(default_factory=LoggerSettings, description="日志配置组")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )


settings = Settings()
"""全局配置单例，项目内统一通过此对象读取配置。"""


def get_llm_config() -> dict:
    """
    获取 LLM 调用所需的配置字典，供各 Adapter 初始化时使用。

    返回
    -------
    dict
        包含 api_key、base_url、model、max_tokens、temperature、top_p、timeout 的字典。
    """
    return {
        "api_key": settings.llm.api_key,
        "base_url": settings.llm.base_url,
        "model": settings.llm.model_name,
        "max_tokens": settings.llm.max_tokens,
        "temperature": settings.llm.temperature,
        "top_p": settings.llm.top_p,
        "timeout": settings.llm.request_timeout,
    }
