"""core/pipelines —— StepRunner 拆分后的流水线模块。

将原 StepRunner（上帝类）按职责拆分为三个独立流水线：

- PerceptionPipeline：感知 + 弹窗处理 + 感知归档
- DecisionEngine：LLM 决策 + 响应解析 + 坐标解析 + LLM 交互归档
- ExecutionPipeline：执行验证 + 步骤归档

三者互不引用，仅由 StepRunner 薄编排层顺序调用。
"""
