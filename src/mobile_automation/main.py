"""
CLI 入口 —— 移动端 AI 自动化操作框架的命令行启动点。

提供命令行参数解析，支持指定任务描述、设备序列号、LLM 提供商和
最大步数等参数。启动时自动初始化日志系统、设备连接和所有核心模块。

支持两个子命令：
- run：单任务执行（默认行为，参数与旧版一致）
- test：批量测试（加载用例文件批量执行，支持标签筛选与报告生成）

设计参考:
- Open-AutoGLM: 交互模式（interactive mode）+ 简洁输出
- mobile-mcp: 结构化进度反馈

使用方式
--------
python -m src.mobile_automation.main -g "打开设置，找到 Wi-Fi 选项"
python -m src.mobile_automation.main run -g "打开设置" --serial xxxxxx
python -m src.mobile_automation.main run -g "..." --provider qwen --max-steps 50
python -m src.mobile_automation.main test ./examples/test_cases.json
python -m src.mobile_automation.main test ./examples/test_cases.json --filter smoke
python -m src.mobile_automation.main test ./examples/test_cases.json --format-report html
"""

import argparse
import html as html_lib
import io
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .config import settings
from .core.orchestrator import TaskOrchestrator
from .core.step_runner import StepRunner
from .device.device_manager import DeviceManager
from .executor.action_executor import ActionExecutor
from .llm.llm_service import LLMService
from .llm.token_budget import TokenBudgetManager
from .logger import get_logger, setup_logger, log_step_progress, log_task_start, log_task_end
from .models.task import TaskContext
from .perception.screen_capture import ScreenCapture
from .popup.popup_handler import PopupHandler
from .testing import BatchTestRunner, TestCase, TestSummary

logger = get_logger(__name__)


def _setup_stdout() -> None:
    """
    跨平台终端输出兼容：将 stdout 包装为 UTF-8 编码，容忍无法编码的字符。

    仅在命令行入口（__main__）调用，避免在模块导入时包装 stdout，
    从而不影响 pytest 等框架对标准输出的捕获。
    """
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer,
            encoding="utf-8",
            errors="replace",
            line_buffering=bool(sys.stdout.line_buffering),
        )


# 支持的批量测试报告格式
REPORT_FORMATS: tuple[str, ...] = ("json", "md", "html")
# 批量测试报告默认输出根目录
BATCH_REPORT_DIR: str = "reports/batch"


def _add_run_args(parser: argparse.ArgumentParser) -> None:
    """
    向 parser 添加单任务/批量测试共用的执行参数。

    - goal / -g：任务描述（可选，运行时校验，便于向后兼容无子命令用法）
    - serial / -s：设备序列号
    - provider / -p：LLM 提供商
    - max-steps / -m：最大步数
    """
    parser.add_argument(
        "-g", "--goal",
        type=str,
        default="",
        help="用户任务目标描述，如「打开设置找到 Wi-Fi 开关」",
    )
    parser.add_argument(
        "-s", "--serial",
        type=str,
        default="",
        help="设备序列号（ADB serial），不指定则自动选择在线设备",
    )
    parser.add_argument(
        "-p", "--provider",
        type=str,
        default="",
        choices=["qwen", "openai", "anthropic", "zhipu", "mimo", "local"],
        help="LLM 提供商（默认从配置文件读取）",
    )
    parser.add_argument(
        "-m", "--max-steps",
        type=int,
        default=0,
        help="任务最大执行步数（默认从配置文件读取）",
    )


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """
    解析命令行参数。

    支持两个子命令：
    - run：单任务执行（参数与旧版一致：-g/-s/-p/-m）
    - test：批量测试（用例文件路径 + --filter + --format-report 等）

    向后兼容：不带子命令直接使用 -g/--goal 时按单任务执行。

    参数
    ----------
    argv : Optional[list[str]]
        命令行参数列表，为 None 时使用 sys.argv[1:]。

    返回
    -------
    argparse.Namespace
        解析后的命令行参数对象。
    """
    parser = argparse.ArgumentParser(
        description="移动端 AI 自动化操作框架 —— 基于多模态 LLM 的自动化测试工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python -m mobile_automation.main -g "打开设置"
  python -m mobile_automation.main run -g "打开设置" -s 123456
  python -m mobile_automation.main run -g "..." -p openai -m 50
  python -m mobile_automation.main test ./examples/test_cases.json
  python -m mobile_automation.main test ./examples/test_cases.json --filter smoke
  python -m mobile_automation.main test ./examples/test_cases.json --format-report html
        """,
    )
    subparsers = parser.add_subparsers(
        dest="command",
        metavar="COMMAND",
        help="子命令: run（单任务执行）或 test（批量测试）",
    )

    # ---- 单任务执行子命令 ----
    run_parser = subparsers.add_parser(
        "run",
        help="单任务执行：执行一个用户目标（默认行为）",
        description="单任务执行：执行一个用户目标（默认行为）",
    )
    _add_run_args(run_parser)

    # ---- 批量测试子命令 ----
    test_parser = subparsers.add_parser(
        "test",
        help="批量测试：按用例文件批量执行自动化测试",
        description="批量测试：按用例文件批量执行自动化测试",
    )
    test_parser.add_argument(
        "cases",
        type=str,
        nargs="?",
        default="",
        help="测试用例 JSON 文件路径，例如 ./examples/test_cases.json",
    )
    test_parser.add_argument(
        "--filter",
        type=str,
        default="",
        help="按标签筛选用例，例如 --filter smoke 只执行带 smoke 标签的用例",
    )
    test_parser.add_argument(
        "--format-report",
        type=str,
        default="json",
        choices=list(REPORT_FORMATS),
        help="批量测试报告格式（默认 json，可选 md/html）",
    )
    test_parser.add_argument(
        "--report-dir",
        type=str,
        default="",
        help="批量测试报告输出根目录（默认 reports/batch）",
    )
    test_parser.add_argument(
        "--stop-on-failure",
        action="store_true",
        help="遇到失败用例时立即停止后续用例执行",
    )
    _add_run_args(test_parser)

    # ---- 顶层参数：向后兼容不带子命令的用法 ----
    _add_run_args(parser)

    return parser.parse_args(argv)


def build_app(args: argparse.Namespace) -> tuple[TaskOrchestrator, DeviceManager]:
    """
    构建应用所需的所有核心模块。

    初始化流程：
      1. 设置日志系统（setup_logger）
      2. 初始化设备管理器（DeviceManager）并连接设备
      3. 初始化感知模块（ScreenCapture）
      4. 初始化弹窗处理器（PopupHandler）
      5. 初始化 LLM 服务（LLMService）
      6. 初始化动作执行器（ActionExecutor）
      7. 初始化单步引擎（StepRunner）
      8. 初始化 Token 预算管理器（TokenBudgetManager）
      9. 初始化任务编排器（TaskOrchestrator）

    参数
    ----------
    args : argparse.Namespace
        命令行参数。

    返回
    -------
    tuple[TaskOrchestrator, DeviceManager]
        (TaskOrchestrator 实例, DeviceManager 实例)。

    异常
    ------
    RuntimeError
        设备连接失败时抛出。
    """
    setup_logger(
        log_dir=settings.logger.log_dir,
        log_level=settings.logger.log_level,
        rotation_mb=settings.logger.log_rotation_mb,
        retention_days=settings.logger.log_retention_days,
    )

    provider_name = args.provider or settings.llm.provider
    if provider_name not in settings.models.providers:
        raise RuntimeError(
            f"供应商 {provider_name} 未在配置中注册，请在 MODELS__PROVIDERS 中配置。"
            f"当前已注册的供应商: {', '.join(settings.models.providers.keys())}"
        )
    provider_cfg = settings.models.providers[provider_name]
    if not provider_cfg.api_key:
        raise RuntimeError(
            f"供应商 {provider_name} 的 API Key 未配置，请在 .env 中设置 "
            f"MODELS__PROVIDERS__{provider_name.upper()}__API_KEY"
        )

    dm: DeviceManager = DeviceManager()
    serial: str = args.serial or settings.device.serial
    logger.info("连接设备: serial=%s", serial or "自动选择")
    dm.connect(serial=serial)
    if not dm.health_check():
        raise RuntimeError("设备连接失败，请检查 ADB 连接状态")
    logger.info("设备连接成功: serial=%s", dm._serial)

    screen_w, screen_h = dm.get_screen_size()
    logger.info("屏幕尺寸: %dx%d", screen_w, screen_h)

    capture: ScreenCapture = ScreenCapture(dm)
    popup_handler: PopupHandler = PopupHandler(dm)
    llm_service: LLMService = LLMService(provider=args.provider or None)
    executor: ActionExecutor = ActionExecutor(dm)
    token_budget: TokenBudgetManager = TokenBudgetManager(provider=args.provider or None)
    step_runner: StepRunner = StepRunner(
        device_manager=dm,
        perception=capture,
        popup_handler=popup_handler,
        llm_service=llm_service,
        action_executor=executor,
        token_budget=token_budget,
    )
    orchestrator: TaskOrchestrator = TaskOrchestrator(
        step_runner=step_runner,
        token_budget=token_budget,
    )

    logger.info("所有模块初始化完成")
    return orchestrator, dm


def run_task(orchestrator: TaskOrchestrator, goal: str, max_steps: int) -> TaskContext:
    """
    执行自动化任务并打印结果摘要。

    参考 Open-AutoGLM 的任务输出格式，新增:
    - 步骤级进度输出 [step/total]
    - 任务开始/结束横幅
    - 执行耗时统计

    参数
    ----------
    orchestrator : TaskOrchestrator
        任务编排器实例。
    goal : str
        用户任务目标描述。
    max_steps : int
        任务最大步数（0 表示使用配置默认值）。

    返回
    -------
    TaskContext
        包含执行结果的任务上下文。
    """
    actual_max_steps = max_steps if max_steps > 0 else settings.execution.max_steps_per_task
    log_task_start(goal, device=settings.device.serial, max_steps=actual_max_steps)

    start_time: float = time.time()

    task_context: TaskContext = orchestrator.execute_task(
        user_goal=goal,
        max_steps=max_steps if max_steps > 0 else None,
    )

    elapsed: float = time.time() - start_time

    # 使用结构化格式输出步骤详情
    if task_context.steps:
        for step in task_context.steps:
            status_icon: str = {
                "success": "OK",
                "failed": "FAIL",
                "aborted": "WARN",
                "skipped": "SKIP",
                "retrying": "RETRY",
            }.get(step.status.value, "?")
            action_desc: str = f"{step.action.action_type.value}"
            if step.action.params.element_id:
                action_desc += f" [#{step.action.params.element_id}]"
            if step.action.params.text:
                action_desc += f' "{step.action.params.text[:20]}"'
            log_step_progress(
                step.step_index,
                len(task_context.steps),
                f"{status_icon} {action_desc}",
                step.action.reason[:60] if step.action.reason else "",
            )

    log_task_end(
        status=task_context.status.value,
        steps=task_context.current_step,
        tokens=task_context.total_tokens_used,
        duration=elapsed,
    )

    return task_context


def load_cases(json_path: str) -> list[TestCase]:
    """
    从 JSON 文件加载测试用例列表。

    JSON 文件格式（与 BatchTestRunner.TestCase 字段一致）：
    ```json
    [
        {
            "goal": "打开设置",
            "max_steps": 10,
            "expected_status": "completed",
            "description": "基础设置打开测试",
            "tags": ["smoke", "settings"],
            "timeout_seconds": 120
        }
    ]
    ```

    参数
    ----------
    json_path : str
        JSON 用例文件路径。

    返回
    -------
    list[TestCase]
        解析出的测试用例列表。

    异常
    ------
    FileNotFoundError
        JSON 文件不存在时抛出。
    """
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"测试用例文件不存在: {json_path}")

    with open(path, "r", encoding="utf-8") as f:
        data: list[dict] = json.load(f)

    return [
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


def _summary_to_json(summary: TestSummary) -> dict[str, Any]:
    """将批量测试汇总结果转换为 JSON 报告字典。"""
    return {
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


def _summary_to_markdown(summary: TestSummary) -> str:
    """
    将批量测试汇总结果转换为 Markdown 报告文本。

    包含汇总概览与逐用例详情表格，表格中的特殊字符（竖线/换行）会被
    转义，防止用例可控内容破坏报告结构。
    """
    pass_rate: float = summary.passed / max(summary.total, 1) * 100
    lines: list[str] = [
        "# 批量测试报告",
        "",
        f"- **开始时间**: {summary.started_at}",
        f"- **总用例**: {summary.total}",
        f"- **通过**: {summary.passed} ✅",
        f"- **失败**: {summary.failed} ❌",
        f"- **通过率**: {pass_rate:.1f}%",
        f"- **总耗时**: {summary.total_duration:.1f} 秒",
        "",
        "## 用例详情",
        "",
        "| # | 状态 | 目标 | 描述 | 标签 | 预期状态 | 实际状态 | 步数 | 成功率 | 耗时 | 错误 |",
        "|---|------|------|------|------|----------|----------|------|--------|------|------|",
    ]

    for i, r in enumerate(summary.results, start=1):
        icon: str = "✅" if r.passed else "❌"
        goal: str = (r.test_case.goal or "").replace("|", "｜").replace("\r\n", "<br>").replace("\n", "<br>")
        desc: str = (r.test_case.description or "").replace("|", "｜").replace("\r\n", "<br>").replace("\n", "<br>")
        error: str = (r.error_message or "").replace("|", "｜").replace("\r\n", "<br>").replace("\n", "<br>")
        if len(error) > 80:
            error = error[:80] + "…"
        lines.append(
            f"| {i} | {icon} | {goal} | {desc} | {','.join(r.test_case.tags)} | "
            f"{r.test_case.expected_status} | {r.status} | {r.steps_executed} | "
            f"{r.success_rate:.0%} | {r.duration_seconds:.1f}s | {error} |"
        )

    return "\n".join(lines) + "\n"


def _summary_to_html(summary: TestSummary) -> str:
    """
    将批量测试汇总结果转换为自包含的 HTML 报告文本。

    所有用例可控内容均经过 HTML 转义，防止注入破坏页面结构。
    """
    pass_rate: float = summary.passed / max(summary.total, 1) * 100
    rows: list[str] = []
    for i, r in enumerate(summary.results, start=1):
        status_badge: str = '<span class="pass">✅ 通过</span>' if r.passed else '<span class="fail">❌ 失败</span>'
        rows.append(
            "<tr>"
            f"<td>{i}</td>"
            f"<td>{status_badge}</td>"
            f"<td>{html_lib.escape(r.test_case.goal)}</td>"
            f"<td>{html_lib.escape(r.test_case.description)}</td>"
            f"<td>{html_lib.escape(','.join(r.test_case.tags))}</td>"
            f"<td>{html_lib.escape(r.test_case.expected_status)}</td>"
            f"<td>{html_lib.escape(r.status)}</td>"
            f"<td>{r.steps_executed}</td>"
            f"<td>{r.success_rate:.0%}</td>"
            f"<td>{r.duration_seconds:.1f}s</td>"
            f"<td>{html_lib.escape(r.error_message)}</td>"
            "</tr>"
        )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>批量测试报告</title>
<style>
  body {{ font-family: "Microsoft YaHei", sans-serif; margin: 24px; color: #333; }}
  h1 {{ border-bottom: 2px solid #4a90d9; padding-bottom: 8px; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 16px; }}
  th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; font-size: 14px; }}
  th {{ background: #f2f7fc; }}
  .pass {{ color: #1a7f37; font-weight: bold; }}
  .fail {{ color: #cf222e; font-weight: bold; }}
  .summary {{ display: flex; gap: 24px; margin: 16px 0; flex-wrap: wrap; }}
  .card {{ background: #f8f9fa; border: 1px solid #e0e0e0; border-radius: 8px; padding: 12px 20px; }}
</style>
</head>
<body>
<h1>批量测试报告</h1>
<div class="summary">
  <div class="card"><strong>总用例</strong>: {summary.total}</div>
  <div class="card"><strong>通过</strong>: {summary.passed}</div>
  <div class="card"><strong>失败</strong>: {summary.failed}</div>
  <div class="card"><strong>通过率</strong>: {pass_rate:.1f}%</div>
  <div class="card"><strong>总耗时</strong>: {summary.total_duration:.1f} 秒</div>
  <div class="card"><strong>开始时间</strong>: {html_lib.escape(summary.started_at)}</div>
</div>
<table>
  <thead><tr><th>#</th><th>状态</th><th>目标</th><th>描述</th><th>标签</th><th>预期状态</th><th>实际状态</th><th>步数</th><th>成功率</th><th>耗时</th><th>错误</th></tr></thead>
  <tbody>
  {''.join(rows)}
  </tbody>
</table>
</body>
</html>
"""


def save_batch_report(summary: TestSummary, args: argparse.Namespace) -> str:
    """
    按指定格式保存批量测试报告。

    报告输出到 <report-dir>/batch/<时间戳>/batch_test_report.<ext>，
    默认 report-dir 为 reports。

    参数
    ----------
    summary : TestSummary
        批量测试汇总结果。
    args : argparse.Namespace
        命令行参数（format_report / report_dir）。

    返回
    -------
    str
        实际写入的报告文件路径。
    """
    fmt: str = (args.format_report or "json").lower()
    base_dir: Path = Path(args.report_dir or "reports") / "batch"
    ts: str = datetime.now().strftime("%y_%m_%d_%H_%M_%S")
    out_dir: Path = base_dir / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    ext: str = fmt if fmt in REPORT_FORMATS else "json"
    output_path: Path = out_dir / f"batch_test_report.{ext}"

    if fmt == "json":
        output_path.write_text(
            json.dumps(_summary_to_json(summary), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    elif fmt == "md":
        output_path.write_text(_summary_to_markdown(summary), encoding="utf-8")
    else:
        output_path.write_text(_summary_to_html(summary), encoding="utf-8")

    logger.info("批量测试报告已保存: %s", output_path)
    return str(output_path)


def run_single_task(args: argparse.Namespace) -> int:
    """
    单任务执行入口（run 子命令或向后兼容的默认行为）。

    参数
    ----------
    args : argparse.Namespace
        命令行参数。

    返回
    -------
    int
        退出码：0 表示任务成功或部分成功，1 表示任务失败或出错，2 表示参数缺失。
    """
    if not args.goal:
        print(
            "[ERROR] 未指定任务目标，请使用 -g/--goal 参数，例如: "
            'python -m mobile_automation.main -g "打开设置"',
            file=sys.stderr,
        )
        return 2

    dm: Optional[DeviceManager] = None
    try:
        orchestrator, dm = build_app(args)
        context: TaskContext = run_task(orchestrator, args.goal, args.max_steps)

        if context.status.value in ("completed", "partially_completed", "aborted"):
            logger.info("任务最终状态: %s，退出码 0", context.status.value)
            return 0
        logger.warning("任务最终状态: %s，退出码 1", context.status.value)
        return 1

    except Exception as exc:
        logger.critical("框架运行异常: %s", exc, exc_info=True)
        print(f"\n[ERROR] 框架运行异常: {exc}", file=sys.stderr)
        return 1
    finally:
        if dm:
            dm.disconnect()
            logger.info("设备连接已断开")


def run_batch_tests(args: argparse.Namespace) -> int:
    """
    批量测试执行入口（test 子命令）。

    流程：构建模块 -> 加载用例 -> 标签筛选 -> 批量执行 -> 保存报告。

    参数
    ----------
    args : argparse.Namespace
        命令行参数。

    返回
    -------
    int
        退出码：0 表示全部通过，1 表示存在失败用例或出错，2 表示参数缺失。
    """
    if not args.cases:
        print(
            "[ERROR] 未指定测试用例文件路径，用法示例: "
            "python -m mobile_automation.main test ./examples/test_cases.json",
            file=sys.stderr,
        )
        return 2

    dm: Optional[DeviceManager] = None
    try:
        orchestrator, dm = build_app(args)
        runner: BatchTestRunner = BatchTestRunner(orchestrator)
        cases: list[TestCase] = load_cases(args.cases)

        if args.filter:
            cases = [c for c in cases if args.filter in c.tags]
            logger.info("按标签筛选 '%s'，剩余 %d 个用例", args.filter, len(cases))
            if not cases:
                logger.warning("没有匹配标签 '%s' 的测试用例", args.filter)
                print(f"[WARN] 没有匹配标签 '{args.filter}' 的测试用例", file=sys.stderr)
                return 1

        summary: TestSummary = runner.run_all(cases, stop_on_failure=args.stop_on_failure)

        report_path: str = save_batch_report(summary, args)
        if report_path:
            print(f"批量测试报告已保存: {report_path}")

        if summary.failed == 0:
            logger.info("批量测试全部通过，退出码 0")
            return 0
        logger.warning("批量测试存在失败用例，退出码 1")
        return 1

    except Exception as exc:
        logger.critical("批量测试运行异常: %s", exc, exc_info=True)
        print(f"\n[ERROR] 批量测试运行异常: {exc}", file=sys.stderr)
        return 1
    finally:
        if dm:
            dm.disconnect()
            logger.info("设备连接已断开")


def main() -> int:
    """
    主入口函数。

    解析命令行参数并分发到对应执行入口：
    - test 子命令 -> run_batch_tests（批量测试）
    - run 子命令或无子命令 -> run_single_task（单任务执行）

    返回
    -------
    int
        退出码：0 表示成功，1 表示执行失败，2 表示参数缺失。
    """
    args: argparse.Namespace = parse_args()

    command: str = args.command or "run"
    if command == "test":
        return run_batch_tests(args)
    return run_single_task(args)


if __name__ == "__main__":
    _setup_stdout()
    sys.exit(main())
