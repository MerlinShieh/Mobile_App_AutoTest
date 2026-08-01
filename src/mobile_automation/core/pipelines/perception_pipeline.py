"""感知流水线 —— PerceptionPipeline。

负责单步执行中的感知环节：
  1. 调用 ScreenCapture 双通道感知（截图 + UI 树）。
  2. 归档操作前的截图、原始 XML 和结构化摘要。
  3. 弹窗检测与自动处理（失败达上限时放行给 LLM 决策）。

原为 StepRunner 的内部方法（_perceive_with_popup_handling /
_archive_screenshot / _archive_xml_and_summary），拆分后独立成模块。
"""

import base64
from typing import Optional

from ...logger import get_logger
from ...device.device_manager import DeviceManager
from ...models.enums import StepStatus
from ...models.perception import PerceptualResult, UITree
from ...models.task import StepRecord
from ...perception.screen_capture import ScreenCapture
from ...popup.popup_handler import PopupHandler
from ...reporting.archiver import DataArchiver

logger = get_logger(__name__)


class PerceptionPipeline:
    """感知 + 弹窗处理流水线。"""

    def __init__(
        self,
        device_manager: DeviceManager,
        perception: ScreenCapture,
        popup_handler: PopupHandler,
        archiver: Optional[DataArchiver] = None,
    ) -> None:
        self._dm: DeviceManager = device_manager
        self._perception: ScreenCapture = perception
        self._popup_handler: PopupHandler = popup_handler
        self._archiver: Optional[DataArchiver] = archiver
        logger.debug("PerceptionPipeline 初始化完成")

    def set_archiver(self, archiver: DataArchiver) -> None:
        """切换归档器（每次任务执行前由编排层调用）。"""
        self._archiver = archiver

    def perceive_with_popup_handling(
        self,
        step_index: int,
        record: StepRecord,
    ) -> PerceptualResult:
        """
        感知当前页面并处理弹窗。

        1. 调用 ScreenCapture 获取截图和 UI 树。
        2. 归档操作前的截图和 XML。
        3. 检测弹窗，有则处理后设置 record.status = RETRYING。

        返回
        -------
        PerceptualResult
            感知结果。
        """
        perceptual: PerceptualResult = self._perception.capture_with_ui_tree()

        self._archive_screenshot(step_index, perceptual, after=False)
        if perceptual.ui_tree:
            self._archive_xml_and_summary(step_index, perceptual.ui_tree)

        popup_result = self._popup_handler.detect(perceptual.ui_tree)  # type: ignore[arg-type]  # detect 内部有 not tree 防御
        if popup_result and popup_result.detected:
            if not popup_result.auto_handlable:
                # 弹窗自动处理已达失败上限（或类型不匹配），
                # 不再重试感知死循环，放行给 LLM 决策处理
                logger.warning(
                    "Step %d 弹窗自动处理失败次数过多，放行给 LLM 决策: type=%s",
                    step_index, popup_result.popup_type.value,
                )
                return perceptual

            handled = self._popup_handler.handle(popup_result)
            if handled:
                logger.info("Step %d 弹窗已处理，重新感知并重试", step_index)
            else:
                logger.warning("Step %d 弹窗处理未完成，重新感知", step_index)
            record.status = StepStatus.RETRYING

        return perceptual

    def _archive_screenshot(self, step_index: int, perceptual: PerceptualResult, after: bool) -> None:
        """
        将截图通过归档器保存到本地文件。

        参数
        ----------
        step_index : int
            步骤序号。
        perceptual : PerceptualResult
            包含 Base64 截图的感知结果。
        after : bool
            是否为操作后的截图。
        """
        if self._archiver is None:
            return
        try:
            raw = base64.b64decode(perceptual.screenshot_base64)
            self._archiver.save_screenshot(step_index, raw, after=after)
        except Exception as exc:
            logger.warning("截图归档失败: %s", exc)

    def _archive_xml_and_summary(self, step_index: int, ui_tree: UITree) -> None:
        """
        将原始 XML 和结构化摘要通过归档器保存到本地文件。

        参数
        ----------
        step_index : int
            步骤序号。
        ui_tree : UITree
            包含 XML 和摘要的 UI 树数据。
        """
        if self._archiver is None:
            return
        try:
            if ui_tree.raw_xml:
                self._archiver.save_raw_xml(step_index, ui_tree.raw_xml)
            if ui_tree.structured_summary:
                self._archiver.save_structured_summary(step_index, ui_tree.structured_summary)
        except Exception as exc:
            logger.warning("XML/摘要归档失败: %s", exc)
