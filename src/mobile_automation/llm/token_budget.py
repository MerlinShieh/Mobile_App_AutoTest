"""
Token 预算管理器 —— 计算、跟踪 Token 消耗并动态决策压缩策略。

管理每个 LLM 提供商的上下文窗口限制，跟踪累计 Token 消耗，
在接近窗口上限时自动建议压缩策略。支持 Qwen (32K)、
OpenAI (128K)、Anthropic (200K) 和 Zhipu (128K) 四种模型。"""

from typing import Optional

from ..config import settings
from ..logger import get_logger
from .base import LLMMessage

logger = get_logger(__name__)


class TokenBudgetManager:
    """
    Token 预算管理器。

    维护当前任务的 Token 消耗状态，根据模型上下文窗口计算可用预算，
    并在 Token 接近上限时提供压缩策略建议。

    使用方式
    --------
    >>> manager = TokenBudgetManager("qwen")
    >>> manager.needs_compression(current_step_tokens=5000)
    True
    >>> strategy = manager.get_compression_strategy(messages)
    """

    CONTEXT_WINDOWS: dict[str, int] = {
        "qwen": 32000,
        "openai": 128000,
        "anthropic": 200000,
        "zhipu": 128000,
    }
    """各提供商模型的上下文窗口大小映射。"""

    def __init__(self, provider: Optional[str] = None) -> None:
        """
        初始化 TokenBudgetManager。

        根据提供商名称读取对应的上下文窗口大小，并计算输入预算
        （上下文窗口减去输出保留 Token）。优先从 settings.models
        模型配置读取 context_window，保持与 ModelEntry 定义一致；
        未匹配时回退到内置 CONTEXT_WINDOWS 兜底。

        参数
        ----------
        provider : Optional[str]
            LLM 提供商名称，为 None 时从 settings.llm.provider 读取。
        """
        self._provider: str = provider or settings.llm.provider
        self.max_context: int = self._resolve_context_window()
        self.output_reserve: int = settings.llm.max_tokens
        self.input_budget: int = self.max_context - self.output_reserve
        self.total_used: int = 0

        logger.info(
            "TokenBudgetManager 初始化: provider=%s, context=%d, input_budget=%d",
            self._provider, self.max_context, self.input_budget,
        )

    def _resolve_context_window(self) -> int:
        """
        从配置中解析当前提供商的上下文窗口大小。

        优先从 settings.models 模型注册表查找匹配 provider 的
        ModelEntry.context_window，确保与用户配置保持同步。
        未匹配时回退到内置 CONTEXT_WINDOWS 字典，兜底 32000。
        """
        for model_entry in settings.models.models.values():
            if model_entry.provider == self._provider:
                return model_entry.context_window
        return self.CONTEXT_WINDOWS.get(self._provider, 32000)

    def get_available_budget(self) -> int:
        """
        获取当前任务剩余的可用输入 Token 预算。

        返回
        -------
        int
            剩余的可用 Token 数，最小为 0。
        """
        remaining: int = self.input_budget - self.total_used
        available: int = max(0, remaining)
        logger.debug("TokenBudgetManager 可用预算: %d / %d", available, self.input_budget)
        return available

    def record_usage(self, tokens: int) -> None:
        """
        记录本次消耗的 Token 数，累加到已用总量中。

        参数
        ----------
        tokens : int
            本次消耗的 Token 数。
        """
        self.total_used += tokens
        logger.debug("TokenBudgetManager 记录消耗: +%d, 总计=%d", tokens, self.total_used)

    def needs_compression(self, current_step_tokens: int) -> bool:
        """
        判断当前是否需要压缩历史消息以节约 Token。

        当已用 Token + 当前步 Token > 输入预算的 80% 时触发压缩。
        与 get_compression_strategy 使用一致的阈值体系。

        参数
        ----------
        current_step_tokens : int
            当前步骤预计消耗的 Token 数。

        返回
        -------
        bool
            True 表示需要压缩，False 表示预算充足。
        """
        total_needed: int = self.total_used + current_step_tokens
        need: bool = total_needed > self.input_budget * 0.8
        if need:
            logger.warning(
                "TokenBudgetManager 触发压缩: 已用=%d, 当前步=%d, 阈值=%.0f",
                self.total_used, current_step_tokens, self.input_budget * 0.8,
            )
        return need

    @staticmethod
    def _estimate_image_tokens(item: dict) -> int:
        """
        估算单张图片的 Token 消耗数。

        基于 Base64 数据长度估算图片分辨率，采用 OpenAI 高细节公式：
          tokens = ceil(width / 512) * ceil(height / 512) * 170 + 85
        当无法解析 Base64 时回退为固定值 1000。
        """
        image_url = item.get("image_url", {}) if isinstance(item, dict) else {}
        url = image_url.get("url", "") if isinstance(image_url, dict) else ""
        if not isinstance(url, str) or not url.startswith("data:image/"):
            return 1000

        base64_part = url.split(",", 1)[-1] if "," in url else url
        file_bytes = len(base64_part) * 3 // 4
        if file_bytes < 1000:
            return 85

        pixel_est = int(file_bytes * 8 / 2.5)
        side = int(pixel_est ** 0.5)
        tiles_x = max(1, (side + 511) // 512)
        tiles_y = max(1, (side + 511) // 512)
        return tiles_x * tiles_y * 170 + 85

    def estimate_messages_tokens(self, messages: list[LLMMessage]) -> int:
        """
        估算消息列表的总 Token 消耗数。

        文本按字符数的一半估算，图片根据 Base64 数据长度按 OpenAI
        标准公式估算（回退值为 1000）。

        参数
        ----------
        messages : list[LLMMessage]
            待估算的消息列表。

        返回
        -------
        int
            估算的 Token 总数。
        """
        total: int = 0
        for msg in messages:
            if isinstance(msg.content, str):
                total += len(msg.content) // 2
            elif isinstance(msg.content, list):
                for item in msg.content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            total += len(item.get("text", "")) // 2
                        elif item.get("type") == "image_url":
                            total += self._estimate_image_tokens(item)
        return total

    def get_compression_strategy(self, messages: list[LLMMessage]) -> str:
        """
        根据当前 Token 预算返回建议的压缩策略。

        考虑已消耗 Token 与当前步估算之和（累积预算），与 needs_compression
        使用一致的阈值体系：
        - "none": 累积预算 <= 预算的 80%（充足）
        - "compress_history": 累积预算 <= 预算的 150%，压缩历史文本
        - "drop_images": 累积预算 <= 预算的 200%，丢弃历史截图仅保留文本
        - "full_summary": 严重超预算，使用完整摘要压缩

        参数
        ----------
        messages : list[LLMMessage]
            待评估的消息列表。

        返回
        -------
        str
            压缩策略名称: "none" / "compress_history" / "drop_images" / "full_summary"。
        """
        estimated: int = self.estimate_messages_tokens(messages)
        total_needed: int = self.total_used + estimated

        if total_needed <= self.input_budget * 0.8:
            strategy: str = "none"
        elif total_needed <= self.input_budget * 1.5:
            strategy = "compress_history"
        elif total_needed <= self.input_budget * 2.0:
            strategy = "drop_images"
        else:
            strategy = "full_summary"

        logger.info(
            "TokenBudgetManager 压缩策略: %s (已用=%d, 当前步估算=%d, 累积=%d, 预算=%d)",
            strategy, self.total_used, estimated, total_needed, self.input_budget,
        )
        return strategy

    def reset(self) -> None:
        """
        重置 Token 计数器，开始新任务的 Token 追踪。

        通常在 LLMService 或 Orchestrator 开始新任务时调用。
        """
        self.total_used = 0
        logger.info("TokenBudgetManager 已重置 total_used=0")
