"""
统一配置管理模块（pydantic-settings）。

采用 pydantic-settings 实现按模块分组的类型安全配置体系。
支持 .env 文件、环境变量两种注入方式，嵌套配置项通过 "__" 分隔。

多模型配置说明：
- 所有供应商平级配置在 settings.models.providers 字典中
- 每个供应商独立配置 api_key、base_url、model_name 等
- 多模态/纯文本能力由 model_registry 定义，不在配置中重复
- 通过 default_multimodal_provider / default_text_provider 指定默认供应商

全局单例用法：
    >>> from src.mobile_automation.config import settings
    >>> settings.models.providers["qwen"].api_key
    >>> settings.models.providers["deepseek"].model_name
"""

from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProviderConfig(BaseSettings):
    """单个供应商的连接配置（API Key、Base URL 等共享配置）。"""
    api_key: str = Field(default="", description="API 密钥")
    base_url: str = Field(default="", description="API 请求基础地址")
    timeout: int = Field(default=60, description="请求超时时间（秒）")


class ModelEntry(BaseSettings):
    """
    单个模型的完整定义。

    每个模型属于一个供应商，具有独立的能力标签（多模态/纯文本）。
    同一供应商可注册多个模型（如 Qwen 的 qwen3.6-flash 和 qwen3.7-plus）。
    """
    provider: str = Field(default="", description="所属供应商名称: qwen / zhipu / deepseek / longcat")
    model_name: str = Field(default="", description="API 调用时使用的模型名称")
    model_type: str = Field(
        default="multimodal",
        description="模型类型: multimodal（文本+视觉）或 text（纯文本）",
    )
    context_window: int = Field(default=32000, description="模型上下文窗口大小（Token）")
    max_tokens: int = Field(default=4096, description="单次请求最大输出 Token 数")
    temperature: float = Field(default=0.1, ge=0, le=2, description="生成温度")

    @property
    def is_multimodal(self) -> bool:
        """是否为多模态模型（支持视觉理解）。"""
        return self.model_type == "multimodal"

    @property
    def is_text_only(self) -> bool:
        """是否为纯文本模型。"""
        return self.model_type == "text"


class ModelSettings(BaseSettings):
    """
    多模型配置根节点。

    架构说明：
    - providers: 供应商共享配置（API Key、Base URL），按供应商名索引
    - models: 模型注册表，按 model_key 索引，每个模型关联一个供应商
    - default_multimodal / default_text: 指定默认使用的模型 key

    环境变量命名规则（使用 "__" 分隔）：
      MODELS__PROVIDERS__QWEN__API_KEY=sk-xxx
      MODELS__MODELS__QWEN_FLASH__MODEL_NAME=qwen3.6-flash
      MODELS__MODELS__QWEN_FLASH__MODEL_TYPE=multimodal
      MODELS__DEFAULT_MULTIMODAL=qwen-flash
    """
    providers: dict[str, ProviderConfig] = Field(
        default_factory=lambda: {
            "qwen": ProviderConfig(
                api_key="",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            ),
            "zhipu": ProviderConfig(
                api_key="",
                base_url="https://open.bigmodel.cn/api/paas/v4/",
            ),
            "deepseek": ProviderConfig(
                api_key="",
                base_url="https://api.deepseek.com/v1",
            ),
            "longcat": ProviderConfig(
                api_key="",
                base_url="https://api.longcat.chat/v1",
            ),
            "mimo": ProviderConfig(
                api_key="",
                base_url="https://api.xiaomimimo.com/v1",
            ),
        },
        description="所有模型供应商的共享配置字典（API Key、Base URL）",
    )
    models: dict[str, ModelEntry] = Field(
        default_factory=lambda: {
            # ---- MiMo 多模态模型（小米） ----
            "mimo-omni": ModelEntry(
                provider="mimo",
                model_name="mimo-v2.5",
                model_type="multimodal",
                context_window=128000,
            ),
            "mimo-pro": ModelEntry(
                provider="mimo",
                model_name="mimo-v2.5-pro",
                model_type="text",
                context_window=1000000,
            ),
            # ---- Qwen 多模态模型 ----
            "qwen-flash": ModelEntry(
                provider="qwen",
                model_name="qwen3.6-flash",
                model_type="multimodal",
                context_window=32000,
            ),
            "qwen-plus": ModelEntry(
                provider="qwen",
                model_name="qwen3.7-plus",
                model_type="multimodal",
                context_window=32000,
            ),
            # ---- Zhipu 多模态模型 ----
            "zhipu-flash": ModelEntry(
                provider="zhipu",
                model_name="glm-4.1v-thinking-flash",
                model_type="multimodal",
                context_window=128000,
            ),
            "zhipu-flashx": ModelEntry(
                provider="zhipu",
                model_name="glm-4.6v-flashx",
                model_type="multimodal",
                context_window=128000,
            ),
            # ---- DeepSeek 纯文本模型 ----
            "deepseek-flash": ModelEntry(
                provider="deepseek",
                model_name="deepseek-v4-flash",
                model_type="text",
                context_window=128000,
            ),
            # ---- LongCat 纯文本模型 ----
            "longcat-flash": ModelEntry(
                provider="longcat",
                model_name="LongCat-2.0",
                model_type="text",
                context_window=128000,
            ),
        },
        description="模型注册表: model_key → ModelEntry（provider + model_name + 能力标签）",
    )
    default_multimodal: str = Field(
        default="mimo-omni",
        description="默认多模态模型 key（需视觉理解的任务）",
    )
    default_text: str = Field(
        default="deepseek-flash",
        description="默认纯文本模型 key（无需视觉的任务）",
    )

    # ---- 便捷查询方法 ----

    def get_model(self, model_key: str) -> Optional[ModelEntry]:
        """根据 model_key 获取模型定义。"""
        return self.models.get(model_key)

    def get_provider_config(self, provider_name: str) -> Optional[ProviderConfig]:
        """根据供应商名称获取共享配置。"""
        return self.providers.get(provider_name)

    def resolve_api_key(self, model_key: str) -> str:
        """
        根据 model_key 解析 API Key。

        优先级：models[model_key] 对应 provider 的 api_key > LLM 全局 api_key。
        """
        entry = self.get_model(model_key)
        if entry:
            provider_cfg = self.get_provider_config(entry.provider)
            if provider_cfg and provider_cfg.api_key:
                return provider_cfg.api_key
        return ""

    def list_multimodal_models(self) -> list[str]:
        """列出所有多模态模型的 key。"""
        return [k for k, v in self.models.items() if v.is_multimodal]

    def list_text_models(self) -> list[str]:
        """列出所有纯文本模型的 key。"""
        return [k for k, v in self.models.items() if v.is_text_only]


# ---- 保留向后兼容的 LLMSettings ----

class LLMSettings(BaseSettings):
    """
    LLM 提供商相关配置（向后兼容）。

    新版本推荐使用 settings.models.providers 访问多模型配置。
    本字段保留用于兼容旧代码。
    """
    provider: str = Field(default="zhipu", description="默认 LLM 提供商名称")
    api_key: str = Field(default="", description="API 密钥")
    base_url: str = Field(
        default="https://open.bigmodel.cn/api/paas/v4/",
        description="API 请求基础地址",
    )
    model_name: str = Field(default="glm-4.1v-thinking-flash", description="默认模型名称")
    max_tokens: int = Field(default=4096, description="每次 LLM 请求的最大输出 Token 数")
    temperature: float = Field(default=0.1, ge=0, le=2, description="生成温度")
    top_p: float = Field(default=0.9, ge=0, le=1, description="核采样参数")
    request_timeout: int = Field(default=60, description="LLM API 请求超时时间（秒）")
    max_retries: int = Field(default=3, description="LLM API 调用最大重试次数")
    context_window: int = Field(default=32000, description="模型上下文窗口大小")


class DeviceSettings(BaseSettings):
    """移动端设备连接相关配置。"""
    serial: str = Field(default="", description="设备序列号，为空时自动选择首个在线设备")
    host: str = Field(default="127.0.0.1", description="ADB 服务主机地址")
    port: int = Field(default=5555, description="ADB 服务端口号")
    connect_retries: int = Field(default=3, description="设备连接失败后的最大重试次数")
    adb_path: str = Field(default="adb", description="ADB 可执行文件路径")
    u2_init_on_start: bool = Field(default=True, description="框架启动时是否自动初始化 uiautomator2 会话")
    default_screen_width: int = Field(default=1080, description="无法获取设备屏幕时的默认宽度（像素）")
    default_screen_height: int = Field(default=1920, description="无法获取设备屏幕时的默认高度（像素）")


class ExecutionSettings(BaseSettings):
    """任务执行流程相关配置。"""
    max_steps_per_task: int = Field(default=30, description="单个任务允许执行的最大步数")
    max_retries_per_step: int = Field(default=3, description="单步操作失败后的最大重试次数")
    max_total_duration_seconds: int = Field(default=300, description="单个任务允许的最大耗时（秒）")
    retry_interval_ms: int = Field(default=2000, description="重试间隔时间（毫秒）")
    screenshot_max_size: int = Field(default=720, description="截图缩放后的最长边像素值")
    screenshot_quality: int = Field(default=85, ge=1, le=100, description="截图 JPEG 压缩质量")
    page_stable_wait_ms: int = Field(default=5000, description="等待页面稳定的最大超时时间（毫秒）")
    page_stable_poll_ms: int = Field(default=500, description="页面稳定检测的轮询间隔（毫秒）")


class PerceptionSettings(BaseSettings):
    """屏幕感知相关配置。"""
    ssim_threshold_stable: float = Field(default=0.98, ge=0, le=1, description="SSIM 页面稳定判断阈值")
    ui_tree_max_flattened_nodes: int = Field(default=150, description="UI 树展平后的最大节点数")
    spatial_grid_size: int = Field(default=100, description="空间索引的网格像素大小")
    page_stable_structural_threshold: float = Field(default=0.05, ge=0, le=1, description="页面稳定检测的结构差异阈值")


class PopupSettings(BaseSettings):
    """弹窗检测与处理相关配置。"""
    enabled: bool = Field(default=True, description="是否启用弹窗自动检测与处理功能")
    permission_auto_allow: bool = Field(default=True, description="权限请求弹窗是否自动点击「允许」")
    ad_popup_auto_close: bool = Field(default=True, description="广告弹窗是否自动关闭")
    unknown_popup_report_to_llm: bool = Field(default=True, description="未知类型弹窗是否上报 LLM 决策")


class LoopDetectionSettings(BaseSettings):
    """死循环检测相关配置。"""
    max_same_actions: int = Field(default=3, description="连续相同操作的次数阈值")
    ssim_threshold: float = Field(default=0.95, ge=0, le=1, description="页面相似度 SSIM 阈值")
    max_history_size: int = Field(default=50, description="历史操作记录的最大留存条数")


class CoordinateTuningSettings(BaseSettings):
    """坐标微调相关配置。"""
    offset_x: int = Field(default=0, description="X 轴方向偏移量（像素）")
    offset_y: int = Field(default=0, description="Y 轴方向偏移量（像素）")
    enable_tuning: bool = Field(default=False, description="是否启用坐标微调功能")


class LoggerSettings(BaseSettings):
    """日志系统相关配置。"""
    log_dir: str = Field(default="logs", description="日志文件输出目录")
    log_level: str = Field(default="DEBUG", description="日志级别")
    log_rotation_mb: int = Field(default=10, description="单个日志文件的大小上限（MB）")
    log_retention_days: int = Field(default=7, description="日志文件保留天数")
    save_screenshots: bool = Field(default=True, description="是否保存操作过程中的截图证据链")


class Settings(BaseSettings):
    """
    全局配置根对象。

    所有子配置组作为嵌套字段挂载在根对象下，通过 .env 文件或环境变量注入。
    环境变量使用 "__" 作为嵌套分隔符，例如 "MODELS__PROVIDERS__QWEN__API_KEY".
    """
    models: ModelSettings = Field(default_factory=ModelSettings, description="多模型配置根节点")
    llm: LLMSettings = Field(default_factory=LLMSettings, description="LLM 配置组（向后兼容）")
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
