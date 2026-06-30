"""数据归档器 —— DataArchiver。

为每次自动化任务的每一步，将截图、原始 XML、结构化摘要、LLM 请求消息
和 LLM 响应文本归档到本地文件系统。归档目录结构：

  reports/yy_mm_dd_hh_mm_ss/<task_id>/
    ├── task_meta.json              # 任务级元数据
    ├── step_01/
    │   ├── screenshot.png           # 操作前截图
    │   ├── screenshot_after.png     # 操作后截图
    │   ├── xml_raw.xml              # 原始 UI 树 XML
    │   ├── summary.txt              # 结构化摘要
    │   ├── llm_request.json         # 发送给 LLM 的消息
    │   └── llm_response.json        # LLM 返回的响应
    ├── step_02/
    │   └── ...
    └── report.md                   # 最终生成的流程化报告
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..logger import get_logger, _timestamp_dir

logger = get_logger(__name__)


@dataclass
class StepArchiveData:
    """
    单个步骤的归档数据容器。

    归档器在执行过程中收集这些数据，最终由 ReportGenerator 读取生成报告。

    参数
    ----------
    step_index : int
        步骤序号。
    step_dir : Path
        本步骤的归档目录路径。
    screenshot_path : Path
        操作前截图文件路径。
    screenshot_after_path : Optional[Path]
        操作后截图文件路径。
    xml_path : Path
        原始 XML dump 文件路径。
    summary_path : Path
        结构化摘要文件路径。
    llm_request_path : Optional[Path]
        LLM 请求消息文件路径。
    llm_response_path : Optional[Path]
        LLM 响应文件路径。
    action_type : str
        执行的操作类型。
    action_detail : str
        操作详情描述。
    status : str
        步骤状态。
    error_message : str
        错误信息（如果有）。
    reason : str
        LLM 给出的操作理由。
    """
    step_index: int
    step_dir: Path
    screenshot_path: Path
    screenshot_after_path: Optional[Path] = None
    xml_path: Optional[Path] = None
    summary_path: Optional[Path] = None
    llm_request_path: Optional[Path] = None
    llm_response_path: Optional[Path] = None
    action_type: str = ""
    action_detail: str = ""
    status: str = ""
    error_message: str = ""
    reason: str = ""


class DataArchiver:
    """
    数据归档器。

    将自动化任务每一步产生的原始数据保存到本地文件系统，
    为 ReportGenerator 提供数据基础。

    归档目录结构：
        reports/yy_mm_dd_hh_mm_ss/<task_id>/
        ├── task_meta.json
        ├── step_01/
        │   ├── screenshot.png
        │   ├── screenshot_after.png
        │   ├── xml_raw.xml
        │   ├── summary.txt
        │   ├── llm_request.json
        │   └── llm_response.json
        ├── step_02/
        └── ...

    参数
    ----------
    task_id : str
        任务唯一标识符。
    report_dir : str
        报告输出根目录，默认为 "reports"。实际写入的子目录为
        report_dir/yy_mm_dd_hh_mm_ss/<task_id>/。
    """

    def __init__(
        self,
        task_id: str,
        report_dir: str = "reports",
    ) -> None:
        self._task_id: str = task_id
        # 在 report_dir 下增加时间戳子目录
        timestamped = _timestamp_dir(report_dir)
        self._base_dir: Path = timestamped / task_id
        self._step_archives: list[StepArchiveData] = []
        self._task_start_time: float = 0.0

        try:
            self._base_dir.mkdir(parents=True, exist_ok=True)
            logger.info("归档目录创建完成: %s", self._base_dir)
        except OSError as exc:
            logger.error("归档目录创建失败: %s", exc)
            raise

    @property
    def base_dir(self) -> Path:
        """返回归档根目录。"""
        return self._base_dir

    @property
    def step_archives(self) -> list[StepArchiveData]:
        """返回所有步骤的归档数据列表。"""
        return list(self._step_archives)

    def save_task_meta(self, meta: dict[str, Any]) -> None:
        """
        保存任务级元数据到 task_meta.json。

        参数
        ----------
        meta : dict
            包含任务目标、状态、总步数等信息的字典。
        """
        meta_path = self._base_dir / "task_meta.json"
        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2, default=str)
            logger.debug("任务元数据已保存: %s", meta_path)
        except OSError as exc:
            logger.error("任务元数据保存失败: %s", exc)

    def _get_step_dir(self, step_index: int) -> Path:
        """获取指定步骤的归档子目录。"""
        step_dir = self._base_dir / f"step_{step_index:02d}"
        step_dir.mkdir(parents=True, exist_ok=True)
        return step_dir

    def save_screenshot(
        self,
        step_index: int,
        image_bytes: bytes,
        after: bool = False,
    ) -> Path:
        """
        保存步骤截图到归档目录。

        参数
        ----------
        step_index : int
            步骤序号。
        image_bytes : bytes
            截图图片的字节数据（PNG 或 JPEG）。
        after : bool
            是否为操作后的截图。False 表示操作前快照。

        返回
        -------
        Path
            截图文件的完整路径。
        """
        step_dir = self._get_step_dir(step_index)
        filename = "screenshot_after.png" if after else "screenshot.png"
        filepath = step_dir / filename

        try:
            with open(filepath, "wb") as f:
                f.write(image_bytes)
            logger.debug("截图已保存: %s (%d 字节)", filepath, len(image_bytes))
        except OSError as exc:
            logger.error("截图保存失败: %s", exc)

        return filepath

    def save_raw_xml(self, step_index: int, xml_str: str) -> Path:
        """
        保存原始 UI 树 XML 到归档目录。

        参数
        ----------
        step_index : int
            步骤序号。
        xml_str : str
            uiautomator2 导出的原始 XML 字符串。

        返回
        -------
        Path
            XML 文件的完整路径。
        """
        step_dir = self._get_step_dir(step_index)
        filepath = step_dir / "xml_raw.xml"

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(xml_str)
            logger.debug("原始 XML 已保存: %s (%d 字符)", filepath, len(xml_str))
        except OSError as exc:
            logger.error("XML 保存失败: %s", exc)

        return filepath

    def save_structured_summary(self, step_index: int, summary: str) -> Path:
        """
        保存结构化摘要文本到归档目录。

        参数
        ----------
        step_index : int
            步骤序号。
        summary : str
            UI 树的结构化摘要文本。

        返回
        -------
        Path
            摘要文件的完整路径。
        """
        step_dir = self._get_step_dir(step_index)
        filepath = step_dir / "summary.txt"

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(summary)
            logger.debug("结构化摘要已保存: %s (%d 字符)", filepath, len(summary))
        except OSError as exc:
            logger.error("摘要保存失败: %s", exc)

        return filepath

    def save_llm_request(self, step_index: int, messages: list[dict], attempt: int = 1) -> Path:
        """
        保存 LLM 请求消息到归档目录。

        参数
        ----------
        step_index : int
            步骤序号。
        messages : list[dict]
            发送给 LLM 的消息列表。
        attempt : int
            本步骤的第几次尝试，用于区分同一步骤的多次 LLM 调用。

        返回
        -------
        Path
            请求消息文件的完整路径。
        """
        step_dir = self._get_step_dir(step_index)
        filename = "llm_request.json" if attempt <= 1 else f"llm_request_attempt_{attempt}.json"
        filepath = step_dir / filename

        sanitized = self._sanitize_for_json(messages)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(sanitized, f, ensure_ascii=False, indent=2, default=str)
            logger.debug("LLM 请求已保存: %s", filepath)
        except OSError as exc:
            logger.error("LLM 请求保存失败: %s", exc)

        return filepath

    def save_llm_response(self, step_index: int, response: str, attempt: int = 1) -> Path:
        """
        保存 LLM 响应文本到归档目录。

        参数
        ----------
        step_index : int
            步骤序号。
        response : str
            LLM 返回的原始响应文本。
        attempt : int
            本步骤的第几次尝试，用于区分同一步骤的多次 LLM 调用。

        返回
        -------
        Path
            响应文件的完整路径。
        """
        step_dir = self._get_step_dir(step_index)
        filename = "llm_response.json" if attempt <= 1 else f"llm_response_attempt_{attempt}.json"
        filepath = step_dir / filename

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump({"response": response}, f, ensure_ascii=False, indent=2)
            logger.debug("LLM 响应已保存: %s", filepath)
        except OSError as exc:
            logger.error("LLM 响应保存失败: %s", exc)

        return filepath

    def register_step_archive(self, archive: StepArchiveData) -> None:
        """
        注册一个步骤的归档数据。

        由 StepRunner 或 Orchestrator 在步骤完成后调用。

        参数
        ----------
        archive : StepArchiveData
            步骤归档数据。
        """
        self._step_archives.append(archive)
        logger.debug("步骤 %d 归档数据已注册", archive.step_index)

    def get_report_path(self) -> Path:
        """获取最终报告文件的路径。"""
        return self._base_dir / "report.md"

    @staticmethod
    def _sanitize_for_json(messages: Any) -> Any:
        """
        清洗消息数据，确保可 JSON 序列化。

        主要处理：将 Base64 图片数据替换为占位描述，避免 JSON 文件过大。

        参数
        ----------
        messages : Any
            待清洗的消息数据。

        返回
        -------
        Any
            清洗后的 JSON 安全数据。
        """
        if isinstance(messages, list):
            return [DataArchiver._sanitize_for_json(item) for item in messages]
        if isinstance(messages, dict):
            sanitized = {}
            for key, value in messages.items():
                if key == "image_url" and isinstance(value, dict):
                    url = value.get("url", "")
                    if url and len(url) > 200:
                        sanitized[key] = {"url": f"[BASE64 图片，长度 {len(url)} 字符]"}
                    else:
                        sanitized[key] = value
                elif key == "content" and isinstance(value, list):
                    sanitized[key] = DataArchiver._sanitize_for_json(value)
                else:
                    sanitized[key] = DataArchiver._sanitize_for_json(value)
            return sanitized
        return messages
