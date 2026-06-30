"""
报告生成器 —— ReportGenerator。

读取 DataArchiver 归档的数据，生成一份流程化的 Markdown 报告文档。
报告以时间线方式展示任务执行的每一步，包含：
  - 任务概览卡片（目标、状态、耗时、步数、Token）
  - 每一步的操作前/后截图对比（嵌入显示）
  - 操作详情（Action 类型、参数、坐标、理由）
  - LLM 决策过程（请求消息摘要 + 响应原文，可折叠）
  - 执行日志（时间线方式展示步骤事件流）
  - 原始数据链接（XML、JSON 等）

每个步骤用 <div class="step-card"> 包裹，确保步骤间平级展示互不干扰。
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..logger import get_logger
from ..models.enums import TaskStatus, StepStatus
from ..models.task import TaskContext
from .archiver import DataArchiver, StepArchiveData

logger = get_logger(__name__)


class ReportGenerator:
    """
    报告生成器。

    读取任务上下文和归档数据，生成一份完整的 Markdown 流程报告。

    参数
    ----------
    task_context : TaskContext
        包含步骤记录和任务状态的任务上下文。
    archiver : DataArchiver
        已完成数据归档的归档器。
    """

    def __init__(
        self,
        task_context: TaskContext,
        archiver: DataArchiver,
    ) -> None:
        self._context: TaskContext = task_context
        self._archiver: DataArchiver = archiver
        self._step_archives: list[StepArchiveData] = archiver.step_archives

    def generate(self) -> Path:
        """
        生成完整的 Markdown 报告文档。

        报告结构：
          1. 任务概览（标题、目标、状态徽章、统计信息）
          2. 每步执行时间线（每个步骤用 div 包裹，平级展示互不干扰）
          3. 报告尾注

        返回
        -------
        Path
            生成的报告文件路径。
        """
        report_path = self._archiver.get_report_path()
        lines: list[str] = []

        lines.append("# 移动端自动化任务报告")
        lines.append("")
        lines.append(self._build_overview())
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## 操作流程时间线")
        lines.append("")

        for i, record in enumerate(self._context.steps):
            step_archive = self._get_step_archive(i + 1)
            lines.append(self._build_step_section(i + 1, record, step_archive))
            # 步骤之间用分隔线明确隔开，确保平级展示
            lines.append("")
            lines.append("<hr>")
            lines.append("")

        lines.append("")
        lines.append(self._build_footer())

        try:
            with open(report_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            logger.info("报告已生成: %s", report_path)
        except OSError as exc:
            logger.error("报告写入失败: %s", exc)

        return report_path

    def _build_overview(self) -> str:
        """构建任务概览段落。包含任务 ID、目标、状态、统计和操作步骤总览。"""
        ctx = self._context
        total = len(ctx.steps)
        success = sum(1 for s in ctx.steps if s.is_success())
        elapsed = (datetime.now() - ctx.created_at).total_seconds()

        status_badge = {
            TaskStatus.COMPLETED: "✅ 已完成",
            TaskStatus.FAILED: "❌ 失败",
            TaskStatus.ABORTED: "⛔ 已中止（检测到操作循环或任务条件满足）",
            TaskStatus.PARTIALLY_COMPLETED: "⚠️ 部分完成",
            TaskStatus.RUNNING: "🔄 运行中",
        }.get(ctx.status, "❓ 未知")

        overview = [
            "## 任务概览",
            "",
            "| 项目 | 值 |",
            "|------|-----|",
            f"| **任务 ID** | `{ctx.task_id}` |",
            f"| **用户目标** | {ctx.user_goal} |",
            f"| **状态** | {status_badge} |",
            f"| **执行步数** | {total} |",
        ]
        if total > 0:
            overview.append(f"| **成功率** | {success / total * 100:.1f}% ({success}/{total}) |")
            overview.append(f"| **耗时** | {elapsed:.1f} 秒 |")
        overview.extend([
            f"| **Token 消耗** | {ctx.total_tokens_used} |",
            f"| **设备** | `{ctx.device_id}` |" if ctx.device_id else "",
            f"| **LLM 提供商** | {ctx.llm_provider} |",
            f"| **创建时间** | {ctx.created_at.strftime('%Y-%m-%d %H:%M:%S')} |",
        ])

        # 步骤总览时间线
        if ctx.steps:
            overview.append("")
            overview.append("**步骤总览：**")
            timeline_parts = []
            for s in ctx.steps:
                icon = "✅" if s.is_success() else "❌"
                timeline_parts.append(f"{icon} Step {s.step_index:02d}")
            overview.append(" → ".join(timeline_parts))

        return "\n".join(filter(None, overview))

    def _build_step_section(
        self,
        step_index: int,
        record,
        step_archive: Optional[StepArchiveData],
    ) -> str:
        """
        构建单步的详细报告段落。

        包含：状态卡片、截图对比、操作详情、LLM 决策（折叠）、执行日志。
        整个步骤用 <div> 包裹，与相邻步骤平级展示互不影响。

        参数
        ----------
        step_index : int
            步骤序号。
        record : StepRecord
            步骤执行记录。
        step_archive : Optional[StepArchiveData]
            步骤归档数据，可为空。

        返回
        -------
        str
            步骤报告 Markdown 文本。
        """
        action = record.action
        duration = record.duration_ms()

        status_icon = "✅" if record.is_success() else "❌" if record.status in (
            StepStatus.FAILED, StepStatus.ABORTED) else "⚠️"

        # -------- 步骤容器开始 --------
        lines: list[str] = [
            "<div class=\"step-card\">",
            "",
            f"### Step {step_index:02d} — {status_icon} {action.action_type.value}",
            "",
            f"> **状态:** {record.status.value}"
            f"{' | 重试: ' + str(record.retry_count) + ' 次' if record.retry_count > 0 else ''}"
            f"{' | 耗时: ' + str(duration) + 'ms' if duration > 0 else ''}",
            "",
        ]

        # 错误信息
        if record.error_message:
            lines.append(f"> ⚠️ **错误:** {record.error_message}")
            lines.append("")

        # ---- 截图对比区域 ----
        if step_archive and step_archive.screenshot_path.exists():
            lines.append("#### 界面截图")
            lines.append("")
            rel_before = self._relative_path(step_archive.screenshot_path)
            if step_archive.screenshot_after_path and step_archive.screenshot_after_path.exists():
                rel_after = self._relative_path(step_archive.screenshot_after_path)
                lines.append("<div align=\"center\">")
                lines.append("")
                lines.append("| 操作前 | 操作后 |")
                lines.append("|--------|--------|")
                lines.append(f"| <img src=\"{rel_before}\" width=\"280\"/> | <img src=\"{rel_after}\" width=\"280\"/> |")
                lines.append("")
                lines.append("</div>")
            else:
                lines.append(f"<img src=\"{rel_before}\" width=\"280\"/>")
            lines.append("")

        # ---- 操作详情区域 ----
        lines.append("#### 操作详情")
        lines.append("")
        lines.append("| 属性 | 值 |")
        lines.append("|------|-----|")
        lines.append(f"| **动作类型** | `{action.action_type.value}` |")

        if action.params.element_id:
            lines.append(f"| **元素 ID** | `{action.params.element_id}` |")
        if action.params.package_name:
            lines.append(f"| **包名** | `{action.params.package_name}` |")
        if action.params.x is not None and action.params.y is not None:
            lines.append(f"| **点击坐标** | ({action.params.x}, {action.params.y}) |")
        if action.params.text:
            lines.append(f"| **输入文本** | `{action.params.text}` |")
        if action.params.direction:
            lines.append(f"| **方向** | `{action.params.direction}` |")
        if action.params.ui_element:
            lines.append(f"| **UI 元素** | `{action.params.ui_element}` |")
        if action.reason:
            lines.append(f"| **LLM 决策理由** | {action.reason} |")
        lines.append("")

        # ---- LLM 决策过程（可折叠） ----
        has_llm = (
            step_archive
            and step_archive.llm_request_path
            and step_archive.llm_request_path.exists()
            and step_archive.llm_response_path
            and step_archive.llm_response_path.exists()
        )
        if has_llm:
            lines.append("")
            lines.append("<details>")
            lines.append("<summary><b>🤖 LLM 决策过程</b>（点击展开/折叠）</summary>")
            lines.append("")
            lines.append("<br>")

            # 请求消息
            lines.append("<p><b>🔼 发送给 LLM 的消息：</b></p>")
            lines.append("")
            try:
                with open(step_archive.llm_request_path, "r", encoding="utf-8") as f:
                    req_data = json.load(f)
                req_text = json.dumps(req_data, ensure_ascii=False, indent=2)
                if len(req_text) > 3000:
                    req_text = req_text[:3000] + "\n  ... (以下内容已截断)"
                lines.append("```json")
                lines.append(req_text)
                lines.append("```")
            except Exception:
                lines.append("*(无法读取请求文件)*")
            lines.append("")

            # 响应消息
            lines.append("<p><b>🔽 LLM 返回的响应：</b></p>")
            lines.append("")
            try:
                with open(step_archive.llm_response_path, "r", encoding="utf-8") as f:
                    resp_data = json.load(f)
                resp_text = resp_data.get("response", "")
                if resp_text:
                    lines.append("```json")
                    lines.append(resp_text if isinstance(resp_text, str) else json.dumps(resp_text, ensure_ascii=False, indent=2))
                    lines.append("```")
                else:
                    lines.append("*(空响应)*")
            except Exception:
                lines.append("*(无法读取响应文件)*")
            lines.append("")

            lines.append("</details>")
            lines.append("")

        # ---- 执行日志区域 ----
        lines.append("#### 执行日志")
        lines.append("")
        lines.append("```log")
        lines.append(f"[Step {step_index:02d}] 操作: {action.action_type.value}")

        if action.params.element_id:
            lines.append(f"[Step {step_index:02d}] 目标元素: {action.params.element_id}")
        if action.params.package_name:
            lines.append(f"[Step {step_index:02d}] 启动应用: {action.params.package_name}")
        if action.params.x is not None and action.params.y is not None:
            lines.append(f"[Step {step_index:02d}] 执行坐标: ({action.params.x}, {action.params.y})")
        if action.reason:
            lines.append(f"[Step {step_index:02d}] LLM 理由: {action.reason}")

        if record.retry_count > 0:
            lines.append(f"[Step {step_index:02d}] 重试次数: {record.retry_count}")
        if record.error_message:
            lines.append(f"[Step {step_index:02d}] 错误: {record.error_message}")

        if duration > 0:
            lines.append(f"[Step {step_index:02d}] 耗时: {duration}ms")
        lines.append(f"[Step {step_index:02d}] 结果: {record.status.value.upper()}")
        lines.append("```")
        lines.append("")

        # ---- 原始数据链接 ----
        if step_archive:
            links = []
            if step_archive.xml_path and step_archive.xml_path.exists():
                links.append(f"[📄 原始 XML]({self._relative_path(step_archive.xml_path)})")
            if step_archive.summary_path and step_archive.summary_path.exists():
                links.append(f"[📝 结构化摘要]({self._relative_path(step_archive.summary_path)})")
            if step_archive.llm_request_path and step_archive.llm_request_path.exists():
                links.append(f"[🤖 LLM 请求]({self._relative_path(step_archive.llm_request_path)})")
            if step_archive.llm_response_path and step_archive.llm_response_path.exists():
                links.append(f"[🤖 LLM 响应]({self._relative_path(step_archive.llm_response_path)})")
            if links:
                lines.append("#### 原始数据")
                lines.append("")
                lines.append(" | ".join(links))
                lines.append("")

        # -------- 步骤容器结束 --------
        lines.append("</div>")

        return "\n".join(lines)

    def _build_footer(self) -> str:
        """构建报告尾注。"""
        return (
            "## 报告信息\n\n"
            f"- **生成时间:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"- **报告目录:** `{self._archiver.base_dir}`\n"
            f"- 本报告由 mobile-automation 框架自动生成\n"
        )

    def _get_step_archive(self, step_index: int) -> Optional[StepArchiveData]:
        """按步骤序号查找对应的归档数据。"""
        for a in self._step_archives:
            if a.step_index == step_index:
                return a
        return None

    def _relative_path(self, path: Path) -> str:
        """
        将绝对路径转为相对于报告文件所在目录的路径。

        报告在 archiver.base_dir/report.md，所有归档文件在 base_dir/step_xx/ 下。
        相对于报告的路径 = 相对于 base_dir 的路径。

        参数
        ----------
        path : Path
            文件的绝对路径（应为 base_dir/step_xx/filename 格式）。

        返回
        -------
        str
            相对于 base_dir 的相对路径（POSIX 风格）。
        """
        try:
            return str(Path(os.path.relpath(path, start=self._archiver.base_dir)).as_posix())
        except (ValueError, OSError):
            return path.name
