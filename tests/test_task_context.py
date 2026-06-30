"""任务上下文模块测试。

测试 TaskContext 的任务状态管理、步骤记录和辅助方法。
测试 StepRecord 的执行记录和时间计算。
"""

from datetime import datetime, timedelta

from mobile_automation.models.action import Action, ActionParams
from mobile_automation.models.enums import ActionType, StepStatus, TaskStatus
from mobile_automation.models.task import StepRecord, TaskContext


class TestStepRecord:
    """测试 StepRecord 单步执行记录。"""

    def test_duration_ms_with_both_times(self):
        """验证 duration_ms 在有起止时间时正确计算。"""
        now = datetime.now()
        record = StepRecord(
            step_index=1,
            action=Action(ActionType.CLICK, ActionParams()),
            status=StepStatus.SUCCESS,
            started_at=now,
            finished_at=now + timedelta(seconds=2),
        )
        assert record.duration_ms() == 2000

    def test_duration_ms_without_times(self):
        """验证 duration_ms 在无时间时返回 0。"""
        record = StepRecord(
            step_index=1,
            action=Action(ActionType.CLICK, ActionParams()),
            status=StepStatus.PENDING,
        )
        assert record.duration_ms() == 0

    def test_is_success_true(self):
        """验证 SUCCESS 状态返回 True。"""
        record = StepRecord(
            step_index=1,
            action=Action(ActionType.CLICK, ActionParams()),
            status=StepStatus.SUCCESS,
        )
        assert record.is_success() is True

    def test_is_success_false(self):
        """验证非 SUCCESS 状态返回 False。"""
        for status in [StepStatus.FAILED, StepStatus.PENDING, StepStatus.RETRYING]:
            record = StepRecord(
                step_index=1,
                action=Action(ActionType.CLICK, ActionParams()),
                status=status,
            )
            assert record.is_success() is False

    def test_default_values(self):
        """验证 StepRecord 的默认值正确。"""
        action = Action(ActionType.WAIT, ActionParams())
        record = StepRecord(step_index=1, action=action, status=StepStatus.PENDING)
        assert record.error_message == ""
        assert record.retry_count == 0
        assert record.token_used == 0
        assert record.started_at is None


class TestTaskContext:
    """测试 TaskContext 任务上下文的状态管理。"""

    def test_initial_state(self):
        """验证 TaskContext 初始化状态正确。"""
        ctx = TaskContext(task_id="test-001", user_goal="打开设置")
        assert ctx.status == TaskStatus.RUNNING
        assert ctx.current_step == 0
        assert ctx.steps == []
        assert ctx.total_tokens_used == 0

    def test_add_step_updates_state(self):
        """验证 add_step 正确更新步骤索引和 Token 计数。"""
        ctx = TaskContext(task_id="test-001", user_goal="测试")
        record = StepRecord(
            step_index=1,
            action=Action(ActionType.CLICK, ActionParams()),
            status=StepStatus.SUCCESS,
            token_used=100,
        )
        ctx.add_step(record)
        assert ctx.current_step == 1
        assert len(ctx.steps) == 1
        assert ctx.total_tokens_used == 100

    def test_add_multiple_steps(self):
        """验证多次 add_step 累加 Token 和更新步骤。"""
        ctx = TaskContext(task_id="test-001", user_goal="测试")
        for i in range(3):
            record = StepRecord(
                step_index=i + 1,
                action=Action(ActionType.CLICK, ActionParams()),
                status=StepStatus.SUCCESS,
                token_used=50,
            )
            ctx.add_step(record)
        assert ctx.current_step == 3
        assert ctx.total_tokens_used == 150

    def test_is_completed(self):
        """验证终止状态的任务返回 True。"""
        ctx = TaskContext(task_id="test-001", user_goal="测试")
        assert ctx.is_completed() is False
        ctx.status = TaskStatus.COMPLETED
        assert ctx.is_completed() is True
        ctx.status = TaskStatus.FAILED
        assert ctx.is_completed() is True
        ctx.status = TaskStatus.ABORTED
        assert ctx.is_completed() is True

    def test_is_timeout(self):
        """验证超时检测逻辑。"""
        ctx = TaskContext(task_id="test-001", user_goal="测试")
        assert ctx.is_timeout(max_duration_seconds=0) is True
        assert ctx.is_timeout(max_duration_seconds=3600) is False

    def test_get_last_step_with_steps(self):
        """验证 get_last_step 返回最后一条记录。"""
        ctx = TaskContext(task_id="test-001", user_goal="测试")
        r1 = StepRecord(step_index=1, action=Action(ActionType.WAIT, ActionParams()), status=StepStatus.SUCCESS)
        r2 = StepRecord(step_index=2, action=Action(ActionType.CLICK, ActionParams()), status=StepStatus.SUCCESS)
        ctx.add_step(r1)
        ctx.add_step(r2)
        last = ctx.get_last_step()
        assert last is not None
        assert last.step_index == 2

    def test_get_last_step_empty(self):
        """验证无步骤时 get_last_step 返回 None。"""
        ctx = TaskContext(task_id="test-001", user_goal="测试")
        assert ctx.get_last_step() is None

    def test_get_success_rate(self):
        """验证成功率计算。"""
        ctx = TaskContext(task_id="test-001", user_goal="测试")
        ctx.add_step(StepRecord(step_index=1, action=Action(ActionType.WAIT, ActionParams()), status=StepStatus.SUCCESS))
        ctx.add_step(StepRecord(step_index=2, action=Action(ActionType.CLICK, ActionParams()), status=StepStatus.FAILED))
        ctx.add_step(StepRecord(step_index=3, action=Action(ActionType.BACK, ActionParams()), status=StepStatus.SUCCESS))
        assert ctx.get_success_rate() == 2 / 3

    def test_get_success_rate_empty(self):
        """验证无步骤时成功率为 0。"""
        ctx = TaskContext(task_id="test-001", user_goal="测试")
        assert ctx.get_success_rate() == 0.0

    def test_user_goal_stored(self):
        """验证用户目标正确保存。"""
        goal = "打开微信，给张三发消息"
        ctx = TaskContext(task_id="test-001", user_goal=goal)
        assert ctx.user_goal == goal

    def test_default_max_steps(self):
        """验证默认最大步数为 30。"""
        ctx = TaskContext(task_id="test-001", user_goal="测试")
        assert ctx.max_steps == 30
