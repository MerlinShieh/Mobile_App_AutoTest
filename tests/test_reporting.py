"""
报告归档与生成模块测试。

验证 DataArchiver 的文件保存功能、ReportGenerator 的 MD 报告生成逻辑。
"""

import json
import tempfile
from pathlib import Path

import pytest

from src.mobile_automation.models.action import Action, ActionParams
from src.mobile_automation.models.enums import ActionType, StepStatus, TaskStatus
from src.mobile_automation.models.task import StepRecord, TaskContext
from src.mobile_automation.reporting.archiver import DataArchiver, StepArchiveData
from src.mobile_automation.reporting.report_generator import ReportGenerator


class TestDataArchiver:
    """DataArchiver 归档器测试。"""

    def test_initialization_creates_directory(self):
        """验证初始化时创建归档目录。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            archiver = DataArchiver(task_id="test001", report_dir=tmpdir)
            assert archiver.base_dir.exists()
            assert archiver.base_dir.name == "test001"

    def test_save_screenshot(self):
        """验证截图文件保存。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            archiver = DataArchiver(task_id="test001", report_dir=tmpdir)
            path = archiver.save_screenshot(1, b"fake_image_bytes")
            assert path.exists()
            assert path.name == "screenshot.png"
            assert path.read_bytes() == b"fake_image_bytes"

    def test_save_screenshot_after(self):
        """验证操作后截图文件保存。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            archiver = DataArchiver(task_id="test001", report_dir=tmpdir)
            path = archiver.save_screenshot(1, b"after_bytes", after=True)
            assert path.exists()
            assert path.name == "screenshot_after.png"

    def test_save_raw_xml(self):
        """验证 XML 文件保存。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            archiver = DataArchiver(task_id="test001", report_dir=tmpdir)
            xml = '<node text="测试"/>'
            path = archiver.save_raw_xml(1, xml)
            assert path.exists()
            assert path.read_text(encoding="utf-8") == xml

    def test_save_structured_summary(self):
        """验证结构化摘要保存。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            archiver = DataArchiver(task_id="test001", report_dir=tmpdir)
            summary = "#1 [可点] 设置"
            path = archiver.save_structured_summary(1, summary)
            assert path.exists()
            assert path.read_text(encoding="utf-8") == summary

    def test_save_llm_request(self):
        """验证 LLM 请求消息保存。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            archiver = DataArchiver(task_id="test001", report_dir=tmpdir)
            messages = [{"role": "user", "content": "你好"}]
            path = archiver.save_llm_request(1, messages)
            assert path.exists()
            loaded = json.loads(path.read_text(encoding="utf-8"))
            assert loaded[0]["role"] == "user"

    def test_save_llm_request_masks_base64(self):
        """验证 Base64 图片被替换为占位符。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            archiver = DataArchiver(task_id="test001", report_dir=tmpdir)
            long_b64 = "A" * 1000
            messages = [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image;base64,{long_b64}"}},
            ]}]
            path = archiver.save_llm_request(1, messages)
            loaded = json.loads(path.read_text(encoding="utf-8"))
            url = loaded[0]["content"][0]["image_url"]["url"]
            assert len(url) < 500
            assert "[BASE64" in url

    def test_save_llm_response(self):
        """验证 LLM 响应保存。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            archiver = DataArchiver(task_id="test001", report_dir=tmpdir)
            path = archiver.save_llm_response(1, '{"action_type": "click"}')
            assert path.exists()
            loaded = json.loads(path.read_text(encoding="utf-8"))
            assert "response" in loaded

    def test_save_task_meta(self):
        """验证任务元数据保存。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            archiver = DataArchiver(task_id="test001", report_dir=tmpdir)
            archiver.save_task_meta({"task_id": "test001", "status": "completed"})
            meta_path = archiver.base_dir / "task_meta.json"
            assert meta_path.exists()
            loaded = json.loads(meta_path.read_text(encoding="utf-8"))
            assert loaded["task_id"] == "test001"

    def test_register_step_archive(self):
        """验证步骤归档数据注册。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            archiver = DataArchiver(task_id="test001", report_dir=tmpdir)
            step_dir = archiver.base_dir / "step_01"
            step_dir.mkdir()
            archive = StepArchiveData(
                step_index=1,
                step_dir=step_dir,
                screenshot_path=step_dir / "screenshot.png",
                action_type="click",
                status="success",
            )
            archiver.register_step_archive(archive)
            assert len(archiver.step_archives) == 1
            assert archiver.step_archives[0].action_type == "click"

    def test_get_report_path(self):
        """验证报告路径正确。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            archiver = DataArchiver(task_id="test001", report_dir=tmpdir)
            assert archiver.get_report_path().name == "report.md"

    def test_step_directories_per_step(self):
        """验证不同步骤有独立目录。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            archiver = DataArchiver(task_id="test001", report_dir=tmpdir)
            archiver.save_screenshot(1, b"step1")
            archiver.save_screenshot(2, b"step2")
            step1_dir = archiver.base_dir / "step_01"
            step2_dir = archiver.base_dir / "step_02"
            assert step1_dir.exists()
            assert step2_dir.exists()

    def test_sanitize_long_base64_in_messages(self):
        """验证长 Base64 被清洗。"""
        messages = [{"image_url": {"url": "data:image;base64," + "A" * 5000}}]
        result = DataArchiver._sanitize_for_json(messages)
        assert "[BASE64" in result[0]["image_url"]["url"]


class TestReportGenerator:
    """ReportGenerator 报告生成器测试。"""

    def test_generate_report_file(self):
        """验证报告文件生成。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            archiver = DataArchiver(task_id="report001", report_dir=tmpdir)

            step_record = StepRecord(
                step_index=1,
                action=Action(ActionType.CLICK, ActionParams(element_id="#1")),
                status=StepStatus.SUCCESS,
            )
            task_context = TaskContext(
                task_id="report001",
                user_goal="测试目标",
                status=TaskStatus.COMPLETED,
                steps=[step_record],
            )

            report_gen = ReportGenerator(task_context, archiver)
            report_path = report_gen.generate()

            assert report_path.exists()
            content = report_path.read_text(encoding="utf-8")
            assert "report001" in content
            assert "测试目标" in content
            assert "CLICK" in content or "click" in content

    def test_report_contains_overview(self):
        """验证报告包含任务概览。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            archiver = DataArchiver(task_id="r002", report_dir=tmpdir)

            step_record = StepRecord(
                step_index=1,
                action=Action(ActionType.CLICK, ActionParams(element_id="#1")),
                status=StepStatus.SUCCESS,
            )
            task_context = TaskContext(
                task_id="r002", user_goal="打开设置",
                status=TaskStatus.COMPLETED, steps=[step_record],
            )

            report_gen = ReportGenerator(task_context, archiver)
            content = report_gen.generate().read_text(encoding="utf-8")

            assert "## 任务概览" in content
            assert "**用户目标**" in content
            assert "**状态**" in content
            assert "✅" in content

    def test_report_contains_step_section(self):
        """验证报告包含步骤详情。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            archiver = DataArchiver(task_id="r003", report_dir=tmpdir)

            step_record = StepRecord(
                step_index=1,
                action=Action(ActionType.CLICK, ActionParams(element_id="#1"), reason="点击设置"),
                status=StepStatus.SUCCESS,
            )
            task_context = TaskContext(
                task_id="r003", user_goal="打开设置",
                status=TaskStatus.COMPLETED, steps=[step_record],
            )

            report_gen = ReportGenerator(task_context, archiver)
            content = report_gen.generate().read_text(encoding="utf-8")

            assert "### Step 01" in content
            assert "点击设置" in content
            assert "操作详情" in content

    def test_report_contains_footer(self):
        """验证报告包含尾注信息。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            archiver = DataArchiver(task_id="r004", report_dir=tmpdir)

            task_context = TaskContext(
                task_id="r004", user_goal="test",
                status=TaskStatus.FAILED,
            )
            report_gen = ReportGenerator(task_context, archiver)
            content = report_gen.generate().read_text(encoding="utf-8")

            assert "## 报告信息" in content
            assert "生成时间" in content
            assert "mobile-automation" in content

    def test_report_failed_step(self):
        """验证失败步骤的错误信息展示。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            archiver = DataArchiver(task_id="r005", report_dir=tmpdir)

            step_record = StepRecord(
                step_index=1,
                action=Action(ActionType.CLICK, ActionParams()),
                status=StepStatus.FAILED,
                error_message="元素未找到",
                retry_count=3,
            )
            task_context = TaskContext(
                task_id="r005", user_goal="test",
                status=TaskStatus.FAILED, steps=[step_record],
            )

            report_gen = ReportGenerator(task_context, archiver)
            content = report_gen.generate().read_text(encoding="utf-8")

            assert "❌" in content
            assert "元素未找到" in content
            assert "重试" in content
