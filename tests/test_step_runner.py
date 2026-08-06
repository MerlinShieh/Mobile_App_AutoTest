"""单步执行引擎模块测试。

使用 mock 协作者测试 StepRunner 的执行闭环，包括弹窗处理、
LLM 决策、element_id 解析和重试逻辑。
"""

import pytest

from mobile_automation.core.step_runner import StepRunner
from mobile_automation.models.action import Action, ActionParams
from mobile_automation.models.enums import ActionType, StepStatus
from mobile_automation.models.perception import UINode, UITree
from mobile_automation.models.task import TaskContext


class TestStepRunner:
    """测试 StepRunner 的单步执行闭环。"""

    def test_run_step_successful(self, mocker, mock_device_manager, mock_perception, mock_llm_service):
        """验证成功执行一步操作。"""
        mock_popup = mocker.MagicMock()
        mock_popup.detect.return_value = None

        mock_executor = mocker.MagicMock()
        mock_executor.execute.return_value = True

        ui_tree = UITree(
            root=UINode(),
            local_index={"#1": UINode(element_id="#1", bounds=(0, 0, 50, 50))},
            structured_summary="#1 clickable 按钮",
        )
        mock_perception.capture_with_ui_tree.return_value = mocker.MagicMock(
            screenshot_base64="b64",
            screenshot_format="jpeg",
            ui_tree=ui_tree,
            page_stable=True,
            change_score=0.0,
            timestamp_ms=1000,
        )

        runner = StepRunner(
            device_manager=mock_device_manager,
            perception=mock_perception,
            popup_handler=mock_popup,
            llm_service=mock_llm_service,
            action_executor=mock_executor,
        )

        context = TaskContext(task_id="test-001", user_goal="测试操作")
        record = runner.run_step(1, context)

        assert record.status == StepStatus.SUCCESS
        assert record.step_index == 1

    def test_run_step_max_retries_zero(self, mocker, mock_device_manager, mock_perception, mock_llm_service):
        """验证 max_retries_per_step=0 时步骤直接标记为 FAILED 而非 PENDING。"""
        mocker.patch("mobile_automation.core.step_runner.settings.execution.max_retries_per_step", 0)
        mock_popup = mocker.MagicMock()
        mock_popup.detect.return_value = None

        mock_executor = mocker.MagicMock()
        mock_executor.execute.return_value = True

        runner = StepRunner(
            device_manager=mock_device_manager,
            perception=mock_perception,
            popup_handler=mock_popup,
            llm_service=mock_llm_service,
            action_executor=mock_executor,
        )

        context = TaskContext(task_id="test-001", user_goal="测试操作")
        record = runner.run_step(1, context)

        assert record.status == StepStatus.FAILED
        assert "max_retries_per_step" in record.error_message

    def test_run_step_popup_handled(self, mocker, mock_device_manager, mock_perception, mock_llm_service):
        """验证弹窗被处理后重试直到成功。"""
        mock_popup = mocker.MagicMock()
        mock_popup_detect_result = mocker.MagicMock()
        mock_popup_detect_result.detected = True
        mock_popup.detect.side_effect = [mock_popup_detect_result, None]
        mock_popup.handle.return_value = True

        mock_executor = mocker.MagicMock()
        mock_executor.execute.return_value = True

        ui_tree = UITree(
            root=UINode(),
            local_index={"#1": UINode(element_id="#1", bounds=(0, 0, 50, 50))},
            structured_summary="#1 clickable",
        )
        mock_perception.capture_with_ui_tree.return_value = mocker.MagicMock(
            screenshot_base64="b64",
            screenshot_format="jpeg",
            ui_tree=ui_tree,
            page_stable=True,
            change_score=0.0,
            timestamp_ms=1000,
        )

        runner = StepRunner(
            device_manager=mock_device_manager,
            perception=mock_perception,
            popup_handler=mock_popup,
            llm_service=mock_llm_service,
            action_executor=mock_executor,
        )

        context = TaskContext(task_id="test-001", user_goal="测试")
        record = runner.run_step(1, context)

        assert record.status == StepStatus.SUCCESS
        assert mock_popup.handle.called

    def test_run_step_popup_not_auto_handlable_releases_to_llm(
        self, mocker, mock_device_manager, mock_perception, mock_llm_service
    ):
        """验证弹窗自动处理不可行时放行给 LLM 决策，不再死循环重试。"""
        mock_popup = mocker.MagicMock()
        mock_popup_detect_result = mocker.MagicMock()
        mock_popup_detect_result.detected = True
        mock_popup_detect_result.auto_handlable = False
        mock_popup.detect.return_value = mock_popup_detect_result

        mock_executor = mocker.MagicMock()
        mock_executor.execute.return_value = True

        ui_tree = UITree(
            root=UINode(),
            local_index={"#1": UINode(element_id="#1", bounds=(0, 0, 50, 50))},
            structured_summary="#1 clickable",
        )
        mock_perception.capture_with_ui_tree.return_value = mocker.MagicMock(
            screenshot_base64="b64",
            screenshot_format="jpeg",
            ui_tree=ui_tree,
            page_stable=True,
            change_score=0.0,
            timestamp_ms=1000,
        )

        runner = StepRunner(
            device_manager=mock_device_manager,
            perception=mock_perception,
            popup_handler=mock_popup,
            llm_service=mock_llm_service,
            action_executor=mock_executor,
        )

        context = TaskContext(task_id="test-001", user_goal="测试")
        record = runner.run_step(1, context)

        assert mock_popup.handle.called is False
        assert record.status == StepStatus.SUCCESS

    def test_run_step_popup_with_preset_action_not_auto_handlable(
        self, mocker, mock_device_manager, mock_perception, mock_llm_service
    ):
        """验证带预置 Action 时弹窗不可自动处理仍放行，不进入死循环。"""
        mock_popup = mocker.MagicMock()
        mock_popup_detect_result = mocker.MagicMock()
        mock_popup_detect_result.detected = True
        mock_popup_detect_result.auto_handlable = False
        mock_popup.detect.return_value = mock_popup_detect_result

        mock_executor = mocker.MagicMock()
        mock_executor.execute.return_value = True

        ui_tree = UITree(
            root=UINode(),
            local_index={"#1": UINode(element_id="#1", bounds=(0, 0, 50, 50))},
            structured_summary="#1 clickable",
        )
        mock_perception.capture_with_ui_tree.return_value = mocker.MagicMock(
            screenshot_base64="b64",
            screenshot_format="jpeg",
            ui_tree=ui_tree,
            page_stable=True,
            change_score=0.0,
            timestamp_ms=1000,
        )

        runner = StepRunner(
            device_manager=mock_device_manager,
            perception=mock_perception,
            popup_handler=mock_popup,
            llm_service=mock_llm_service,
            action_executor=mock_executor,
        )

        preset = Action(ActionType.BACK, ActionParams(), reason="预置返回操作")
        context = TaskContext(task_id="test-001", user_goal="测试")
        record = runner.run_step(1, context, preset_action=preset)

        assert mock_popup.handle.called is False
        assert record.status == StepStatus.SUCCESS
        assert record.action.action_type == ActionType.BACK

    def test_run_step_with_preset_action(self, mocker, mock_device_manager, mock_perception, mock_llm_service):
        """验证预置 Action 时跳过 LLM 决策。"""
        mock_popup = mocker.MagicMock()
        mock_popup.detect.return_value = None

        mock_executor = mocker.MagicMock()
        mock_executor.execute.return_value = True

        ui_tree = UITree(
            root=UINode(),
            local_index={"#1": UINode(element_id="#1", bounds=(0, 0, 50, 50))},
            structured_summary="#1 clickable",
        )
        mock_perception.capture_with_ui_tree.return_value = mocker.MagicMock(
            screenshot_base64="b64",
            screenshot_format="jpeg",
            ui_tree=ui_tree,
            page_stable=True,
            change_score=0.0,
            timestamp_ms=1000,
        )

        runner = StepRunner(
            device_manager=mock_device_manager,
            perception=mock_perception,
            popup_handler=mock_popup,
            llm_service=mock_llm_service,
            action_executor=mock_executor,
        )

        preset = Action(ActionType.BACK, ActionParams(), reason="预置返回操作")
        context = TaskContext(task_id="test-001", user_goal="测试")
        record = runner.run_step(1, context, preset_action=preset)

        assert record.status == StepStatus.SUCCESS
        assert record.action.action_type == ActionType.BACK
        mock_llm_service.chat.assert_not_called()

    def test_run_step_popup_persistent_exhausts_attempts_failed(
        self, mocker, mock_device_manager, mock_perception, mock_llm_service
    ):
        """验证弹窗持续存在直至 attempt 耗尽时，步骤以 FAILED 终态返回（非 RETRYING）。

        弹窗重试不计入 retry_count（保持既有设计），但 attempt 耗尽后必须补齐 FAILED
        终态，避免步骤以 RETRYING 非终态泄漏到编排层。
        """
        mocker.patch("mobile_automation.core.step_runner.settings.execution.max_retries_per_step", 2)

        popup_result = mocker.MagicMock()
        popup_result.detected = True
        popup_result.auto_handlable = True
        popup_result.popup_type.value = "permission"
        mock_popup = mocker.MagicMock()
        mock_popup.detect.return_value = popup_result
        mock_popup.handle.return_value = True

        mock_executor = mocker.MagicMock()
        mock_executor.execute.return_value = True

        ui_tree = UITree(
            root=UINode(),
            local_index={"#1": UINode(element_id="#1", bounds=(0, 0, 50, 50))},
            structured_summary="#1 clickable",
        )
        mock_perception.capture_with_ui_tree.return_value = mocker.MagicMock(
            screenshot_base64="b64",
            screenshot_format="jpeg",
            ui_tree=ui_tree,
            page_stable=True,
            change_score=0.0,
            timestamp_ms=1000,
        )

        runner = StepRunner(
            device_manager=mock_device_manager,
            perception=mock_perception,
            popup_handler=mock_popup,
            llm_service=mock_llm_service,
            action_executor=mock_executor,
        )

        context = TaskContext(task_id="test-001", user_goal="测试")
        record = runner.run_step(1, context)

        assert record.status == StepStatus.FAILED
        assert record.error_message
        assert "弹窗" in record.error_message
        # 弹窗重试不计入 retry_count（语义分离），耗尽后仅补齐终态
        assert record.retry_count == 0

    def test_run_step_executor_failure(self, mocker, mock_device_manager, mock_perception, mock_llm_service):
        """验证执行器失败时记录错误并重试。"""
        mock_popup = mocker.MagicMock()
        mock_popup.detect.return_value = None

        mock_executor = mocker.MagicMock()
        mock_executor.execute.side_effect = RuntimeError("执行失败")

        ui_tree = UITree(
            root=UINode(),
            local_index={"#1": UINode(element_id="#1", bounds=(0, 0, 50, 50))},
            structured_summary="#1 clickable",
        )
        mock_perception.capture_with_ui_tree.return_value = mocker.MagicMock(
            screenshot_base64="b64",
            screenshot_format="jpeg",
            ui_tree=ui_tree,
            page_stable=True,
            change_score=0.0,
            timestamp_ms=1000,
        )

        runner = StepRunner(
            device_manager=mock_device_manager,
            perception=mock_perception,
            popup_handler=mock_popup,
            llm_service=mock_llm_service,
            action_executor=mock_executor,
        )

        mocker.patch("mobile_automation.core.step_runner.settings.execution.max_retries_per_step", 1)
        context = TaskContext(task_id="test-001", user_goal="测试")
        record = runner.run_step(1, context)

        assert record.status == StepStatus.FAILED
        assert "执行失败" in record.error_message

    def test_parse_llm_response_json_block(self):
        """验证解析 ```json 代码块格式的 LLM 响应。"""
        response = '```json\n{"action_type": "click", "params": {"element_id": "#3"}, "reason": "测试"}\n```'
        action = StepRunner._parse_llm_response(response)
        assert action.action_type == ActionType.CLICK
        assert action.params.element_id == "#3"
        assert action.reason == "测试"

    def test_parse_llm_response_bare_json(self):
        """验证解析裸 JSON 格式的 LLM 响应。"""
        response = '{"action_type": "back", "params": {}, "reason": "返回"}'
        action = StepRunner._parse_llm_response(response)
        assert action.action_type == ActionType.BACK
        assert action.reason == "返回"

    def test_parse_llm_response_type_action(self):
        """验证解析 TYPE 操作的 LLM 响应。"""
        response = '{"action_type": "type", "params": {"element_id": "#1", "text": "hello"}, "reason": "输入文本"}'
        action = StepRunner._parse_llm_response(response)
        assert action.action_type == ActionType.TYPE
        assert action.params.element_id == "#1"
        assert action.params.text == "hello"

    def test_parse_llm_response_invalid(self):
        """验证解析无效 JSON 时抛出异常。"""
        response = "这不是有效的 JSON 响应"
        with pytest.raises(ValueError, match="LLM 响应解析失败"):
            StepRunner._parse_llm_response(response)

    def test_parse_llm_response_scroll(self):
        """验证解析 SCROLL 操作的 LLM 响应。"""
        response = '{"action_type": "scroll", "params": {"direction": "down"}, "reason": "向下滚动"}'
        action = StepRunner._parse_llm_response(response)
        assert action.action_type == ActionType.SCROLL
        assert action.params.direction == "down"
