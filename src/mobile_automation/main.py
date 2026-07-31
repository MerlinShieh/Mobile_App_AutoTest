"""
CLI 入口 —— 移动端 AI 自动化操作框架的命令行启动点。

提供命令行参数解析，支持指定任务描述、设备序列号、LLM 提供商和
最大步数等参数。启动时自动初始化日志系统、设备连接和所有核心模块。

设计参考:
- Open-AutoGLM: 交互模式（interactive mode）+ 简洁输出
- mobile-mcp: 结构化进度反馈

使用方式
--------
python -m src.mobile_automation.main --goal "打开设置，找到 Wi-Fi 选项"
python -m src.mobile_automation.main --goal "打开淘宝搜索手机" --serial xxxxxx
python -m src.mobile_automation.main --goal "..." --provider qwen --max-steps 50
"""

import argparse
import io
import sys
import time
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

logger = get_logger(__name__)

# 跨平台终端输出兼容：将 stdout 包装为 UTF-8 编码，容忍无法编码的字符
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer,
        encoding="utf-8",
        errors="replace",
        line_buffering=sys.stdout.line_buffering,
    )


def parse_args() -> argparse.Namespace:
    """
    解析命令行参数。

    支持以下参数：
    - goal / -g：任务描述（必需）
    - serial / -s：设备序列号（可选，默认自动选择）
    - provider / -p：LLM 提供商（可选，默认 qwen）
    - max-steps / -m：最大步数（可选，默认 30）

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
  python -m mobile_automation.main -g "打开淘宝搜索手机" -s 123456
  python -m mobile_automation.main -g "..." -p openai -m 50
        """,
    )
    parser.add_argument(
        "-g", "--goal",
        type=str,
        required=True,
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
    return parser.parse_args()


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


def main() -> int:
    """
    主入口函数。

    解析命令行参数 -> 初始化模块 -> 执行任务 -> 返回退出码。

    返回
    -------
    int
        退出码：0 表示任务成功或部分成功，1 表示任务失败或出错。
    """
    dm: Optional[DeviceManager] = None
    try:
        args: argparse.Namespace = parse_args()
        orchestrator, dm = build_app(args)
        context: TaskContext = run_task(orchestrator, args.goal, args.max_steps)

        if dm:
            dm.disconnect()
            logger.info("设备连接已断开")

        if context.status.value in ("completed", "partially_completed", "aborted"):
            logger.info("任务最终状态: %s，退出码 0", context.status.value)
            return 0
        else:
            logger.warning("任务最终状态: %s，退出码 1", context.status.value)
            return 1

    except Exception as exc:
        logger.critical("框架运行异常: %s", exc, exc_info=True)
        print(f"\n[ERROR] 框架运行异常: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
