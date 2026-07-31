"""
Prompt 模板包。

定义与 LLM 交互所用的各类提示词模板，包括系统指令、步骤决策模板
和历史摘要压缩模板。所有 prompt 在此包中集中管理，便于维护和调优。
"""

from .system_prompt import SYSTEM_PROMPT
from .decision_prompt import DecisionPromptBuilder
from .summary_prompt import SUMMARY_PROMPT

__all__ = [
    "SYSTEM_PROMPT",
    "DecisionPromptBuilder",
    "SUMMARY_PROMPT",
]
