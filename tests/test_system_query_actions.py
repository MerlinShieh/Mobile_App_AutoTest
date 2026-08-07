"""系统级查询动作闭环测试（v1.5 新增能力）。

覆盖 ADB 系统级查询（短信/剪贴板/通知/通话状态）接入 LLM 决策闭环的完整链路：
- LLM 响应解析：4 个新 action_type 可被 parse_llm_response 解析，sms_type/limit 参数透传。
- TaskContext：system_query_results 字段默认空列表、可追加。
- ExecutionPipeline：查询动作无需验证页面变化，直接标记成功。
- DecisionEngine：decide_action 将 task_context.system_query_results 透传给 build。
"""

import pytest

from mobile_automation.core.pipelines.decision_engine import DecisionEngine
from mobile_automation.core.pipelines.execution_pipeline import ExecutionPipeline
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


class TestParseSystemQueryActions:
    """LLM 响应解析：系统查询类动作可被解析。"""

    def test_parse_read_sms_with_params(self):
        """read_sms 可解析，sms_type/limit 参数透传到 ActionParams。"""
        response = (
            '<answer>{"action_type": "read_sms", '
            '"params": {"sms_type": "inbox", "limit": 5}, '
            '"reason": "读取短信验证码"}</answer>'
        )
        action = DecisionEngine.parse_llm_response(response)
        assert action.action_type == ActionType.READ_SMS
        assert action.params.sms_type == "inbox"
        assert action.params.limit == 5

    def test_parse_get_clipboard(self):
        """get_clipboard 可解析，无参数。"""
        response = '{"action_type": "get_clipboard", "params": {}, "reason": "读取剪贴板"}'
        action = DecisionEngine.parse_llm_response(response)
        assert action.action_type == ActionType.GET_CLIPBOARD
        assert action.params.sms_type is None
        assert action.params.limit is None

    def test_parse_get_notifications_with_limit(self):
        """get_notifications 可解析，limit 参数透传。"""
        response = (
            '{"action_type": "get_notifications", '
            '"params": {"limit": 10}, "reason": "查看通知验证码"}'
        )
        action = DecisionEngine.parse_llm_response(response)
        assert action.action_type == ActionType.GET_NOTIFICATIONS
        assert action.params.limit == 10

    def test_parse_get_call_state(self):
        """get_call_state 可解析，无参数。"""
        response = '{"action_type": "get_call_state", "params": {}, "reason": "检测来电"}'
        action = DecisionEngine.parse_llm_response(response)
        assert action.action_type == ActionType.GET_CALL_STATE

    def test_parse_all_query_types_enum_mapping(self):
        """4 个新类型均通过 ActionType 枚举映射（无白名单拦截）。"""
        for value in ("read_sms", "get_clipboard", "get_notifications", "get_call_state"):
            assert ActionType(value).value == value


class TestTaskContextQueryResults:
    """TaskContext.system_query_results 字段行为。"""

    def test_default_empty_list(self):
        """默认 system_query_results 为空列表（不共享可变默认值）。"""
        ctx1 = TaskContext(task_id="a", user_goal="g")
        ctx2 = TaskContext(task_id="b", user_goal="g")
        assert ctx1.system_query_results == []
        assert ctx2.system_query_results == []
        ctx1.system_query_results.append("read_sms: 验证码")
        assert ctx2.system_query_results == []

    def test_append_works(self):
        """列表可直接追加（由编排层维护）。"""
        ctx = TaskContext(task_id="a", user_goal="g")
        ctx.system_query_results.append("get_clipboard: 内容")
        assert ctx.system_query_results == ["get_clipboard: 内容"]


class TestExecutionPipelineQueryActions:
    """查询动作无需页面变化验证，直接成功。"""

    def test_read_sms_direct_success_no_recapture(self, mocker, mock_device_manager, mock_perception):
        """READ_SMS 执行后直接标记成功，不做二次感知。"""
        pipeline = ExecutionPipeline(
            device_manager=mock_device_manager,
            perception=mock_perception,
        )
        ui_tree = _make_ui_tree()
        perceptual = _make_perceptual(ui_tree, mocker)
        record = StepRecord(
            step_index=1,
            action=Action(ActionType.READ_SMS, ActionParams()),
            status=StepStatus.RUNNING,
        )

        done = pipeline.verify_and_finalize(1, perceptual, record)

        assert done is True
        assert record.status == StepStatus.SUCCESS
        mock_perception.capture_with_ui_tree.assert_not_called()

    def test_get_call_state_direct_success(self, mocker, mock_device_manager, mock_perception):
        """GET_CALL_STATE 执行后直接标记成功。"""
        pipeline = ExecutionPipeline(
            device_manager=mock_device_manager,
            perception=mock_perception,
        )
        ui_tree = _make_ui_tree()
        perceptual = _make_perceptual(ui_tree, mocker)
        record = StepRecord(
            step_index=1,
            action=Action(ActionType.GET_CALL_STATE, ActionParams()),
            status=StepStatus.RUNNING,
        )

        done = pipeline.verify_and_finalize(1, perceptual, record)

        assert done is True
        assert record.status == StepStatus.SUCCESS


class TestDecisionEngineQueryPropagation:
    """decide_action 将 system_query_results 透传给 build。"""

    def test_query_results_passed_to_builder(self, mocker, mock_device_manager, mock_llm_service):
        """验证 build 收到 task_context.system_query_results。"""
        mock_builder = mocker.MagicMock()
        mock_builder.build.return_value = []
        mock_llm_service.chat.return_value = '{"action_type": "terminate", "params": {}, "reason": "完成"}'

        engine = DecisionEngine(
            device_manager=mock_device_manager,
            llm_service=mock_llm_service,
            decision_builder=mock_builder,
        )
        ui_tree = _make_ui_tree()
        perceptual = _make_perceptual(ui_tree, mocker)
        context = TaskContext(task_id="t", user_goal="读取验证码")
        context.system_query_results.append("read_sms: 验证码 123456")

        engine.decide_action(perceptual, context, attempt=1)

        assert mock_builder.build.call_count >= 1
        kwargs = mock_builder.build.call_args.kwargs
        assert kwargs["system_query_results"] == ["read_sms: 验证码 123456"]

    def test_query_results_empty_passed_as_list(self, mocker, mock_device_manager, mock_llm_service):
        """无查询结果时透传空列表（build 内部不注入，保持旧行为）。"""
        mock_builder = mocker.MagicMock()
        mock_builder.build.return_value = []
        mock_llm_service.chat.return_value = '{"action_type": "terminate", "params": {}, "reason": "完成"}'

        engine = DecisionEngine(
            device_manager=mock_device_manager,
            llm_service=mock_llm_service,
            decision_builder=mock_builder,
        )
        ui_tree = _make_ui_tree()
        perceptual = _make_perceptual(ui_tree, mocker)
        context = TaskContext(task_id="t", user_goal="打开设置")

        engine.decide_action(perceptual, context, attempt=1)

        kwargs = mock_builder.build.call_args.kwargs
        assert kwargs["system_query_results"] == []
