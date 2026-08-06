"""执行流水线 —— ExecutionPipeline。

负责单步执行中的执行验证与归档环节：
  1. 等待页面稳定 / 健康检查。
  2. 非变更操作（screenshot/wait/terminate/verify）直接标记成功。
  3. 其他操作二次感知并与操作前对比，判断页面是否变化。
  4. 无论成功或失败均注册步骤归档数据。

原为 StepRunner 的内部方法（_verify_and_finalize /
_register_step_archive / _format_action_detail），拆分后独立成模块。
"""

import time
from typing import Optional

from ...logger import get_logger
from ...config import settings
from ...device.device_manager import DeviceManager
from ...models.action import Action
from ...models.enums import ActionType, StepStatus
from ...models.perception import PerceptualResult
from ...models.task import StepRecord
from ...perception.page_diff import PageChangeDetector
from ...perception.screen_capture import ScreenCapture
from ...reporting.archiver import DataArchiver, StepArchiveData

logger = get_logger(__name__)


class ExecutionPipeline:
    """执行验证 + 步骤归档流水线。"""

    def __init__(
        self,
        device_manager: DeviceManager,
        perception: ScreenCapture,
        page_diff: Optional[PageChangeDetector] = None,
        archiver: Optional[DataArchiver] = None,
    ) -> None:
        self._dm: DeviceManager = device_manager
        self._perception: ScreenCapture = perception
        self._page_diff: PageChangeDetector = page_diff or PageChangeDetector()
        self._archiver: Optional[DataArchiver] = archiver
        logger.debug("ExecutionPipeline 初始化完成")

    def set_archiver(self, archiver: DataArchiver) -> None:
        """切换归档器（每次任务执行前由编排层调用）。"""
        self._archiver = archiver

    def verify_and_finalize(
        self,
        step_index: int,
        perceptual: PerceptualResult,
        record: StepRecord,
    ) -> bool:
        """
        验证操作执行后的页面变化并归档结果。

        对滑动操作先等待页面稳定，然后：
        - 非变更操作（screenshot / wait / terminate / verify）：直接标记成功。
        - 其他操作：二次感知并与操作前对比，判断页面是否变化。
        无论成功或失败均会执行归档。

        参数
        ----------
        step_index : int
            步骤序号。
        perceptual : PerceptualResult
            操作前的感知结果。
        record : StepRecord
            当前步骤记录，会被修改。

        返回
        -------
        bool
            True 表示步骤已完成（应退出重试循环），False 表示需重试。
        """
        if record.action.action_type in (
            ActionType.SWIPE, ActionType.SWIPE_POINT, ActionType.SCROLL,
        ):
            time.sleep(settings.execution.page_stable_poll_ms / 1000.0)

        self._dm.health_check()

        # 非变更操作：跳过验证，直接成功
        if record.action.action_type in (
            ActionType.SCREENSHOT, ActionType.WAIT, ActionType.TERMINATE, ActionType.VERIFY,
        ):
            record.page_summary = (
                perceptual.ui_tree.structured_summary
                if perceptual.ui_tree else ""
            )
            record.status = StepStatus.SUCCESS
            logger.info("Step %d 执行成功 (动作=%s 无需验证页面变化)",
                        step_index, record.action.action_type.value)
            self._archive_screenshot(step_index, perceptual, after=True)
            self._register_step_archive(
                step_index, perceptual, record.action, record.status.value,
            )
            return True

        # 二次感知 + 页面变化对比
        new_perceptual: PerceptualResult = self._perception.capture_with_ui_tree()
        self._archive_screenshot(step_index, new_perceptual, after=True)
        change_result = self._page_diff.compare(
            new_perceptual.ui_tree,  # type: ignore[arg-type]  # compare 内部处理首次调用无历史场景
            new_perceptual.screenshot_base64,
        )

        if change_result.has_changed:
            record.page_summary = (
                new_perceptual.ui_tree.structured_summary
                if new_perceptual.ui_tree else ""
            )
            record.status = StepStatus.SUCCESS
            logger.info("Step %d 执行成功", step_index)
            self._register_step_archive(
                step_index, perceptual, record.action, record.status.value,
            )
            return True

        record.retry_count += 1
        if record.retry_count >= settings.execution.max_retries_per_step:
            record.status = StepStatus.FAILED
            record.error_message = "操作后页面未发生变化"
            logger.warning("Step %d 失败: 操作后页面未变化", step_index)
            self._register_step_archive(
                step_index, perceptual, record.action, record.status.value,
                error=record.error_message,
            )
            return True

        record.status = StepStatus.RETRYING
        logger.info("Step %d 页面未变化，重试 (attempt %d/%d)",
                    step_index, record.retry_count, settings.execution.max_retries_per_step)
        return False

    def _archive_screenshot(self, step_index: int, perceptual: PerceptualResult, after: bool) -> None:
        """归档操作后截图（与 PerceptionPipeline 共用逻辑，需 Base64 解码）。

        注：PerceptionPipeline 中的 _archive_screenshot 负责操作前截图归档，
        本方法负责操作后（after=True）截图归档。两处均实现 Base64 → 文件保存。
        """
        if self._archiver is None:
            return
        try:
            import base64
            raw = base64.b64decode(perceptual.screenshot_base64)
            self._archiver.save_screenshot(step_index, raw, after=after)
        except Exception as exc:
            logger.warning("截图归档失败: %s", exc)

    def register_failed_step_archive(
        self,
        step_index: int,
        action: Action,
        status: str,
        error: str = "",
    ) -> None:
        """
        注册失败步骤的归档数据（公开接口，供编排层在异常/重试耗尽场景调用）。

        内部委托给 _register_step_archive，其中 perceptual 固定为 None
        （失败场景下无操作前感知结果）。

        参数
        ----------
        step_index : int
            步骤序号。
        action : Action
            执行的操作指令。
        status : str
            步骤状态。
        error : str
            错误信息。
        """
        self._register_step_archive(step_index, None, action, status, error=error)

    def _register_step_archive(
        self,
        step_index: int,
        perceptual: Optional[PerceptualResult],
        action: Action,
        status: str,
        error: str = "",
    ) -> None:
        """
        注册步骤的归档数据摘要。

        参数
        ----------
        step_index : int
            步骤序号。
        perceptual : Optional[PerceptualResult]
            操作前的感知结果。
        action : Action
            执行的操作指令。
        status : str
            步骤状态。
        error : str
            错误信息。
        """
        if self._archiver is None:
            return
        try:
            step_dir = self._archiver.base_dir / f"step_{step_index:02d}"
            archive = StepArchiveData(
                step_index=step_index,
                step_dir=step_dir,
                screenshot_path=step_dir / "screenshot.png",
                screenshot_after_path=step_dir / "screenshot_after.png"
                if (step_dir / "screenshot_after.png").exists() else None,
                xml_path=step_dir / "xml_raw.xml"
                if (step_dir / "xml_raw.xml").exists() else None,
                summary_path=step_dir / "summary.txt"
                if (step_dir / "summary.txt").exists() else None,
                llm_request_path=step_dir / "llm_request.json"
                if (step_dir / "llm_request.json").exists() else None,
                llm_response_path=step_dir / "llm_response.json"
                if (step_dir / "llm_response.json").exists() else None,
                action_type=action.action_type.value,
                action_detail=self._format_action_detail(action),
                status=status,
                error_message=error,
                reason=action.reason,
            )
            self._archiver.register_step_archive(archive)
        except Exception as exc:
            logger.warning("步骤归档注册失败: %s", exc)

    @staticmethod
    def _format_action_detail(action: Action) -> str:
        """格式化操作详情为字符串。"""
        parts = [f"type={action.action_type.value}"]
        if action.params.element_id:
            parts.append(f"element={action.params.element_id}")
        if action.params.text:
            parts.append(f"text={action.params.text}")
        if action.params.package_name:
            parts.append(f"package={action.params.package_name}")
        if action.params.direction:
            parts.append(f"direction={action.params.direction}")
        if action.params.x is not None:
            parts.append(f"coord=({action.params.x},{action.params.y})")
        return " | ".join(parts)
