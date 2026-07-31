"""
弹窗处理包 —— 检测并处理移动端各类弹窗干扰。

以 UI 树节点匹配为主要检测手段，图像分类为辅助。
预置规则库处理已知弹窗类型（权限、更新、广告、协议等），
未知弹窗上报 LLM 决策处理方式。
"""

from .classifier import PopupClassifier
from .models import PopupDetectResult, PopupRule
from .pattern_rules import PatternRules
from .popup_handler import PopupHandler

__all__ = [
    "PopupHandler",
    "PopupDetectResult",
    "PopupRule",
    "PatternRules",
    "PopupClassifier",
]
