"""任务编排器模块测试。

使用 mock 的 StepRunner 和 TokenBudgetManager 测试 TaskOrchestrator
的任务生命周期管理、死循环检测和超时检测功能。
"""

import pytest

from mobile_automation.config import settings
from mobile_automation.core.orchestrator import TaskOrchestrator
from mobile_automation.models.action import Action, ActionParams
from mobile_automation.models.enums import ActionType, StepStatus, TaskStatus
from mobile_automation.models.task import StepRecord, TaskContext


class TestTaskOrchestrator:
    """测试 TaskOrchestrator 的任务编排功能。"""

    def test_execute_task_successful_completion(self, mocker):
        """验证任务成功执行完成。"""
        mock_step_runner = mocker.MagicMock()
        mock_token_budget = mocker.MagicMock()

        mock_step_runner.run_step.return_value = StepRecord(
            step_index=1,
            action=Action(ActionType.CLICK, ActionParams(element_id="#1")),
            status=StepStatus.SUCCESS,
            page_summary="摘要1",
            retry_count=0,
        )

        orchestrator = TaskOrchestrator(
            step_runner=mock_step_runner,
            token_budget=mock_token_budget,
        )

        context = orchestrator.execute_task(user_goal="打开设置", max_steps=1)
        assert context.status == TaskStatus.COMPLETED
        assert context.current_step == 1
        assert len(context.steps) == 1

    def test_execute_task_failed_step(self, mocker):
        """验证步骤失败后任务标记为 FAILED。"""
        mock_step_runner = mocker.MagicMock()
        mock_token_budget = mocker.MagicMock()

        mock_step_runner.run_step.return_value = StepRecord(
            step_index=1,
            action=Action(ActionType.CLICK, ActionParams(element_id="#1")),
            status=StepStatus.FAILED,
            error_message="执行失败",
            retry_count=3,
        )

        orchestrator = TaskOrchestrator(
            step_runner=mock_step_runner,
            token_budget=mock_token_budget,
        )

        context = orchestrator.execute_task(user_goal="测试", max_steps=5)
        assert context.status == TaskStatus.FAILED

    def test_execute_task_popup_exhausted_failed_step(self, mocker):
        """验证弹窗重试耗尽的 FAILED 步骤（retry_count=0）触发任务失败。

        弹窗路径 retry_count 恒为 0，不满足旧的 retry_count >= max_retries 判定；
        步骤以 FAILED 终态返回时必须走失败处理路径终止任务，而非仅记 warning。
        """
        mock_step_runner = mocker.MagicMock()
        mock_token_budget = mocker.MagicMock()

        mock_step_runner.run_step.return_value = StepRecord(
            step_index=1,
            action=Action(ActionType.CLICK, ActionParams(element_id="#1")),
            status=StepStatus.FAILED,
            error_message="弹窗处理失败：重试耗尽后弹窗仍存在",
            retry_count=0,
        )

        orchestrator = TaskOrchestrator(
            step_runner=mock_step_runner,
            token_budget=mock_token_budget,
        )

        context = orchestrator.execute_task(user_goal="测试", max_steps=5)
        assert context.status == TaskStatus.FAILED
        assert context.current_step == 1

    def test_execute_task_loop_detection(self, mocker):
        """验证死循环检测后任务标记为 ABORTED。"""
        mock_step_runner = mocker.MagicMock()
        mock_token_budget = mocker.MagicMock()

        same_record = StepRecord(
            step_index=1,
            action=Action(ActionType.CLICK, ActionParams(element_id="#1")),
            status=StepStatus.SUCCESS,
            page_summary="相同页面",
        )
        mock_step_runner.run_step.return_value = same_record

        orchestrator = TaskOrchestrator(
            step_runner=mock_step_runner,
            token_budget=mock_token_budget,
        )

        mocker.patch("mobile_automation.core.orchestrator.settings.loop_detection.max_same_actions", 3)
        mocker.patch("mobile_automation.core.orchestrator.settings.loop_detection.max_history_size", 50)

        context = orchestrator.execute_task(user_goal="测试", max_steps=10)
        assert context.status == TaskStatus.ABORTED

    def test_execute_task_timeout(self, mocker):
        """验证超时后任务标记为 FAILED。"""
        mock_step_runner = mocker.MagicMock()
        mock_token_budget = mocker.MagicMock()

        mock_context = mocker.MagicMock()
        mock_context.is_completed.return_value = False
        mock_context.is_timeout.return_value = True
        mock_context.current_step = 0
        mock_context.max_steps = 30
        mock_context.status = TaskStatus.RUNNING
        mock_context.task_id = "test-timeout"
        mock_context.user_goal = "测试超时"
        mock_context.page_history = []
        mock_context.total_tokens_used = 0

        mocker.patch("mobile_automation.core.orchestrator.TaskContext", return_value=mock_context)

        orchestrator = TaskOrchestrator(
            step_runner=mock_step_runner,
            token_budget=mock_token_budget,
        )

        context = orchestrator.execute_task(user_goal="测试超时", max_steps=30)
        assert context.status == TaskStatus.FAILED

    def test_execute_task_max_duration_applied(self, mocker):
        """验证用例级 max_duration 生效：超时判断使用该值并终止任务。"""
        mock_step_runner = mocker.MagicMock()
        mock_token_budget = mocker.MagicMock()

        mock_context = mocker.MagicMock()
        mock_context.is_completed.return_value = False
        mock_context.is_timeout.return_value = True
        mock_context.current_step = 0
        mock_context.max_steps = 30
        mock_context.status = TaskStatus.RUNNING
        mock_context.task_id = "test-max-duration"
        mock_context.user_goal = "测试用例级超时"
        mock_context.page_history = []
        mock_context.total_tokens_used = 0

        mocker.patch("mobile_automation.core.orchestrator.TaskContext", return_value=mock_context)

        orchestrator = TaskOrchestrator(
            step_runner=mock_step_runner,
            token_budget=mock_token_budget,
        )

        context = orchestrator.execute_task(
            user_goal="测试用例级超时", max_steps=30, max_duration=10.0
        )
        assert context.status == TaskStatus.FAILED
        # 超时判断必须收到用例级 max_duration，而非全局配置
        mock_context.is_timeout.assert_called_once_with(max_duration_seconds=10.0)

    def test_execute_task_max_duration_none_falls_back_to_global(self, mocker):
        """验证 max_duration=None 时回退全局超时配置。"""
        mock_step_runner = mocker.MagicMock()
        mock_token_budget = mocker.MagicMock()

        mock_context = mocker.MagicMock()
        mock_context.is_completed.return_value = False
        mock_context.is_timeout.return_value = True
        mock_context.current_step = 0
        mock_context.max_steps = 30
        mock_context.status = TaskStatus.RUNNING
        mock_context.task_id = "test-global-timeout"
        mock_context.user_goal = "测试全局超时"
        mock_context.page_history = []
        mock_context.total_tokens_used = 0

        mocker.patch("mobile_automation.core.orchestrator.TaskContext", return_value=mock_context)

        orchestrator = TaskOrchestrator(
            step_runner=mock_step_runner,
            token_budget=mock_token_budget,
        )

        context = orchestrator.execute_task(
            user_goal="测试全局超时", max_steps=30, max_duration=None
        )
        assert context.status == TaskStatus.FAILED
        # 未传 max_duration 时必须使用全局配置
        mock_context.is_timeout.assert_called_once_with(
            max_duration_seconds=settings.execution.max_total_duration_seconds
        )

    def test_detect_loop_returns_true(self, mocker):
        """验证 _detect_loop 在连续相同操作时返回 True。"""
        mock_step_runner = mocker.MagicMock()
        mock_token_budget = mocker.MagicMock()

        orchestrator = TaskOrchestrator(
            step_runner=mock_step_runner,
            token_budget=mock_token_budget,
        )

        mocker.patch("mobile_automation.core.orchestrator.settings.loop_detection.max_same_actions", 3)

        action = Action(ActionType.CLICK, ActionParams(element_id="#1"))
        # 优化后：连续相同操作直接递增，第 3 次即触发 max_same(3)
        assert orchestrator._detect_loop(action) is False  # 第 1 次，_same_action_count=1
        assert orchestrator._detect_loop(action) is False  # 第 2 次，_same_action_count=2
        assert orchestrator._detect_loop(action) is True   # 第 3 次，_same_action_count=3

    def test_detect_loop_different_actions(self, mocker):
        """验证不同操作不会触发死循环检测。"""
        mock_step_runner = mocker.MagicMock()
        mock_token_budget = mocker.MagicMock()

        orchestrator = TaskOrchestrator(
            step_runner=mock_step_runner,
            token_budget=mock_token_budget,
        )

        mocker.patch("mobile_automation.core.orchestrator.settings.loop_detection.max_same_actions", 3)

        orchestrator._detect_loop(Action(ActionType.CLICK, ActionParams(element_id="#1")))
        orchestrator._detect_loop(Action(ActionType.BACK, ActionParams()))
        orchestrator._detect_loop(Action(ActionType.CLICK, ActionParams(element_id="#2")))
        # 优化后：新操作重置为 1（第一次出现），不再是 0
        assert orchestrator._same_action_count == 1

    def test_detect_loop_after_different_action(self, mocker):
        """验证不同操作后计数器重置。"""
        mock_step_runner = mocker.MagicMock()
        mock_token_budget = mocker.MagicMock()

        orchestrator = TaskOrchestrator(
            step_runner=mock_step_runner,
            token_budget=mock_token_budget,
        )

        mocker.patch("mobile_automation.core.orchestrator.settings.loop_detection.max_same_actions", 3)

        click = Action(ActionType.CLICK, ActionParams(element_id="#1"))
        orchestrator._detect_loop(click)
        orchestrator._detect_loop(click)
        orchestrator._detect_loop(Action(ActionType.BACK, ActionParams()))
        # 经过 BACK 后计数器重置，需要再做 5 次 click 才能触发
        orchestrator._detect_loop(click)
        orchestrator._detect_loop(click)
        orchestrator._detect_loop(click)
        orchestrator._detect_loop(click)
        result = orchestrator._detect_loop(click)
        assert result is True

    def test_execute_task_max_steps_reached(self, mocker):
        """验证达到最大步数后任务自动 COMPLETED。"""
        mock_step_runner = mocker.MagicMock()
        mock_token_budget = mocker.MagicMock()

        mock_step_runner.run_step.return_value = StepRecord(
            step_index=1,
            action=Action(ActionType.BACK, ActionParams()),
            status=StepStatus.SUCCESS,
            page_summary="某页面",
        )

        orchestrator = TaskOrchestrator(
            step_runner=mock_step_runner,
            token_budget=mock_token_budget,
        )

        context = orchestrator.execute_task(user_goal="测试", max_steps=1)
        assert context.status == TaskStatus.COMPLETED
        assert context.current_step == 1

    def test_execute_task_max_steps_zero_unlimited(self, mocker):
        """验证 max_steps=0 表示不限制步数（保留显式 0 语义）。"""
        mock_step_runner = mocker.MagicMock()
        # 第一次执行返回 WAIT 成功，第二次返回 TERMINATE 终止循环
        mock_step_runner.run_step.side_effect = [
            StepRecord(
                step_index=1,
                action=Action(ActionType.WAIT, ActionParams()),
                status=StepStatus.SUCCESS,
                page_summary="某页面",
            ),
            StepRecord(
                step_index=2,
                action=Action(ActionType.TERMINATE, ActionParams()),
                status=StepStatus.SUCCESS,
                page_summary="目标已达成",
            ),
        ]
        mock_token_budget = mocker.MagicMock()

        orchestrator = TaskOrchestrator(
            step_runner=mock_step_runner,
            token_budget=mock_token_budget,
        )

        context = orchestrator.execute_task(user_goal="测试", max_steps=0)
        # max_steps=0 不被替换为默认值，任务按终止信号正常结束
        assert context.max_steps == 0
        assert context.current_step == 2
        assert context.status == TaskStatus.COMPLETED

    def test_task_id_is_generated(self, mocker):
        """验证每次执行生成不同的 task_id。"""
        mock_step_runner = mocker.MagicMock()
        mock_step_runner.run_step.return_value = StepRecord(
            step_index=1, action=Action(ActionType.WAIT, ActionParams()), status=StepStatus.SUCCESS,
        )
        mock_token_budget = mocker.MagicMock()

        orchestrator = TaskOrchestrator(
            step_runner=mock_step_runner,
            token_budget=mock_token_budget,
        )

        context1 = orchestrator.execute_task("任务1", max_steps=1)
        context2 = orchestrator.execute_task("任务2", max_steps=1)
        assert context1.task_id != context2.task_id

    # ------------------------------------------------------------------
    # 系统查询结果收集（system_query_results）
    # ------------------------------------------------------------------

    def _build_query_record(self, step_index, action_type, result, status=StepStatus.SUCCESS):
        """构造一条查询动作步骤记录，params.result 携带查询结果。"""
        return StepRecord(
            step_index=step_index,
            action=Action(action_type, ActionParams(result=result)),
            status=status,
            page_summary="某页面",
        )

    def test_execute_task_collects_query_result(self, mocker):
        """验证查询类动作执行后结果格式化并追加到 system_query_results。"""
        mock_step_runner = mocker.MagicMock()
        mock_step_runner.run_step.return_value = self._build_query_record(
            1, ActionType.GET_CLIPBOARD, "验证码 888888",
        )
        mock_token_budget = mocker.MagicMock()

        orchestrator = TaskOrchestrator(
            step_runner=mock_step_runner,
            token_budget=mock_token_budget,
        )

        context = orchestrator.execute_task(user_goal="读取剪贴板", max_steps=1)
        assert context.status == TaskStatus.COMPLETED
        assert len(context.system_query_results) == 1
        assert context.system_query_results[0].startswith("get_clipboard: ")
        assert "验证码 888888" in context.system_query_results[0]

    def test_execute_task_collects_sms_result(self, mocker):
        """验证 read_sms 查询结果（list[dict]）格式化为 JSON 摘要。"""
        mock_step_runner = mocker.MagicMock()
        mock_step_runner.run_step.return_value = self._build_query_record(
            1, ActionType.READ_SMS,
            [{"address": "10086", "body": "验证码 123456", "date": 1700000000000}],
        )
        mock_token_budget = mocker.MagicMock()

        orchestrator = TaskOrchestrator(
            step_runner=mock_step_runner,
            token_budget=mock_token_budget,
        )

        context = orchestrator.execute_task(user_goal="读取短信", max_steps=1)
        assert context.status == TaskStatus.COMPLETED
        assert len(context.system_query_results) == 1
        assert context.system_query_results[0].startswith("read_sms: ")
        assert "验证码 123456" in context.system_query_results[0]

    def test_execute_task_query_result_truncated(self, mocker):
        """验证超长查询结果被截断至 200 字符。"""
        mock_step_runner = mocker.MagicMock()
        mock_step_runner.run_step.return_value = self._build_query_record(
            1, ActionType.GET_CLIPBOARD, "长" * 1000,
        )
        mock_token_budget = mocker.MagicMock()

        orchestrator = TaskOrchestrator(
            step_runner=mock_step_runner,
            token_budget=mock_token_budget,
        )

        context = orchestrator.execute_task(user_goal="读取剪贴板", max_steps=1)
        assert len(context.system_query_results) == 1
        assert len(context.system_query_results[0]) <= 200 + len("get_clipboard: ") + len("...")
        assert context.system_query_results[0].endswith("...")

    def test_execute_task_query_results_capped_at_five(self, mocker):
        """验证 system_query_results 最多保留 5 条，超出丢弃最旧。"""
        mock_step_runner = mocker.MagicMock()
        mock_token_budget = mocker.MagicMock()

        # 连续执行 7 个查询步骤（混合查询类型，避免触发死循环检测）
        query_types = [
            ActionType.READ_SMS, ActionType.GET_CLIPBOARD,
            ActionType.GET_NOTIFICATIONS, ActionType.GET_CALL_STATE,
            ActionType.READ_SMS, ActionType.GET_CLIPBOARD, ActionType.GET_NOTIFICATIONS,
        ]
        mock_step_runner.run_step.side_effect = [
            self._build_query_record(i + 1, at, {"ok": True})
            for i, at in enumerate(query_types)
        ]

        orchestrator = TaskOrchestrator(
            step_runner=mock_step_runner,
            token_budget=mock_token_budget,
        )

        context = orchestrator.execute_task(user_goal="查询系统信息", max_steps=7)
        assert context.status == TaskStatus.COMPLETED
        assert len(context.system_query_results) == 5
        # 最旧的 2 条（read_sms、get_clipboard）被丢弃，保留第 3~7 条
        assert context.system_query_results[0].startswith("get_notifications: ")
        assert context.system_query_results[-1].startswith("get_notifications: ")
        assert all('"ok": true' in r for r in context.system_query_results)

    def test_execute_task_query_result_none_recorded(self, mocker):
        """验证查询失败（result=None）时记录「无结果」占位，任务不受影响。"""
        mock_step_runner = mocker.MagicMock()
        mock_step_runner.run_step.return_value = self._build_query_record(
            1, ActionType.GET_NOTIFICATIONS, None,
        )
        mock_token_budget = mocker.MagicMock()

        orchestrator = TaskOrchestrator(
            step_runner=mock_step_runner,
            token_budget=mock_token_budget,
        )

        context = orchestrator.execute_task(user_goal="读取通知", max_steps=1)
        assert context.status == TaskStatus.COMPLETED
        assert len(context.system_query_results) == 1
        assert "无结果" in context.system_query_results[0]

    def test_execute_task_query_action_does_not_terminate(self, mocker):
        """验证查询类动作不触发 TERMINATE 逻辑，执行后正常进入下一步。"""
        mock_step_runner = mocker.MagicMock()
        mock_token_budget = mocker.MagicMock()

        mock_step_runner.run_step.side_effect = [
            self._build_query_record(1, ActionType.GET_CLIPBOARD, "内容"),
            StepRecord(
                step_index=2,
                action=Action(ActionType.TERMINATE, ActionParams()),
                status=StepStatus.SUCCESS,
                page_summary="目标已达成",
            ),
        ]

        orchestrator = TaskOrchestrator(
            step_runner=mock_step_runner,
            token_budget=mock_token_budget,
        )

        context = orchestrator.execute_task(user_goal="查询后结束", max_steps=0)
        assert context.status == TaskStatus.COMPLETED
        assert context.current_step == 2
        assert len(context.system_query_results) == 1
