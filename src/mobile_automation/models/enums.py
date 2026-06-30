"""
核心枚举类型定义。

框架中所有业务枚举集中在此模块，包括操作类型、步骤状态、
任务状态、弹窗类型与策略、LLM 提供商及消息角色。
"""

from enum import Enum

from ..logger import get_logger

logger = get_logger(__name__)


class ActionType(str, Enum):
    """
    操作类型枚举。

    定义了系统支持的所有操作指令类型，涵盖点击、输入、滑动、
    系统按键、应用管理和等待等类别。

    使用示例
    --------
    >>> ActionType.CLICK
    <ActionType.CLICK: 'click'>
    >>> ActionType.CLICK.value
    'click'
    """
    CLICK = "click"
    """单击元素"""
    DOUBLE_CLICK = "double_click"
    """双击元素"""
    LONG_CLICK = "long_click"
    """长按元素"""
    TYPE = "type"
    """向输入框填入文本"""
    CLEAR_TEXT = "clear_text"
    """清空输入框内容"""
    SWIPE = "swipe"
    """沿指定方向滑动"""
    SWIPE_POINT = "swipe_point"
    """沿指定坐标轨迹滑动"""
    SCROLL = "scroll"
    """滚动操作（上 / 下 / 左 / 右）"""
    BACK = "back"
    """系统返回键"""
    HOME = "home"
    """回到桌面"""
    RECENT_APPS = "recent_apps"
    """打开最近任务列表"""
    WAIT = "wait"
    """等待页面稳定"""
    SCREENSHOT = "screenshot"
    """截图并返回"""
    OPEN_APP = "open_app"
    """打开指定应用"""
    CLOSE_APP = "close_app"
    """关闭指定应用"""
    TERMINATE = "terminate"
    """终止当前任务"""
    VERIFY = "verify"
    """验证判断操作，不会实际操作设备，仅用于向系统返回验证结论（params.match 表示是否匹配）"""


class StepStatus(str, Enum):
    """
    单步执行状态枚举。

    描述一步操作从创建到完成的完整生命周期状态。
    """
    PENDING = "pending"
    """等待执行"""
    RUNNING = "running"
    """正在执行"""
    SUCCESS = "success"
    """执行成功"""
    FAILED = "failed"
    """执行失败"""
    SKIPPED = "skipped"
    """已跳过"""
    RETRYING = "retrying"
    """正在重试"""
    ABORTED = "aborted"
    """被终止"""


class TaskStatus(str, Enum):
    """
    任务整体状态枚举。

    描述一个自动化任务最终的完成情况。
    """
    RUNNING = "running"
    """任务正在运行"""
    COMPLETED = "completed"
    """任务全部完成"""
    FAILED = "failed"
    """任务失败"""
    PARTIALLY_COMPLETED = "partially_completed"
    """任务部分完成"""
    ABORTED = "aborted"
    """任务被终止"""


class PopupType(str, Enum):
    """
    弹窗类型枚举。

    用于分类识别屏幕上出现的各类弹窗，以便采取针对性的处理策略。
    """
    PERMISSION_DIALOG = "permission_dialog"
    """系统权限请求弹窗"""
    UPDATE_DIALOG = "update_dialog"
    """应用更新提示弹窗"""
    AD_POPUP = "ad_popup"
    """广告弹窗"""
    RATING_DIALOG = "rating_dialog"
    """评分邀请弹窗"""
    AGREEMENT_DIALOG = "agreement_dialog"
    """用户协议 / 隐私政策弹窗"""
    SYSTEM_ALERT = "system_alert"
    """系统级警告弹窗"""
    UNKNOWN = "unknown"
    """无法识别的弹窗类型"""


class PopupStrategy(str, Enum):
    """
    弹窗处理策略枚举。

    定义对各种弹窗可采取的处理动作。
    """
    ALLOW = "allow"
    """点击「允许」或「同意」"""
    DENY = "deny"
    """点击「拒绝」或「禁止」"""
    DISMISS = "dismiss"
    """关闭弹窗（点 X 或返回键）"""
    CANCEL = "cancel"
    """点击「取消」或「稍后」"""
    REPORT_TO_LLM = "report_to_llm"
    """上报给 LLM 决策处理方式"""
    UNKNOWN = "unknown"
    """暂不处理"""


class LLMProvider(str, Enum):
    """
    LLM 提供商枚举。

    框架目前支持的四种大语言模型服务商。
    """
    QWEN = "qwen"
    """阿里云通义千问（DashScope 兼容接口）"""
    OPENAI = "openai"
    """OpenAI GPT 系列模型"""
    ANTHROPIC = "anthropic"
    """Anthropic Claude 系列模型"""
    ZHIPU = "zhipu"
    """智谱开放平台 GLM 系列模型"""


class LLMRole(str, Enum):
    """
    LLM 消息角色枚举。

    对应 OpenAI / Anthropic / Qwen 等多模型通用的消息角色体系。
    """
    SYSTEM = "system"
    """系统级指令消息"""
    USER = "user"
    """用户输入消息"""
    ASSISTANT = "assistant"
    """模型回复消息"""


logger.debug("枚举模块加载完成，共定义 %d 个枚举类", 7)
