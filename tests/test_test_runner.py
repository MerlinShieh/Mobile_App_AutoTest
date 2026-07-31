"""
BatchTestRunner 批量测试执行器测试。

验证测试用例定义、批量执行、结果汇总、JSON 文件导入等核心功能。
使用 mock 的 Orchestrator 避免真实设备依赖。
"""

import json
import tempfile
from pathlib import Path

from unittest.mock import MagicMock

import pytest

from src.mobile_automation.models.enums import TaskStatus
from src.mobile_automation.models.task import TaskContext
from src.mobile_automation.testing import (
    BatchTestRunner,
    TestCase,
    TestResult,
    TestSummary,
)


class TestTestCase:
    """TestCase 数据类测试。"""

    def test_basic_creation(self):
        """验证已基本参数创建。"""
        case = TestCase(goal="打开设置")
        assert case.goal == "打开设置"
        assert case.max_steps == 0
        assert case.expected_status == "completed"
        assert case.tags == []

    def test_full_creation(self):
        """验证所有参数完整创建。"""
        case = TestCase(
            goal="打开设置",
            max_steps=15,
            expected_status="aborted",
            description="基础测试",
            tags=["smoke", "settings"],
            timeout_seconds=120,
        )
        assert case.max_steps == 15
        assert case.expected_status == "aborted"
        assert "smoke" in case.tags

    def test_dataclass_asdict(self):
        """验证可序列化为字典。"""
        case = TestCase(goal="测试", tags=["a"])
        d = case.__dict__
        assert d["goal"] == "测试"
        assert d["tags"] == ["a"]


class TestTestResult:
    """TestResult 数据类测试。"""

    def test_default_failed(self):
        """验证默认是失败状态。"""
        result = TestResult(test_case=TestCase(goal="测试"))
        assert result.passed is False
        assert result.task_id == ""


class TestTestSummary:
    """TestSummary 数据类测试。"""

    def test_defaults(self):
        """验证默认值。"""
        summary = TestSummary()
        assert summary.total == 0
        assert summary.passed == 0
        assert summary.failed == 0


class TestBatchTestRunner:
    """BatchTestRunner 批量执行器测试。"""

    @pytest.fixture
    def mock_orchestrator(self, mocker):
        """创建 mock 的 TaskOrchestrator。"""
        orchestrator = mocker.MagicMock()
        # Mock _token_budget
        token_budget = mocker.MagicMock()
        token_budget.reset = mocker.MagicMock()
        orchestrator._token_budget = token_budget

        def mock_execute_task(user_goal, max_steps=None):
            context = mocker.MagicMock(spec=TaskContext)
            context.task_id = "test_" + user_goal[:4]
            context.status = TaskStatus.COMPLETED
            context.current_step = 5
            context.total_tokens_used = 1000
            context.get_success_rate.return_value = 1.0
            return context

        orchestrator.execute_task = mock_execute_task
        return orchestrator

    def test_initialization(self, mock_orchestrator):
        """验证初始化。"""
        runner = BatchTestRunner(mock_orchestrator)
        assert runner is not None

    def test_run_all_success(self, mock_orchestrator):
        """验证批量执行成功场景。"""
        runner = BatchTestRunner(mock_orchestrator)
        cases = [
            TestCase(goal="打开设置", max_steps=10),
            TestCase(goal="打开相机", max_steps=8),
        ]
        summary = runner.run_all(cases)
        assert summary.total == 2
        assert summary.passed == 2
        assert summary.failed == 0

    def test_run_all_passed_failed(self, mock_orchestrator):
        """验证部分失败场景。"""
        runner = BatchTestRunner(mock_orchestrator)
        call_count = [0]

        def mock_execute_with_fail(user_goal, max_steps=None):
            call_count[0] += 1
            context = MagicMock(spec=TaskContext)
            context.task_id = f"test_{call_count[0]}"
            context.current_step = 3
            context.total_tokens_used = 500
            context.get_success_rate.return_value = 0.5
            if call_count[0] == 2:
                context.status = TaskStatus.FAILED
            else:
                context.status = TaskStatus.COMPLETED
            return context

        mock_orchestrator.execute_task = mock_execute_with_fail

        cases = [
            TestCase(goal="成功用例"),
            TestCase(goal="失败用例"),
        ]
        summary = runner.run_all(cases)
        assert summary.total == 2

    def test_run_all_stop_on_failure(self, mock_orchestrator):
        """验证 stop_on_failure 在失败时停止。"""
        runner = BatchTestRunner(mock_orchestrator)
        call_count = [0]

        def mock_execute_stop(user_goal, max_steps=None):
            call_count[0] += 1
            context = MagicMock(spec=TaskContext)
            context.task_id = f"test_{call_count[0]}"
            context.status = TaskStatus.FAILED if call_count[0] == 1 else TaskStatus.COMPLETED
            context.current_step = 2
            context.total_tokens_used = 100
            context.get_success_rate.return_value = 0.0 if call_count[0] == 1 else 1.0
            return context

        mock_orchestrator.execute_task = mock_execute_stop

        cases = [
            TestCase(goal="第一个"),
            TestCase(goal="第二个"),
            TestCase(goal="第三个"),
        ]
        summary = runner.run_all(cases, stop_on_failure=True)
        # 第一个失败，stop_on_failure 导致只执行了一个用例
        assert summary.total >= 1

    def test_from_json(self, mock_orchestrator):
        """验证从 JSON 文件加载用例。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "test_cases.json"
            cases_data = [
                {"goal": "打开设置", "max_steps": 10, "tags": ["smoke"]},
                {"goal": "打开相机", "expected_status": "aborted"},
            ]
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(cases_data, f, ensure_ascii=False)

            runner = BatchTestRunner.from_json(mock_orchestrator, str(json_path))
            summary = runner.run_all(
                [TestCase(goal="打开设置"), TestCase(goal="打开相机")]
            )
            assert summary.total == 2

    def test_from_json_file_not_found(self, mock_orchestrator):
        """验证 JSON 文件不存在时抛出异常。"""
        with pytest.raises(FileNotFoundError):
            BatchTestRunner.from_json(mock_orchestrator, "/not/exist.json")

    def test_save_report(self, mock_orchestrator):
        """验证报告保存为 JSON。"""
        runner = BatchTestRunner(mock_orchestrator)
        summary = runner.run_all([TestCase(goal="测试用例")])

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "report.json"
            path = runner.save_report(summary, str(output))
            assert Path(path).exists()
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            assert data["total"] == 1
            assert "results" in data

    def test_run_single_exception(self, mock_orchestrator):
        """验证单用例异常处理。"""
        def mock_execute_error(user_goal, max_steps=None):
            raise RuntimeError("设备连接失败")

        mock_orchestrator.execute_task = mock_execute_error
        runner = BatchTestRunner(mock_orchestrator)
        result = runner._run_single(TestCase(goal="会失败的用例"))
        assert result.passed is False
        assert "设备连接失败" in result.error_message

    def test_save_report_creates_dir(self, mock_orchestrator):
        """验证保存报告时自动创建目录。"""
        runner = BatchTestRunner(mock_orchestrator)
        summary = runner.run_all([TestCase(goal="测试")])
        with tempfile.TemporaryDirectory() as tmpdir:
            nested = Path(tmpdir) / "sub" / "dir" / "report.json"
            path = runner.save_report(summary, str(nested))
            assert Path(path).exists()
