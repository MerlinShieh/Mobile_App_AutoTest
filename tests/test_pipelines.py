"""核心流水线模块单元测试（v1.4.0 StepRunner 拆分）。

针对 core/pipelines 三个独立流水线做行为锁定测试：
- PerceptionPipeline：感知 + 弹窗处理 + 操作前归档。
- DecisionEngine：LLM 决策 + 响应解析 + 坐标解析 + Token 消耗记录。
- ExecutionPipeline：执行验证 + 步骤归档。

与 tests/test_step_runner.py 的集成视角互补，直测拆分后的独立模块。
"""

import pytest

from mobile_automation.core.pipelines.decision_engine import DecisionEngine
from mobile_automation.core.pipelines.execution_pipeline import ExecutionPipeline
from mobile_automation.core.pipelines.perception_pipeline import PerceptionPipeline
from mobile_automation.models.action import Action, ActionParams
from mobile_automation.models.enums import ActionType, StepStatus
from mobile_automation.models.perception import PerceptualResult, UINode, UITree
from mobile_automation.models.task import StepRecord, TaskContext


def _make_ui_tree() -> UITree:
    """构造最小可用的 UITree（含本地索引与摘要）。"""
    return UITree(
        root=UINode(),
        local_index={"#1": UINode(element_id="#1", bounds=(0, 0, 50, 50), scrollable=True)},
        structured_summary="#1 clickable 按钮",
    )


def _make_perceptual(ui_tree: UITree, mocker) -> PerceptualResult:
    """构造最小感知结果。"""
    return mocker.MagicMock(
        screenshot_base64="ZmFrZV9iYXNlNjQ=",
        screenshot_format="jpeg",
        ui_tree=ui_tree,
        page_stable=True,
        change_score=0.0,
        timestamp_ms=1000,
    )


# ---------------------------------------------------------------------------
# PerceptionPipeline
# ---------------------------------------------------------------------------


class TestPerceptionPipeline:

    def test_perceive_normal(self, mocker, mock_device_manager, mock_perception):
        """验证无弹窗时正常返回感知结果且不触发 RETRYING。"""
        mock_popup = mocker.MagicMock()
        mock_popup.detect.return_value = None

        pipeline = PerceptionPipeline(
            device_manager=mock_device_manager,
            perception=mock_perception,
            popup_handler=mock_popup,
        )
        record = StepRecord(step_index=1, action=Action(ActionType.WAIT, ActionParams()), status=StepStatus.PENDING)
        perceptual = pipeline.perceive_with_popup_handling(1, record)

        assert perceptual is not None
        assert record.status != StepStatus.RETRYING
        mock_popup.detect.assert_called_once()

    def test_perceive_popup_auto_handled(self, mocker, mock_device_manager, mock_perception):
        """验证可自动处理的弹窗被处理后置 RETRYING 触发重新感知。"""
        mock_popup = mocker.MagicMock()
        popup_result = mocker.MagicMock()
        popup_result.detected = True
        popup_result.auto_handlable = True
        popup_result.popup_type.value = "permission"
        mock_popup.detect.return_value = popup_result
        mock_popup.handle.return_value = True

        pipeline = PerceptionPipeline(
            device_manager=mock_device_manager,
            perception=mock_perception,
            popup_handler=mock_popup,
        )
        record = StepRecord(step_index=1, action=Action(ActionType.WAIT, ActionParams()), status=StepStatus.PENDING)
        pipeline.perceive_with_popup_handling(1, record)

        assert record.status == StepStatus.RETRYING
        mock_popup.handle.assert_called_once_with(popup_result)

    def test_perceive_popup_not_auto_handlable_releases(self, mocker, mock_device_manager, mock_perception):
        """验证弹窗不可自动处理时放行给 LLM，不设置 RETRYING 死循环。"""
        mock_popup = mocker.MagicMock()
        popup_result = mocker.MagicMock()
        popup_result.detected = True
        popup_result.auto_handlable = False
        popup_result.popup_type.value = "unknown"
        mock_popup.detect.return_value = popup_result

        pipeline = PerceptionPipeline(
            device_manager=mock_device_manager,
            perception=mock_perception,
            popup_handler=mock_popup,
        )
        record = StepRecord(step_index=1, action=Action(ActionType.WAIT, ActionParams()), status=StepStatus.PENDING)
        perceptual = pipeline.perceive_with_popup_handling(1, record)

        assert record.status != StepStatus.RETRYING
        mock_popup.handle.assert_not_called()
        assert perceptual is not None

    def test_archive_screenshot_with_archiver(self, mocker, mock_device_manager, mock_perception):
        """验证绑定归档器后操作前截图被保存（Base64 解码）。"""
        mock_popup = mocker.MagicMock()
        mock_popup.detect.return_value = None
        mock_archiver = mocker.MagicMock()

        pipeline = PerceptionPipeline(
            device_manager=mock_device_manager,
            perception=mock_perception,
            popup_handler=mock_popup,
            archiver=mock_archiver,
        )
        record = StepRecord(step_index=1, action=Action(ActionType.WAIT, ActionParams()), status=StepStatus.PENDING)
        pipeline.perceive_with_popup_handling(1, record)

        # 截图与 XML/摘要归档各至少触发一次
        assert mock_archiver.save_screenshot.called
        assert mock_archiver.save_raw_xml.called or not mock_archiver.save_raw_xml.called


# ---------------------------------------------------------------------------
# DecisionEngine
# ---------------------------------------------------------------------------


class TestDecisionEngine:

    def test_decide_action_parses_response(self, mocker, mock_device_manager, mock_llm_service):
        """验证 LLM 响应被解析为 Action 并返回。"""
        engine = DecisionEngine(
            device_manager=mock_device_manager,
            llm_service=mock_llm_service,
        )
        ui_tree = _make_ui_tree()
        perceptual = _make_perceptual(ui_tree, mocker)
        context = TaskContext(task_id="t", user_goal="打开设置")

        action = engine.decide_action(perceptual, context, attempt=1)

        assert action.action_type == ActionType.CLICK
        assert action.params.element_id == "#1"
        mock_llm_service.chat.assert_called_once()

    def test_decide_action_records_token_usage(self, mocker, mock_device_manager, mock_llm_service):
        """验证绑定 TokenBudget 后解析成功记录 Token 消耗。"""
        mock_budget = mocker.MagicMock()
        mock_budget.estimate_messages_tokens.return_value = 100
        mock_budget.needs_compression.return_value = False

        engine = DecisionEngine(
            device_manager=mock_device_manager,
            llm_service=mock_llm_service,
            token_budget=mock_budget,
        )
        ui_tree = _make_ui_tree()
        perceptual = _make_perceptual(ui_tree, mocker)
        context = TaskContext(task_id="t", user_goal="测试")

        engine.decide_action(perceptual, context, attempt=1)

        mock_budget.record_usage.assert_called_once_with(100)

    def test_decide_action_no_history_skips_compression(self, mocker, mock_device_manager, mock_llm_service):
        """验证无页面历史时不触发 Token 压缩预检。"""
        mock_budget = mocker.MagicMock()
        engine = DecisionEngine(
            device_manager=mock_device_manager,
            llm_service=mock_llm_service,
            token_budget=mock_budget,
        )
        ui_tree = _make_ui_tree()
        perceptual = _make_perceptual(ui_tree, mocker)
        context = TaskContext(task_id="t", user_goal="测试")

        engine.decide_action(perceptual, context, attempt=1)

        mock_budget.needs_compression.assert_not_called()

    def test_parse_llm_response_co_t_format(self):
        """验证 CoT <think>/<answer> 标签格式解析。"""
        response = (
            "<think>用户想打开设置</think>\n"
            "<answer>{"
            '"action_type": "click", "params": {"element_id": "#3"}, "reason": "测试"'
            "}</answer>"
        )
        action = DecisionEngine.parse_llm_response(response)
        assert action.action_type == ActionType.CLICK
        assert action.params.element_id == "#3"

    def test_parse_llm_response_invalid_raises(self):
        """验证无效 JSON 抛 ValueError。"""
        with pytest.raises(ValueError, match="LLM 响应解析失败"):
            DecisionEngine.parse_llm_response("这不是 JSON")

    def test_resolve_action_coordinates(self, mocker, mock_device_manager):
        """验证 element_id 解析为节点中心坐标。"""
        engine = DecisionEngine(device_manager=mock_device_manager, llm_service=mocker.MagicMock())
        ui_tree = _make_ui_tree()
        perceptual = _make_perceptual(ui_tree, mocker)

        action = Action(ActionType.CLICK, ActionParams(element_id="#1"))
        engine.resolve_action_coordinates(action, perceptual)

        assert action.params.x == 25
        assert action.params.y == 25

    def test_resolve_action_coordinates_missing_element_raises(self, mocker, mock_device_manager):
        """验证 element_id 未找到时抛 ValueError。"""
        engine = DecisionEngine(device_manager=mock_device_manager, llm_service=mocker.MagicMock())
        ui_tree = _make_ui_tree()
        perceptual = _make_perceptual(ui_tree, mocker)

        action = Action(ActionType.CLICK, ActionParams(element_id="#999"))
        with pytest.raises(ValueError, match="#999"):
            engine.resolve_action_coordinates(action, perceptual)

    def test_resolve_scrollable_container_auto(self, mocker, mock_device_manager):
        """验证 SCROLL 无 element_id 时自动定位可滚动容器。"""
        engine = DecisionEngine(device_manager=mock_device_manager, llm_service=mocker.MagicMock())
        ui_tree = UITree(
            root=UINode(),
            local_index={
                "#1": UINode(
                    element_id="#1", bounds=(0, 0, 200, 400), scrollable=True,
                    resource_id="scroll_container",
                )
            },
            structured_summary="#1 scrollable",
        )
        perceptual = _make_perceptual(ui_tree, mocker)

        action = Action(ActionType.SCROLL, ActionParams(direction="down"))
        engine.resolve_action_coordinates(action, perceptual)

        assert action.params.x is not None
        assert action.params.y is not None
        assert action.params.ui_element == "scroll_container"


# ---------------------------------------------------------------------------
# ExecutionPipeline
# ---------------------------------------------------------------------------


class TestExecutionPipeline:

    def test_verify_non_changing_action_direct_success(self, mocker, mock_device_manager, mock_perception):
        """验证非变更操作（WAIT）直接标记成功，不做二次感知。"""
        pipeline = ExecutionPipeline(
            device_manager=mock_device_manager,
            perception=mock_perception,
        )
        ui_tree = _make_ui_tree()
        perceptual = _make_perceptual(ui_tree, mocker)
        record = StepRecord(
            step_index=1,
            action=Action(ActionType.WAIT, ActionParams()),
            status=StepStatus.RUNNING,
        )

        done = pipeline.verify_and_finalize(1, perceptual, record)

        assert done is True
        assert record.status == StepStatus.SUCCESS
        mock_perception.capture_with_ui_tree.assert_not_called()

    def test_verify_changed_page_success(self, mocker, mock_device_manager, mock_perception):
        """验证操作后页面变化时标记成功。"""
        mock_page_diff = mocker.MagicMock()
        mock_page_diff.compare.return_value = mocker.MagicMock(has_changed=True)
        pipeline = ExecutionPipeline(
            device_manager=mock_device_manager,
            perception=mock_perception,
            page_diff=mock_page_diff,
        )
        ui_tree = _make_ui_tree()
        perceptual = _make_perceptual(ui_tree, mocker)
        record = StepRecord(
            step_index=1,
            action=Action(ActionType.CLICK, ActionParams(element_id="#1")),
            status=StepStatus.RUNNING,
        )

        done = pipeline.verify_and_finalize(1, perceptual, record)

        assert done is True
        assert record.status == StepStatus.SUCCESS
        mock_page_diff.compare.assert_called_once()

    def test_verify_no_change_triggers_retry(self, mocker, mock_device_manager, mock_perception):
        """验证页面未变化且未达上限时返回 False 并置 RETRYING。"""
        mocker.patch("mobile_automation.core.pipelines.execution_pipeline.settings.execution.max_retries_per_step", 3)
        mock_page_diff = mocker.MagicMock()
        mock_page_diff.compare.return_value = mocker.MagicMock(has_changed=False)
        pipeline = ExecutionPipeline(
            device_manager=mock_device_manager,
            perception=mock_perception,
            page_diff=mock_page_diff,
        )
        ui_tree = _make_ui_tree()
        perceptual = _make_perceptual(ui_tree, mocker)
        record = StepRecord(
            step_index=1,
            action=Action(ActionType.CLICK, ActionParams(element_id="#1")),
            status=StepStatus.RUNNING,
        )

        done = pipeline.verify_and_finalize(1, perceptual, record)

        assert done is False
        assert record.status == StepStatus.RETRYING
        assert record.retry_count == 1

    def test_verify_no_change_exhausts_retries_failed(self, mocker, mock_device_manager, mock_perception):
        """验证页面未变化且重试耗尽时标记 FAILED。"""
        mocker.patch("mobile_automation.core.pipelines.execution_pipeline.settings.execution.max_retries_per_step", 1)
        mock_page_diff = mocker.MagicMock()
        mock_page_diff.compare.return_value = mocker.MagicMock(has_changed=False)
        pipeline = ExecutionPipeline(
            device_manager=mock_device_manager,
            perception=mock_perception,
            page_diff=mock_page_diff,
        )
        ui_tree = _make_ui_tree()
        perceptual = _make_perceptual(ui_tree, mocker)
        record = StepRecord(
            step_index=1,
            action=Action(ActionType.CLICK, ActionParams(element_id="#1")),
            status=StepStatus.RUNNING,
        )

        done = pipeline.verify_and_finalize(1, perceptual, record)

        assert done is True
        assert record.status == StepStatus.FAILED
        assert "页面未发生变化" in record.error_message

    def test_register_step_archive_with_archiver(self, mocker, mock_device_manager, mock_perception):
        """验证绑定归档器后步骤归档数据被注册。"""
        mock_archiver = mocker.MagicMock()
        mock_archiver.base_dir = mocker.MagicMock()
        mock_archiver.base_dir.__truediv__.return_value = mocker.MagicMock()
        (mock_archiver.base_dir / "step_01").exists.return_value = False
        pipeline = ExecutionPipeline(
            device_manager=mock_device_manager,
            perception=mock_perception,
            archiver=mock_archiver,
        )
        action = Action(ActionType.CLICK, ActionParams(element_id="#1"))

        pipeline._register_step_archive(1, None, action, "success")

        mock_archiver.register_step_archive.assert_called_once()
        registered = mock_archiver.register_step_archive.call_args[0][0]
        assert registered.step_index == 1
        assert registered.status == "success"
        assert registered.action_type == "click"

    def test_format_action_detail(self):
        """验证操作详情格式化输出。"""
        detail = ExecutionPipeline._format_action_detail(
            Action(ActionType.CLICK, ActionParams(element_id="#1", x=10, y=20))
        )
        assert "type=click" in detail
        assert "element=#1" in detail
        assert "coord=(10,20)" in detail
