# 遗留问题归档（Known Issues）

> 本文件记录当前项目的遗留问题与待办事项，随修复进展更新。
> 最后更新：2026-08-06

## 未解决

### 1. 弹窗检测误报（持续观察）

- **现象**：弹窗检测曾偶发误报，将正常页面元素误判为弹窗
- **已实施优化（2026-08-04，用户授权保守优化）**：
  - DIALOG_KEYWORDS 移除 `popup`（PopupWindow/PopupMenu 等非弹窗控件类名是最大误报源）
  - `_find_overlay` 增加根容器 class_name 黑名单过滤（排除全屏可点击的 DecorView/ViewGroup 类容器）
  - `_find_by_feature_text` 增加空间聚集度检查（匹配按钮水平/垂直跨度超屏幕 60% 判定为分散表单布局，非弹窗）
- **真机验证（2026-08-06）**：Xiaomi 23113RKC6C（1440×3200，Android 16）端到端 5 用例全程 15 步弹窗检测均为「未发现弹窗」，零误报
- **现有防护**：v1.3.1 处理失败退出机制 + 弹窗重试耗尽置 FAILED 终态（2026-08-06 修复，见问题 4）
- **推进方式**：继续真机观察，若仍有误报需截图 + UI 树场景复现后针对性处理

### 2. MessageBuilder 已弃用但代码与测试仍保留（原问题 8，需用户决策）

- **现象**：`llm/message_builder.py` 已标注弃用（生产代码已切到 `DecisionPromptBuilder`），但文件与 `tests/test_message_builder.py`（10 个用例）仍保留
- **处理约束**：受「禁止删除已有单元测试用例」规范约束，是否清理由用户决策

## 已解决

### ~~3. 用例级超时 timeout_seconds 死字段~~（2026-08-06，提交 5a0b9d2）

- **修复**：`execute_task` 新增 `max_duration` 可选参数透传至 `_check_timeout`；`_run_single` 在 `timeout_seconds>0` 时传入用例级超时，否则回退全局配置
- **测试**：新增 5 个单元测试（透传/回退/生效/互不干扰）

### ~~4. 弹窗重试耗尽后 RETRYING 非终态~~（2026-08-06，提交 d5293e4）

- **修复**：StepRunner attempt 循环耗尽后 RETRYING 统转 FAILED 并写 error_message；Orchestrator 失败判定扩展为「status==FAILED 或 retry_count>=max_retries」
- **语义保持**：弹窗重试仍不计 retry_count（语义分离设计不变）
- **测试**：新增 2 个锁定测试

### ~~5. 批量解析三重重复 + from_json 缺陷~~（2026-08-06，提交 24561f8）

- **修复**：新增 `parse_test_cases` / `load_test_cases` 权威解析函数；`from_json` 将 cases 存入 `runner._cases`；`run_from_file` 复用 from_json（文件只读一次）；`main.load_cases` 委托统一入口；删除未使用的 `orchestrator._token_budget` 私有访问
- **测试**：新增/更新 6 个测试（含文件只读一次 spy 验证）

### ~~6. AGENTS.md 架构与实际不一致~~（2026-08-06，提交 0e39a69）

- **修复**：架构树重写与实际目录对齐（core/pipelines + device/executor/perception/popup 平级 + llm 扁平）；供应商表注明 DeepSeek/LongCat/Local 复用 OpenAIAdapter

### ~~7. llm 包遗漏 MiMoAdapter 导出~~（2026-08-06，提交 0e39a69）

- **修复**：补 `from .mimo_adapter import MiMoAdapter` 并加入 `__all__`；新增导出一致性测试

### ~~9. 代码质量小项~~（2026-08-06，提交 0e39a69）

- 9a：ExecutionPipeline 新增公开 `register_failed_step_archive`，step_runner 不再跨模块调用私有方法
- 9b：`.env.example` CONTEXT_WINDOW 32000→128000（与 mimo 实际一致，附各供应商差异注释）
- 9c：LLMServiceFactory docstring 更新为全部 8 家供应商

### ~~端到端通过率低 + LLM 解析异常~~（2026-08-06）

- **端到端**：2026-08-06 真机（Xiaomi 23113RKC6C）批量回归 5/5 全通过（100%），历史 33%→80%→100%
- **LLM 解析异常**：DecisionEngine 解析失败时引擎内自动重试 1 次（附修正提示），仍失败按原逻辑抛异常走步骤重试（提交 1fd04b7）；新增 4 个测试

### ~~批量测试用例文件缺失~~（2026-08-04）

- 新增 `examples/test_cases.json`（5 个真实可用用例）；CLI 重构为 argparse subparsers（run/test）

## 待办

- [x] 修复问题 3/4/5 + 问题 2 附带（2026-08-06，高优先级逐个验证提交）
- [x] 批量修复问题 6/7/9a/9b/9c（2026-08-06，低优先级批量验证提交）
- [ ] 决策是否清理弃用的 MessageBuilder 及其测试（需用户确认）
