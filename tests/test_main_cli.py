"""
CLI 入口（main.py）测试。

验证命令行参数解析（run/test 子命令）、向后兼容用法、用例文件加载、
批量测试入口分发逻辑与报告生成。批量测试使用 mock 的 BatchTestRunner
和 build_app，避免真实设备依赖。
"""

import argparse
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.mobile_automation import main
from src.mobile_automation.models.task import TaskContext
from src.mobile_automation.testing import TestCase, TestResult, TestSummary


class TestParseArgs:
    """parse_args 参数解析测试。"""

    def test_parse_run_subcommand(self):
        """验证 run 子命令参数解析。"""
        args = main.parse_args(
            ["run", "-g", "打开设置", "-s", "abc123", "-p", "qwen", "-m", "15"]
        )
        assert args.command == "run"
        assert args.goal == "打开设置"
        assert args.serial == "abc123"
        assert args.provider == "qwen"
        assert args.max_steps == 15

    def test_parse_legacy_no_subcommand(self):
        """向后兼容：不带子命令直接使用 -g。"""
        args = main.parse_args(["-g", "打开设置"])
        assert args.command is None
        assert args.goal == "打开设置"

    def test_parse_legacy_full_args(self):
        """向后兼容：无子命令 + 全部参数。"""
        args = main.parse_args(["-g", "打开设置", "-s", "abc", "-m", "10"])
        assert args.command is None
        assert args.serial == "abc"
        assert args.max_steps == 10

    def test_parse_test_subcommand(self):
        """验证 test 子命令解析（含 filter/format-report）。"""
        args = main.parse_args(
            [
                "test",
                "./examples/test_cases.json",
                "--filter",
                "smoke",
                "--format-report",
                "html",
            ]
        )
        assert args.command == "test"
        assert args.cases == "./examples/test_cases.json"
        assert args.filter == "smoke"
        assert args.format_report == "html"

    def test_parse_test_defaults(self):
        """验证 test 子命令默认值。"""
        args = main.parse_args(["test", "cases.json"])
        assert args.command == "test"
        assert args.cases == "cases.json"
        assert args.filter == ""
        assert args.format_report == "json"

    def test_parse_test_supports_run_args(self):
        """验证 test 子命令也支持 -s/-p 等执行参数。"""
        args = main.parse_args(["test", "cases.json", "-s", "abc", "-p", "mimo"])
        assert args.serial == "abc"
        assert args.provider == "mimo"


class TestLoadCases:
    """load_cases 用例文件加载测试。"""

    def test_load_cases(self, tmp_path):
        """验证从 JSON 文件加载用例并映射到 TestCase 字段。"""
        json_path = tmp_path / "cases.json"
        json_path.write_text(
            json.dumps(
                [
                    {
                        "goal": "打开设置",
                        "max_steps": 10,
                        "expected_status": "completed",
                        "description": "冒烟",
                        "tags": ["smoke", "settings"],
                        "timeout_seconds": 120,
                    },
                    {"goal": "打开相机"},
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        cases = main.load_cases(str(json_path))
        assert len(cases) == 2
        assert cases[0].goal == "打开设置"
        assert cases[0].max_steps == 10
        assert cases[0].tags == ["smoke", "settings"]
        assert cases[0].timeout_seconds == 120
        # 未提供字段使用默认值
        assert cases[1].goal == "打开相机"
        assert cases[1].max_steps == 0
        assert cases[1].expected_status == "completed"

    def test_load_cases_file_not_found(self):
        """验证文件不存在时抛出 FileNotFoundError。"""
        with pytest.raises(FileNotFoundError):
            main.load_cases("/not/exist.json")


class TestRunBatchTests:
    """run_batch_tests 分发逻辑测试（mock BatchTestRunner）。"""

    @pytest.fixture
    def mock_env(self, mocker):
        """mock 模块构建与 BatchTestRunner。"""
        mocker.patch(
            "src.mobile_automation.main.build_app",
            return_value=(MagicMock(), MagicMock()),
        )
        mock_runner_cls = mocker.patch("src.mobile_automation.main.BatchTestRunner")
        mock_runner = mock_runner_cls.return_value
        mock_runner.run_all.return_value = TestSummary(total=1, passed=1, failed=0)
        return mock_runner

    @staticmethod
    def _make_args(
        cases="cases.json",
        filter_="",
        fmt="json",
        report_dir="",
        stop_on_failure=False,
    ) -> argparse.Namespace:
        return argparse.Namespace(
            command="test",
            cases=cases,
            filter=filter_,
            format_report=fmt,
            report_dir=report_dir,
            stop_on_failure=stop_on_failure,
            goal="",
            serial="",
            provider="",
            max_steps=0,
        )

    @staticmethod
    def _write_cases(tmp_path, cases_data) -> str:
        json_path = tmp_path / "cases.json"
        json_path.write_text(
            json.dumps(cases_data, ensure_ascii=False),
            encoding="utf-8",
        )
        return str(json_path)

    def test_run_batch_tests_all_passed(self, mock_env, tmp_path):
        """验证全部通过时退出码 0，且调用 run_all。"""
        cases = self._write_cases(tmp_path, [{"goal": "打开设置"}])
        code = main.run_batch_tests(self._make_args(cases=cases))
        assert code == 0
        mock_env.run_all.assert_called_once()

    def test_run_batch_tests_with_filter(self, mock_env, tmp_path):
        """验证 --filter 只执行匹配标签的用例。"""
        cases = self._write_cases(
            tmp_path,
            [
                {"goal": "A", "tags": ["smoke"]},
                {"goal": "B", "tags": ["regression"]},
            ],
        )
        code = main.run_batch_tests(self._make_args(cases=cases, filter_="smoke"))
        assert code == 0
        # run_all 收到的用例列表只有带 smoke 标签的一个
        passed_cases = mock_env.run_all.call_args.args[0]
        assert len(passed_cases) == 1
        assert passed_cases[0].goal == "A"

    def test_run_batch_tests_filter_no_match(self, mock_env, tmp_path):
        """验证筛选无匹配用例时退出码 1 且不执行 run_all。"""
        cases = self._write_cases(tmp_path, [{"goal": "A", "tags": ["smoke"]}])
        code = main.run_batch_tests(self._make_args(cases=cases, filter_="nope"))
        assert code == 1
        mock_env.run_all.assert_not_called()

    def test_run_batch_tests_failed(self, mock_env, tmp_path):
        """验证存在失败用例时退出码 1。"""
        mock_env.run_all.return_value = TestSummary(total=2, passed=1, failed=1)
        cases = self._write_cases(tmp_path, [{"goal": "A"}, {"goal": "B"}])
        code = main.run_batch_tests(self._make_args(cases=cases))
        assert code == 1

    def test_run_batch_tests_missing_cases(self, mocker):
        """验证未指定用例文件时退出码 2，且不构建模块。"""
        mock_build = mocker.patch("src.mobile_automation.main.build_app")
        code = main.run_batch_tests(self._make_args(cases=""))
        assert code == 2
        mock_build.assert_not_called()

    def test_run_batch_tests_report_saved(self, mock_env, tmp_path):
        """验证执行后按指定格式保存报告文件。"""
        cases = self._write_cases(tmp_path, [{"goal": "A"}])
        report_dir = tmp_path / "out"
        code = main.run_batch_tests(
            self._make_args(cases=cases, fmt="html", report_dir=str(report_dir))
        )
        assert code == 0
        assert list(report_dir.rglob("*.html"))

    def test_run_batch_tests_stop_on_failure(self, mock_env, tmp_path):
        """验证 stop_on_failure 参数透传给 run_all。"""
        cases = self._write_cases(tmp_path, [{"goal": "A"}])
        main.run_batch_tests(self._make_args(cases=cases, stop_on_failure=True))
        mock_env.run_all.assert_called_once()
        assert mock_env.run_all.call_args.kwargs["stop_on_failure"] is True

    def test_run_batch_tests_file_not_found(self, mock_env):
        """验证用例文件不存在时异常被捕获并返回退出码 1。"""
        code = main.run_batch_tests(self._make_args(cases="/not/exist.json"))
        assert code == 1
        mock_env.run_all.assert_not_called()


class TestSaveBatchReport:
    """save_batch_report 报告生成测试。"""

    @pytest.fixture
    def sample_summary(self):
        """构造一个包含通过/失败用例的示例汇总结果。"""
        ok = TestResult(
            test_case=TestCase(
                goal="打开设置", tags=["smoke"], description="冒烟", expected_status="completed"
            ),
            status="completed",
            steps_executed=3,
            success_rate=1.0,
            duration_seconds=5.0,
            tokens_used=100,
            passed=True,
            task_id="t1",
        )
        fail = TestResult(
            test_case=TestCase(goal="打开相机"),
            status="failed",
            steps_executed=1,
            success_rate=0.0,
            duration_seconds=2.0,
            error_message="设备连接断开",
            passed=False,
            task_id="t2",
        )
        return TestSummary(
            total=2,
            passed=1,
            failed=1,
            total_duration=7.0,
            results=[ok, fail],
            started_at="2026-08-04 10:00:00",
        )

    @staticmethod
    def _make_args(fmt="json", report_dir="") -> argparse.Namespace:
        return argparse.Namespace(format_report=fmt, report_dir=report_dir)

    def test_save_json(self, sample_summary, tmp_path):
        """验证 JSON 报告生成。"""
        out = tmp_path / "out"
        path = main.save_batch_report(sample_summary, self._make_args("json", str(out)))
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        assert data["total"] == 2
        assert data["passed"] == 1
        assert data["failed"] == 1
        assert data["pass_rate"] == 50.0
        assert len(data["results"]) == 2

    def test_save_markdown(self, sample_summary, tmp_path):
        """验证 Markdown 报告生成。"""
        out = tmp_path / "out"
        path = main.save_batch_report(sample_summary, self._make_args("md", str(out)))
        content = Path(path).read_text(encoding="utf-8")
        assert content.startswith("# 批量测试报告")
        assert "打开设置" in content
        assert "设备连接断开" in content

    def test_save_html(self, sample_summary, tmp_path):
        """验证 HTML 报告生成。"""
        out = tmp_path / "out"
        path = main.save_batch_report(sample_summary, self._make_args("html", str(out)))
        content = Path(path).read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "打开设置" in content
        assert "<table>" in content

    def test_save_uses_default_report_dir(self, sample_summary, tmp_path, monkeypatch):
        """验证默认报告目录为 reports/batch 下的时间戳子目录。"""
        monkeypatch.chdir(tmp_path)
        path = main.save_batch_report(sample_summary, self._make_args("json", ""))
        assert Path(path).exists()
        assert "reports" in path


class TestRunSingleTask:
    """run_single_task 分发逻辑测试。"""

    def test_missing_goal_returns_2(self, mocker):
        """验证缺少 goal 时退出码 2 且不构建模块。"""
        mock_build = mocker.patch("src.mobile_automation.main.build_app")
        args = argparse.Namespace(goal="", max_steps=0)
        assert main.run_single_task(args) == 2
        mock_build.assert_not_called()

    def test_completed_returns_0(self, mocker):
        """验证任务完成时退出码 0。"""
        mock_orchestrator = MagicMock()
        mock_ctx = MagicMock(spec=TaskContext)
        mock_ctx.status.value = "completed"
        mock_ctx.steps = []
        mock_orchestrator.execute_task.return_value = mock_ctx
        mock_build = mocker.patch("src.mobile_automation.main.build_app")
        mock_build.return_value = (mock_orchestrator, MagicMock())

        args = argparse.Namespace(goal="打开设置", max_steps=0)
        assert main.run_single_task(args) == 0
        mock_orchestrator.execute_task.assert_called_once()

    def test_failed_returns_1(self, mocker):
        """验证任务失败时退出码 1。"""
        mock_orchestrator = MagicMock()
        mock_ctx = MagicMock(spec=TaskContext)
        mock_ctx.status.value = "failed"
        mock_ctx.steps = []
        mock_orchestrator.execute_task.return_value = mock_ctx
        mock_build = mocker.patch("src.mobile_automation.main.build_app")
        mock_build.return_value = (mock_orchestrator, MagicMock())

        args = argparse.Namespace(goal="打开设置", max_steps=0)
        assert main.run_single_task(args) == 1


class TestMainDispatch:
    """main() 子命令分发测试。"""

    def test_dispatch_to_batch(self, mocker):
        """验证 test 子命令分发到 run_batch_tests。"""
        mocker.patch(
            "src.mobile_automation.main.parse_args",
            return_value=argparse.Namespace(command="test"),
        )
        mock_batch = mocker.patch("src.mobile_automation.main.run_batch_tests", return_value=0)
        assert main.main() == 0
        mock_batch.assert_called_once()

    def test_dispatch_to_single(self, mocker):
        """验证 run 子命令分发到 run_single_task。"""
        mocker.patch(
            "src.mobile_automation.main.parse_args",
            return_value=argparse.Namespace(command="run"),
        )
        mock_single = mocker.patch("src.mobile_automation.main.run_single_task", return_value=0)
        assert main.main() == 0
        mock_single.assert_called_once()

    def test_dispatch_legacy_default(self, mocker):
        """验证无子命令（command=None）时按单任务分发。"""
        mocker.patch(
            "src.mobile_automation.main.parse_args",
            return_value=argparse.Namespace(command=None),
        )
        mock_single = mocker.patch("src.mobile_automation.main.run_single_task", return_value=0)
        assert main.main() == 0
        mock_single.assert_called_once()
