"""任务编排器模块测试。

使用 mock 的 StepRunner 和 TokenBudgetManager 测试 TaskOrchestrator
的任务生命周期管理、死循环检测和超时检测功能。
"""

import pytest

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
        # _same_action_count 需要累积到 max_same(3) 才返回 True
        # 每次需要连续 3 次相同操作才 +1，所以共需 5 次
        assert orchestrator._detect_loop(action) is False  # 第 1 次
        assert orchestrator._detect_loop(action) is False  # 第 2 次
        assert orchestrator._detect_loop(action) is False  # 第 3 次，_same_action_count=1
        assert orchestrator._detect_loop(action) is False  # 第 4 次，_same_action_count=2
        assert orchestrator._detect_loop(action) is True   # 第 5 次，_same_action_count=3

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
        assert orchestrator._same_action_count == 0

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
