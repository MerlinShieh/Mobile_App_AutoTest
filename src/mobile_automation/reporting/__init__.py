"""
数据归档与报告生成模块。

提供 DataArchiver 和 ReportGenerator 两个核心组件，负责将自动化任务的
每一步数据（截图、XML、结构化摘要、LLM 请求/响应）归档到本地文件系统，
并在任务结束后生成一份 HTML 报告文档，便于回放和分析任务执行过程。
"""

from .archiver import DataArchiver, StepArchiveData
from .report_generator import ReportGenerator

__all__ = [
    "DataArchiver",
    "StepArchiveData",
    "ReportGenerator",
]
