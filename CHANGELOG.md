# 版本更新日志（CHANGELOG）

> 本文件记录 Mobile_App_AutoTest 的版本迭代历史。
> 版本规则：**大版本（major）= 里程碑级更新**（架构/稳定性/能力体系），**小版本（minor）= 功能迭代批次**，patch = 单点修复。

当前建议版本：**v1.2.0**

---

# 最近更新

## v1.2.0 — P2 质量改进（2026-07-31）

### 新增
- `U2Controller.long_click` 公开封装（不再允许绕过抽象层直接访问 `_device`）
- 微调后坐标裁剪测试、window_size 回退测试、max_steps=0 语义测试、max_retries=0 保护测试

### 修复
- **执行器**（`e8f22a4`）
  - 双击操作间隔增加 0.1s 延时，确保系统识别为两次独立事件
  - `SWIPE_POINT` 逐段滑过所有途经点，实现真正的多段轨迹（九宫格解锁等场景）
  - 坐标微调（`_apply_tuning`）与 swipe/scroll 终点统一裁剪到屏幕有效范围
  - `type_executor` 聚焦点击失败时中止输入，防止文本泄露到错误控件
  - `_resolve_coordinates` 注释修正（明确 element_id 由 StepRunner 解析）
- **core 逻辑**（`9c5ae81`）
  - `max_retries_per_step=0` 时直接标记 FAILED，不再返回无意义 PENDING
  - retry 耗尽标记 FAILED 后立即 break，避免下一轮迭代覆盖状态
  - Token 消耗记录移到 LLM 响应解析成功后（解析失败不虚增）
  - `max_steps=0` 不再被 `or` 运算替换为默认值（0 = 不限制步数）
- **device 层**（`bac6600`）
  - `window_size` 获取失败回退到配置默认尺寸（`settings.device`），不再硬编码 1080x1920
  - `wait_stable`：dump 异常时重置快照防止误判稳定；连续 3 次失败提前终止（设备断连不再空转）

### 验证
- 单元测试：**341 passed**（新增 8 个用例，0 回归）

---

# 历史版本

## v0.1.0 — 项目初始化（2026-07-26）

### 新增
- 项目初始提交（`0243e6c`）与工程文件上传（`81ff3f1`）
- 示例日志与报告（`3cd58ff`）
- README 文档完善（`4ec9192` / `c10c8fd` / `ad5c59b`）

---

## v0.2.0 — 基础质量修复（2026-07-27）

### 新增
- CoT 思维链 Prompt 引导（`a8fb14a`）
- 集成测试补充（`a8fb14a`）

### 修复
- 多项 Bug 修复与代码质量改进（`79d5fa8`）
- 清理旧日志和报告文件，同步行尾格式（`82f1ba1`）

### 变更
- 同步主分支关键配置文件到新分支（`f206af7`）

---

## v0.3.0 — 稳定性增强（2026-07-28）

### 修复
- **DeviceManager 单例线程锁 + 默认分辨率修正**（`7db979a`）
- **JSON 清理正则化 + 滑动等待配置化**（`6e18df2`）
- **Token 图片估算优化 + API Key 启动检查 + 空引用保护**（`794b1e3`）
- **截图类型转换 Bug 修复**（`c482001`）：u2 截图 bytes/PIL Image 自动转换 + 真机验证通过
- **弹窗覆盖层误报修复**（`9407731`）：三层过滤机制 + 端到端真机验证成功

---

## v0.4.0 — 操作能力扩展（2026-07-29）

### 新增
- **5 个物理操作**（`57bc585`）：`LOCK_SCREEN`（熄屏）/ `OPEN_NOTIFICATIONS`（通知栏）/ `ROTATE_SCREEN`（旋转）/ `VOLUME_UP` / `VOLUME_DOWN`（音量±）

### 修复
- **页面变化检测滚动漏报**（`d7541cc`）：scroll 后页面变化检测优化 + 自动定位可滚动容器
- **LLM Prompt 语义理解**（`a915443`）：输入操作强化 click → type 流程引导 + 历史记录动作信息
- **Token 压缩阈值统一**（`907a2f2`）：统一 `needs_compression` 与 `get_compression_strategy` 的双重预算阈值
- **弹窗特征文本误报**（`f4ecdfc`）：要求 ≥2 种不同特征文本同时出现才判定弹窗

### 遗留
- LLM 仍偶发"只点击搜索框不输入文本"，Prompt 已强化但需端到端持续验证

---

## v0.5.0 — 架构整理（2026-07-29）

### 新增/变更
- **DeviceManager 线程安全加固**（`eeed214`）：实例状态全量 RLock 保护（P2 需求）
- **StepRunner 方法级职责拆分**（`3bd24fa`）：`run_step` 从 141 行降至 48 行，抽出感知/决策/执行/归档子方法（P2 需求）
- **P3 清理**（`8a01234`）：移除死代码、默认屏幕尺寸可配置（`settings.device.default_screen_width/height`）、API Key 启动检查增强

---

## v0.6.0 — 代码审查修复（2026-07-29）

基于 bug_analysis.md 的代码审查结果，完成 14 个问题的批量修复：

| 提交 | 内容 |
|------|------|
| `502d5ce` | **M1** TokenBudgetManager 上下文窗口从硬编码 `CONTEXT_WINDOWS` 改为优先从 `settings.models.ModelEntry.context_window` 动态读取（新增 `_resolve_context_window`） |
| `57ec37d` | **M3** 新增 `TokenBudgetManager.provider` 公共属性；**M4** `_executors` 类型标注精确化；**M5** `_parse_rotation` 无效方向抛 ValueError；**M6** import 整理；**M8** `_find_by_feature_text` 集合推导优化 |
| `55e11a1` | **L1** 测试消除魔术数字；**L3** 补全 5 个新增 ActionType 值断言；**L4** `lock_screen` 文档澄清 toggle 行为 |

### 验证
- 单元测试：**297 passed**

---

## v0.7.0 — 模型接入扩展（2026-07-29 ~ 2026-07-30）

### 新增
- **小米 MiMo V2.5 大模型**（`210c751`）
  - `MiMoAdapter`：兼容 OpenAI 协议，支持 `reasoning_content` 思维链拼接
  - 配置：`mimo` provider + 2 个模型条目（`mimo-omni` 多模态 128K / `mimo-pro` 文本 1M）
  - 默认多模态模型改为 `mimo-omni`；CLI `--provider` 新增 mimo
  - 测试：9 个用例（初始化回退/chat/思维链/多模态/Token 估算）
- **本地大模型（llama-server）**（`4414666` + `5c05a03`）
  - `local` provider（`http://localhost:8080/v1`）+ `local-model` 模型条目（LocalModel, 32K）
  - `OpenAIAdapter` 新增 `provider` 参数支持从 `settings.models.providers` 读配置
  - 复用 OpenAIAdapter（OpenAI 兼容协议），本地服务无需 API Key
- **思维链推理开关**（`f0db6ab`）
  - `ModelSettings.enable_reasoning`（默认 True），环境变量 `MODELS__ENABLE_REASONING=false` 可关闭
  - 关闭时使用 `_NO_REASONING_SYSTEM_PROMPT`（移除 `<think>` 引导）+ MiMo 跳过 `reasoning_content` 拼接
  - 目的：图片推理场景避免思考时间过长

### 遗留
- 弹窗误报问题仍然偶发（v0.3.0 缓解后未根除），需持续优化特征文本过滤
- 模型默认多模态为 MiMo，AGENTS.md 中记录的默认值（glm-4.1v）需同步更新

### 验证
- 单元测试：297 → **306 passed**

---

## v1.0.0 — P0 稳定性里程碑（2026-07-31）

> 大版本升级：完成全部 P0 高风险修复，每项单独回归验证 + 单次 Git 提交。

### 修复内容

| 提交 | 内容 |
|------|------|
| `d02cecc` | **P0-1** 移除 6 个异常类构造函数内的日志调用（反模式：异常被捕获重试时产生误导噪音 + 循环依赖风险） |
| `8ae2d6b` | **P0-2** 弹窗覆盖层检测增加屏幕尺寸防御：`get_screen_size()` 返回 (0,0)/负值时跳过检测，避免所有节点被误判为覆盖层（弹窗误报死循环根因之一） |
| `8ce253a` | **P0-3** 报告系统：新增 `_escape_markdown_table` 转义用户/LLM 可控内容防破坏表格；`_sanitize_task_id` 清洗 Windows 非法字符；5 个 save 方法失败返回 None、save_task_meta/generate 失败抛 OSError（不再静默返回无效路径） |
| `25001a7` | **P0-4** `u2.connect` 增加 30s 超时保护（线程池 + future.result，超时后守护线程接管），兑现 AGENTS.md 承诺 |
| `11738da` | **P0-5** 5 个 LLM 适配器 `chat()` 增加异常包装（openai/anthropic APIError → LLMServiceError）+ 空 choices 守卫；Qwen/Zhipu/Claude/MiMo 构造时校验 API Key（OpenAIAdapter 不校验——local provider 无需认证）；OpenAIAdapter 补充缺失的 timeout 参数；conftest 为 mock 的 openai/anthropic 注入真实异常类 |

### 验证
- 单元测试：**307 → 316 passed**（新增 11 个用例，0 回归）

---

## v1.1.0 — P1 架构级改进（2026-07-31）

### 新增
- `ErrorHandler` 集成到核心流程（`d096405`）
  - 构造函数支持注入 `DeviceManager`，设备重连执行真实恢复
  - LLM 指数退避重试（含 30s 最大延迟上限）
  - `wrap_error` 增加 `@functools.wraps` 保留元数据；显式区分内置/自定义 `TimeoutError`
  - `test_error_handler.py` 19 个测试用例
- `LLMAdapter` 基类默认 `count_tokens` 实现（`67387c3`）
- 适配器 `provider` 参数传递（`e8fbd90`）

### 修复
- **死代码清理**（`b0286bf`）：删除 4 个仅含 `__pycache__` 的空壳目录（cli/framework/mobile/test_runner）；`message_builder.py` 标记 DEPRECATED（与 DecisionPromptBuilder 功能重叠，因 AGENTS.md 禁止删除已有测试而保留）
- **Token 估算单一来源**（`67387c3`）：5 个适配器的重复 `count_tokens` 删除，统一继承基类（文本字符数/2 + 图片 Base64 tile 精确估算）；`TokenBudgetManager` 委托基类算法
- **适配器配置统一**（`e8fbd90`）：Qwen/Zhipu/Claude 适配器优先从 `settings.models.providers` 读取配置，修复 QwenAdapter 错误回退到智谱 endpoint 的问题；`LLMServiceFactory` 将 provider 名称传给适配器

### 遗留
- **P1-5 StepRunner 拆分（已跳过）**：708 行上帝类拆分为 PerceptionPipeline/DecisionEngine/ExecutionPipeline 三模块，风险较高，经确认本次不做，建议作为独立专项任务

### 验证
- 单元测试：**339 → 341 passed**

---

# 遗留问题清单（待办）

| # | 问题 | 来源 | 优先级 |
|---|------|------|--------|
| 1 | **P1-5 StepRunner 上帝类拆分**：708 行、14 个依赖、5 种职责耦合，经确认本次跳过 | 架构审查报告方案 1（强烈推荐） | P1 |
| 2 | **弹窗检测误报**：仍有偶发误报导致死循环，P0-2 已加防御（(0,0) 屏幕尺寸）但特征文本过滤需持续优化 | bug_analysis.md P0 #2 | P1 |
| 3 | **LLM Prompt 语义理解**：偶发"只点击搜索框不输入文本"，Prompt 已强化，需端到端反复验证 | bug_analysis.md P0 #1 | P1 |
| 4 | **端到端测试通过率低**：6 用例通过率 33%（2/6），需随模型/Prompt 迭代提升 | 项目状态记录 | P2 |
| 5 | **适配器资源释放**：OpenAI/Anthropic client 无 `close()` 方法，长期运行可能连接池泄漏 | 代码审查（LLM 模块） | P2 |
| 6 | **`message_builder.py` 弃用但保留**：与 DecisionPromptBuilder 功能重叠，因 AGENTS.md 禁止删除已有测试而保留，后续评估删除 | 代码审查（死代码） | P3 |
| 7 | **工作区未提交改动**：存在大量预存未提交文件（行尾符 LF/CRLF 差异等），需确认后单独处理 | git status | P3 |
| 8 | **文档同步**：AGENTS.md 中默认多模态模型（glm-4.1v）与实际配置（mimo-omni）不一致，需更新 | 配置审查 | P3 |

---

# 版本路线图

```
v0.1 → v0.7   初始开发阶段（基础功能 → 稳定性 → 能力扩展 → 模型接入）
v1.0.0        P0 稳定性里程碑（高风险问题全部修复）
v1.1.0        P1 架构级改进（ErrorHandler 集成 / Token 统一 / 配置统一）
v1.2.0        P2 质量改进（执行器 / core / device 边界修复）
v1.3.0        [规划] P1-5 StepRunner 拆分（独立专项）
v1.4.0        [规划] 端到端通过率提升（Prompt/模型调优）
v2.0.0        [规划] 多设备并行 / 测试框架能力扩展
```
