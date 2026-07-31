"""
LLM 服务层包。

提供统一的 LLM 调用抽象层（Adapter 模式），支持多 LLM 提供商切换。
包含以下核心组件：
- base: LLMMessage 数据类 + LLMAdapter 抽象基类
- qwen_adapter: 通义千问 Qwen-VL（DashScope 兼容接口）适配器
- openai_adapter: OpenAI GPT-4o 适配器
- claude_adapter: Anthropic Claude 适配器
- zhipu_adapter: 智谱 GLM-4V 适配器
- llm_service: LLMServiceFactory 工厂 + LLMService 统一入口
- message_builder: 多模态消息组装器
- token_budget: Token 预算计算与动态压缩策略管理
"""

from .base import LLMAdapter, LLMMessage
from .qwen_adapter import QwenAdapter
from .openai_adapter import OpenAIAdapter
from .claude_adapter import ClaudeAdapter
from .zhipu_adapter import ZhipuAdapter
from .llm_service import LLMServiceFactory, LLMService
from .message_builder import MessageBuilder
from .token_budget import TokenBudgetManager

__all__ = [
    "LLMAdapter",
    "LLMMessage",
    "QwenAdapter",
    "OpenAIAdapter",
    "ClaudeAdapter",
    "ZhipuAdapter",
    "LLMServiceFactory",
    "LLMService",
    "MessageBuilder",
    "TokenBudgetManager",
]
