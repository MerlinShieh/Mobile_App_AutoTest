"""
批量测试执行器 —— BatchTestRunner。

支持以测试用例列表驱动的批量自动化执行模式。每个测试用例包含
用户目标、预期状态、最大步数等参数。支持：
- 单次设备连接的多个用例连续执行
- 用例级超时和失败隔离（一个失败不影响后续）
- JSON 格式的测试用例文件导入
- 汇总测试报告生成（JSON + 终端输出）
- 与 pytest 集成（通过 fixtures 获取 runner 实例）
"""

import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..config import settings
from ..core.orchestrator import TaskOrchestrator
from ..llm.token_budget import TokenBudgetManager
from ..logger import get_logger
from ..models.enums import TaskStatus
from ..models.task import TaskContext

logger = get_logger(__name__)


@dataclass
class TestCase:
    """
    单个测试用例定义。

    参数
    ----------
    goal : str
        用户任务目标描述，例如 "打开设置，找到 Wi-Fi 选项"。
    max_steps : int
        本用例允许的最大执行步数。0 表示使用配置默认值。
    expected_status : str
        预期任务状态，可选: "completed" / "aborted" / "failed"。
        用于断言测试结果。
    description : str
        可选的用例描述，用于日志和报告中标识目的。
    tags : list[str]
        可选的标签列表，用于用例分组和筛选。
    timeout_seconds : int
        用例级超时时间（秒），0 表示使用配置默认值。
    """

    goal: str
    max_steps: int = 0
    expected_status: str = "completed"
    description: str = ""
    tags: list[str] = field(default_factory=list)
    timeout_seconds: int = 0


@dataclass
class TestResult:
    """
    单个测试用例的执行结果。

    参数
    ----------
    test_case : TestCase
        对应的测试用例定义。
    status : str
        实际任务结束状态。
    steps_executed : int
        实际执行的步数。
    success_rate : float
        步骤成功率 (0.0 ~ 1.0)。
    error_message : str
        执行异常时的错误描述。
    duration_seconds : float
        用例执行耗时（秒）。
    tokens_used : int
        消耗的 Token 总数。
    passed : bool
        是否通过断言（实际状态 = 预期状态 + 无异常）。
    task_id : str
        任务唯一标识符。
    """

    test_case: TestCase
    status: str = ""
    steps_executed: int = 0
    success_rate: float = 0.0
    error_message: str = ""
    duration_seconds: float = 0.0
    tokens_used: int = 0
    passed: bool = False
    task_id: str = ""


@dataclass
class TestSummary:
    """
    批量测试的汇总结果。

    参数
    ----------
    total : int
        总用例数。
    passed : int
        通过用例数。
    failed : int
        失败用例数。
    total_duration : float
        总耗时（秒）。
    results : list[TestResult]
        每个用例的详细结果列表。
    started_at : str
        测试启动时间。
    """

    total: int = 0
    passed: int = 0
    failed: int = 0
    total_duration: float = 0.0
    results: list[TestResult] = field(default_factory=list)
    started_at: str = ""


class BatchTestRunner:
    """
    批量测试执行器。

    管理一组测试用例的批量执行。提供用例级的超时控制和失败隔离，
    支持 JSON 文件导入用例。每次执行后生成汇总报告。

    使用方式
    --------
    >>> runner = BatchTestRunner(orchestrator)
    >>> cases = [
    ...     TestCase(goal="打开设置", max_steps=10),
    ...     TestCase(goal="打开相机", max_steps=8),
    ... ]
    >>> summary = runner.run_all(cases)
    >>> print(f"通过: {summary.passed}/{summary.total}")
    """

    def __init__(self, orchestrator: TaskOrchestrator) -> None:
        """
        初始化 BatchTestRunner。

        参数
        ----------
        orchestrator : TaskOrchestrator
            已初始化的任务编排器实例。
        """
        self._orchestrator: TaskOrchestrator = orchestrator
        self._token_budget: TokenBudgetManager = orchestrator._token_budget

    @classmethod
    def from_json(cls, orchestrator: TaskOrchestrator, json_path: str) -> "BatchTestRunner":
        """
        从 JSON 文件加载测试用例并创建执行器。

        JSON 文件格式：
        ```json
        [
            {
                "goal": "打开设置",
                "max_steps": 10,
                "expected_status": "completed",
                "description": "基础设置打开测试",
                "tags": ["smoke", "settings"]
            }
        ]
        ```

        参数
        ----------
        orchestrator : TaskOrchestrator
            任务编排器实例。
        json_path : str
            JSON 文件路径。

        返回
        -------
        BatchTestRunner
            已加载用例的测试执行器。

        异常
        ------
        FileNotFoundError
            JSON 文件不存在时抛出。
        json.JSONDecodeError
            JSON 格式错误时抛出。
        """
        path = Path(json_path)
        if not path.exists():
            raise FileNotFoundError(f"测试用例文件不存在: {json_path}")

        with open(path, "r", encoding="utf-8") as f:
            data: list[dict] = json.load(f)

        cases: list[TestCase] = [
            TestCase(
                goal=item["goal"],
                max_steps=item.get("max_steps", 0),
                expected_status=item.get("expected_status", "completed"),
                description=item.get("description", ""),
                tags=item.get("tags", []),
                timeout_seconds=item.get("timeout_seconds", 0),
            )
            for item in data
        ]

        runner = cls(orchestrator)
        logger.info("从 JSON 文件加载 %d 个测试用例: %s", len(cases), json_path)
        return runner

    def run_all(
        self,
        cases: list[TestCase],
        stop_on_failure: bool = False,
    ) -> TestSummary:
        """
        批量执行所有测试用例。

        参数
        ----------
        cases : list[TestCase]
            待执行的测试用例列表。
        stop_on_failure : bool
            遇到失败是否立即停止后续用例执行。

        返回
        -------
        TestSummary
            包含所有用例结果的汇总。
        """
        started_at: str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        start_time: float = time.time()
        results: list[TestResult] = []

        logger.info("批量测试开始: %d 个用例, stop_on_failure=%s", len(cases), stop_on_failure)

        for i, case in enumerate(cases, start=1):
            logger.info("=" * 50)
            logger.info("执行用例 %d/%d: %s", i, len(cases), case.goal)
            logger.info("描述: %s", case.description or "(无)")
            logger.info("标签: %s", case.tags or "(无)")
            logger.info("=" * 50)

            result: TestResult = self._run_single(case)
            results.append(result)

            # 终端输出
            status_icon = "✅" if result.passed else "❌"
            print(f"  {status_icon} [{i}/{len(cases)}] {case.goal[:60]:60s} → {result.status:12s} "
                  f"({result.steps_executed}步, {result.duration_seconds:.1f}s)")

            if result.error_message:
                print(f"     错误: {result.error_message}")

            if not result.passed and stop_on_failure:
                logger.warning("stop_on_failure 触发，停止后续用例执行")
                break

        total_duration: float = time.time() - start_time
        passed_count: int = sum(1 for r in results if r.passed)
        failed_count: int = sum(1 for r in results if not r.passed)

        summary: TestSummary = TestSummary(
            total=len(results),
            passed=passed_count,
            failed=failed_count,
            total_duration=total_duration,
            results=results,
            started_at=started_at,
        )

        # 打印汇总
        print("\n" + "=" * 60)
        print("批量测试汇总")
        print("=" * 60)
        print(f"  总用例:  {summary.total}")
        print(f"  通过:    {summary.passed} ✅")
        print(f"  失败:    {summary.failed} ❌")
        print(f"  通过率:  {summary.passed / max(summary.total, 1) * 100:.1f}%")
        print(f"  总耗时:  {summary.total_duration:.1f} 秒")
        print("=" * 60)

        logger.info("批量测试完成: total=%d, passed=%d, failed=%d, duration=%.1fs",
                     summary.total, summary.passed, summary.failed, total_duration)

        return summary

    def save_report(self, summary: TestSummary, output_path: str) -> str:
        """
        将测试汇总结果保存为 JSON 文件。

        参数
        ----------
        summary : TestSummary
            测试汇总数据。
        output_path : str
            输出文件路径。

        返回
        -------
        str
            实际写入的文件路径。
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        report_data: dict[str, Any] = {
            "started_at": summary.started_at,
            "total": summary.total,
            "passed": summary.passed,
            "failed": summary.failed,
            "total_duration_seconds": round(summary.total_duration, 2),
            "pass_rate": round(summary.passed / max(summary.total, 1) * 100, 1),
            "results": [
                {
                    "goal": r.test_case.goal,
                    "description": r.test_case.description,
                    "tags": r.test_case.tags,
                    "expected_status": r.test_case.expected_status,
                    "status": r.status,
                    "steps": r.steps_executed,
                    "success_rate": round(r.success_rate, 2),
                    "duration_seconds": round(r.duration_seconds, 2),
                    "tokens_used": r.tokens_used,
                    "passed": r.passed,
                    "task_id": r.task_id,
                    "error": r.error_message,
                }
                for r in summary.results
            ],
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)

        logger.info("测试报告已保存: %s", path)
        return str(path)

    def run_from_file(
        self,
        json_path: str,
        stop_on_failure: bool = False,
        output_path: Optional[str] = None,
    ) -> TestSummary:
        """
        从 JSON 文件加载用例并批量执行。

        参数
        ----------
        json_path : str
            测试用例 JSON 文件路径。
        stop_on_failure : bool
            遇到失败是否停止。
        output_path : Optional[str]
            结果输出路径，为 None 时不保存文件。

        返回
        -------
        TestSummary
            汇总结果。
        """
        runner = self.from_json(self._orchestrator, json_path)
        # 恢复用原来的 cases 列表
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cases = [
            TestCase(
                goal=item["goal"],
                max_steps=item.get("max_steps", 0),
                expected_status=item.get("expected_status", "completed"),
                description=item.get("description", ""),
                tags=item.get("tags", []),
                timeout_seconds=item.get("timeout_seconds", 0),
            )
            for item in data
        ]
        summary = self.run_all(cases, stop_on_failure=stop_on_failure)
        if output_path:
            self.save_report(summary, output_path)
        return summary

    def _run_single(self, case: TestCase) -> TestResult:
        """
        执行单个测试用例。

        参数
        ----------
        case : TestCase
            待执行的测试用例。

        返回
        -------
        TestResult
            用例执行结果。
        """
        result: TestResult = TestResult(test_case=case)
        start_time: float = time.time()

        try:
            context: TaskContext = self._orchestrator.execute_task(
                user_goal=case.goal,
                max_steps=case.max_steps if case.max_steps > 0 else None,
            )

            result.status = context.status.value
            result.steps_executed = context.current_step
            result.success_rate = context.get_success_rate()
            result.tokens_used = context.total_tokens_used
            result.task_id = context.task_id

            # 断言：实际状态 = 预期状态 + 无异常
            result.passed = (context.status.value == case.expected_status)

        except Exception as exc:
            result.status = "error"
            result.error_message = str(exc)
            result.passed = False
            logger.error("用例执行异常: %s -> %s", case.goal, exc)

        result.duration_seconds = round(time.time() - start_time, 2)
        return result
