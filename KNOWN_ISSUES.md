# 遗留问题归档（Known Issues）

> 本文件记录当前项目的遗留问题与待办事项，随修复进展更新。
> 最后更新：2026-08-05

## 未解决

### 1. 弹窗检测误报（优化后仍需真机观察）

- **现象**：弹窗检测曾偶发误报，将正常页面元素误判为弹窗
- **已实施优化（2026-08-04，用户授权保守优化）**：
  - DIALOG_KEYWORDS 移除 `popup`（PopupWindow/PopupMenu 等非弹窗控件类名是最大误报源）
  - `_find_overlay` 增加根容器 class_name 黑名单过滤（排除全屏可点击的 DecorView/ViewGroup 类容器）
  - `_find_by_feature_text` 增加空间聚集度检查（匹配按钮水平/垂直跨度超屏幕 60% 判定为分散表单布局，非弹窗）
- **现有防护**：v1.3.1 处理失败退出机制（自动处理失败达 2 次后放行 LLM，防死循环）；三层过滤逻辑结构与顺序保持不变
- **测试覆盖**：v1.4.1 4 个碰撞案例锁定测试 + v1.4.2 新增 4 个误报源测试（PopupWindow/根容器/分散文本/聚集文本），全部通过
- **推进方式**：真机端到端回归观察，若仍有误报需截图 + UI 树场景复现后针对性处理

### 2. 端到端通过率：80%，打开相机用例偶发 LLM 解析异常

- **现状**：2026-08-04 真机批量回归（examples/test_cases.json 5 用例）结果 4/5 通过（80%），较历史 33%（2/6）大幅提升
- **通过**：打开设置 / 找 Wi-Fi / 设置搜索"电池" / 打开相册（无需 LLM 介入自动成功）
- **失败**：打开相机（1/5，aborted，LLM Step 1 响应 JSON 解析异常 `Expecting property name enclosed in double quotes`），属 MiMo 模型偶发格式不稳定，非框架缺陷
- **未回归的历史用例**：新版 examples/test_cases.json 为 5 个新编用例，与历史 6 用例集可能不完全对应
- **优化建议**：`DecisionEngine.decide_action` 解析失败目前直接抛异常走步骤重试，建议在引擎内对解析失败增加 1 次自动重新请求（附"请严格输出合法 JSON"提示），可低成本消化此类偶发格式问题

### 3. 用例级超时 `timeout_seconds` 为死字段（2026-08-05 全量排查发现）

- **现象**：`TestCase.timeout_seconds` 可从 JSON 用例文件加载（`testing/__init__.py`、`main.py` 均解析该字段），但 `BatchTestRunner._run_single` 从未应用它，`execute_task` 也不支持用例级超时参数
- **影响**：用户配置用例级超时后不会生效，文档承诺与实际行为不符
- **修复方向**：在 `_run_single` 中基于 `case.timeout_seconds`（非 0 时）覆盖全局 `max_total_duration_seconds`，或在 `execute_task` 增加 `max_duration` 参数

### 4. 弹窗重试耗尽后步骤状态停留在非终态 RETRYING（2026-08-05 全量排查发现）

- **现象**：`PerceptionPipeline.perceive_with_popup_handling` 弹窗处理路径只置 `record.status = RETRYING`，不递增 `retry_count`；若弹窗持续存在直至 attempt 耗尽，步骤以 `RETRYING` 非终态返回
- **影响**：Orchestrator 只记 warning 不计失败（`retry_count < max_retries`），状态语义不明，且污染 `success_rate` 统计
- **修复方向**：attempt 耗尽且仍为 RETRYING 时标记为 FAILED 并写入 error_message，或弹窗重试路径同步递增 retry_count

### 5. 批量测试用例解析逻辑三重重复 + from_json 设计缺陷（2026-08-05 全量排查发现）

- **现象**：
  - `BatchTestRunner.from_json` 解析出的 cases 未存入实例即被丢弃，返回的 runner 无用例可执行
  - `run_from_file` 因此把同一 JSON 文件读两遍、解析两遍
  - `main.py` 的 `load_cases` 是第三份重复解析代码
  - `BatchTestRunner.__init__` 访问 `orchestrator._token_budget` 私有属性且从未使用
- **修复方向**：`from_json` 将 cases 存入实例（如 `self._cases`），`run_from_file` 直接复用；`main.py` 改为调用统一入口

### 6. AGENTS.md 架构描述与实际代码不一致（2026-08-05 全量排查发现）

- **现象**：AGENTS.md 架构图中的 `framework/`、`mobile/device|executor|perception|popup/` 目录均不存在，实际为 `core/`（含 `core/pipelines/`）+ `device/executor/perception/popup/` 平级结构；`llm/adapters/` 子包（unified_adapter.py、model_registry.py）也不存在，实际为扁平的 `llm/qwen_adapter.py` 等 + `LLMServiceFactory` 注册字典
- **附带**：供应商表应注明 DeepSeek / LongCat / Local 复用 `OpenAIAdapter`，无独立适配器文件

### 7. llm 包导出遗漏 MiMoAdapter（2026-08-05 全量排查发现）

- **现象**：`llm/__init__.py` docstring 声称 `mimo_adapter` 是核心组件，但 `MiMoAdapter` 既未 import 也不在 `__all__`（mimo 还是默认多模态供应商）
- **修复方向**：补充 `from .mimo_adapter import MiMoAdapter` 并加入 `__all__`

### 8. MessageBuilder 已弃用但代码与测试仍保留（2026-08-05 全量排查发现）

- **现象**：`llm/message_builder.py` 已在 `llm/__init__.py` 标注弃用（生产代码已切到 `DecisionPromptBuilder`），但文件与 `tests/test_message_builder.py`（12 个用例）仍保留
- **处理约束**：受"禁止删除已有单元测试用例"规范约束，是否清理由用户决策

### 9. 代码质量小项（2026-08-05 全量排查发现，低优先级）

- `step_runner.py` 异常分支跨模块调用私有方法 `_execution_pipeline._register_step_archive`，破坏封装
- `.env.example` 中向后兼容字段 `LLM__CONTEXT_WINDOW=32000` 与 mimo 实际 128000 不符，易误导
- `LLMServiceFactory.create` docstring 只列 qwen/openai/anthropic 三家，实际支持 8 家（zhipu/mimo/deepseek/longcat/local）

## 已解决

### ~~3. 批量测试用例文件缺失~~（2026-08-04 已解决）

- **原因**：AGENTS.md 中 `test` 子命令示例对应的 examples 目录为空
- **修复**：新增 `examples/test_cases.json`（5 个真实可用用例：打开设置 / 找 Wi-Fi / 设置搜索电池 / 打开相机 / 打开相册，含 smoke 标签）
- **附带**：CLI 重构为 argparse subparsers（run/test 双命令 + 无子命令 `-g` 向后兼容），`test` 子命令支持 `--filter` / `--format-report(json/md/html)` / `--report-dir` / `--stop-on-failure`

## 待办

- [x] 补充批量测试示例用例文件（2026-08-04，examples/test_cases.json）
- [x] 弹窗误报保守优化（2026-08-04，三层内收紧 + 4 个新测试）
- [x] 完整端到端用例集回归（2026-08-04，4/5 通过，80%）
- [x] 分支 `refactor/step-runner-split` 合并 main 前的最终回归（2026-08-05 核实：该分支与 main 已完全一致，0 ahead / 0 behind，视为已合并）
- [ ] 修复用例级超时 `timeout_seconds` 死字段（问题 3）
- [ ] 修复弹窗重试耗尽后 RETRYING 非终态问题（问题 4）
- [ ] 统一批量测试用例解析入口，修复 from_json 设计缺陷（问题 5）
- [ ] 更新 AGENTS.md 架构图与供应商表，与 v1.4.x 实际结构对齐（问题 6）
- [ ] llm 包补充导出 MiMoAdapter（问题 7）
- [ ] 决策是否清理弃用的 MessageBuilder 及其测试（问题 8，需用户确认）
- [ ] LLM 解析失败增加 1 次自动重新请求，提升端到端稳定性（问题 2 附带建议）
