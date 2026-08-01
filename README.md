# Mobile App AutoTest —— 移动端 AI 自动化操作框架

基于**多模态大模型**驱动的 Android 自动化测试框架。用户通过自然语言描述任务目标，系统自动完成屏幕感知、UI 解析、操作决策与步骤执行。

| 项目 | 内容 |
|------|------|
| 默认多模态模型 | Qwen3.6-Flash（文本 + 视觉理解，32K 上下文） |
| 默认纯文本模型 | DeepSeek-V4-Flash（128K 上下文） |
| Python 版本 | >= 3.10 |
| 设计原则 | element_id 优先定位 \| 双通道感知 \| 三份数据结构 \| 三层分离架构 |
| 架构模式 | 统一适配器 + 模型注册表，支持 Qwen / Zhipu / DeepSeek / LongCat |
| 测试覆盖 | 354+ 个测试用例，覆盖率 70%+ |

---

## 目录

- [核心能力](#核心能力)
- [快速开始](#快速开始)
- [项目结构](#项目结构)
- [模块详解](#模块详解)
- [多模型配置](#多模型配置)
- [Token 智能压缩](#token-智能压缩)
- [归档报告系统](#归档报告系统)
- [工作流程](#工作流程)
- [配置说明](#配置说明)
- [测试](#测试)
- [依赖清单](#依赖清单)

---

## 核心能力

| 能力 | 说明 |
|------|------|
| 自然语言驱动 | 输入中文任务描述，系统自主规划并执行操作步骤 |
| 视觉 + 结构双通道感知 | 同时利用截图（视觉）和 XML dump（UI 树）理解屏幕状态 |
| 跨应用操作 | 不依赖应用内注入，支持系统级跨应用任务链 |
| 弹窗自适应处理 | 自动检测并处理系统弹窗、权限请求、广告等干扰元素 |
| 错误恢复与重试 | 支持操作失败后的自动重试与路径修正 |
| 多模型适配 | 4 家供应商平级配置，多模态与纯文本模型分离 |
| element_id 精确定位 | LLM 输出元素编号，系统从本地索引精确查找 resource-id 执行 |
| Token 智能压缩 | 4 级动态压缩策略，根据预算自动裁剪历史上下文或丢弃截图 |
| 归档报告系统 | 每步截图 / XML / LLM 交互自动归档，任务结束生成完整 Markdown 报告 |

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，填写各模型供应商 API Key：

```bash
cp .env.example .env
```

编辑 `.env` 文件，至少需要设置默认多模态供应商的 API Key：

```ini
MODELS__PROVIDERS__QWEN__API_KEY=sk-your-dashscope-api-key
```

### 3. 连接 Android 设备

通过 USB 或网络连接 Android 设备并确认 ADB 可识别：

```bash
adb devices
```

### 4. 运行任务

#### 单次执行模式

```bash
# 基本用法
python -m mobile_automation.main run -g "打开设置，找到 Wi-Fi 选项"

# 指定设备和模型
python -m mobile_automation.main run -g "打开淘宝搜索手机" -s xxxxxx -p qwen -m 50

# 使用纯文本模型（成本更低，不支持视觉）
python -m mobile_automation.main run -g "打开设置" -p deepseek -m 30
```

#### 交互式模式

```bash
# 进入交互式命令行
python -m mobile_automation.main interactive

# 或使用简写
python -m mobile_automation.main i
```

交互模式支持以下命令：

| 命令 | 说明 |
|------|------|
| `help` | 显示帮助信息 |
| `connect [serial]` | 连接设备 |
| `status` | 显示设备状态 |
| `run <goal>` | 执行自动化任务 |
| `stop` | 停止当前任务 |
| `config show` | 显示当前配置 |
| `test run <path>` | 执行测试用例 |
| `test list <path>` | 列出测试用例 |
| `exit` | 退出交互模式 |

#### 批量测试模式

```bash
# 执行 pytest 测试文件
python -m mobile_automation.main test ./tests/test_orchestrator.py -f pytest

# 执行 JSON 数据驱动测试
python -m mobile_automation.main test ./examples/test_cases.json

# 执行 YAML 数据驱动测试
python -m mobile_automation.main test ./examples/test_cases.yaml

# 筛选执行
python -m mobile_automation.main test ./examples/test_cases.json --filter smoke

# 仅列出用例不执行
python -m mobile_automation.main test ./examples/test_cases.json --dry-run

# 生成 HTML 报告
python -m mobile_automation.main test ./examples/test_cases.json --format-report html -o report
```

### 5. 查看报告

任务执行完成后，在 `reports/yy_mm_dd_hh_mm_ss/<task_id>/` 下查看流程报告。

---

## 项目结构

```
Mobile_App_AutoTest/
│
├── pyproject.toml                 # 项目元数据、核心依赖与构建配置
├── .env                           # 环境变量配置（API Key 等）
├── .env.example                   # 环境变量配置示例
├── README.md                      # 项目说明文档
├── requirements.txt               # pip 依赖清单
│
├── logs/                          # 运行日志（自动按时间戳归档）
├── reports/                       # 任务执行报告
│
├── src/
│   └── mobile_automation/         # 主包（src-layout）
│       │
│       ├── __init__.py            # 包入口
│       ├── config.py              # 【配置管理】pydantic-settings 多模型配置
│       ├── main.py                # 【CLI 入口】命令行参数解析与子命令分发
│       │
│       ├── cli/                   # ═══ 交互式 CLI 模块 ═══
│       │   ├── app.py             #   CLI 应用主类（状态管理 + 命令注册）
│       │   ├── repl.py            #   REPL 交互循环
│       │   └── commands/          #   命令处理器
│       │       ├── base.py        #   命令基类 + 内置命令（help/exit/clear/history）
│       │       ├── device.py      #   设备管理命令（connect/status/disconnect）
│       │       ├── task.py        #   任务管理命令（run/stop）
│       │       ├── config.py      #   配置管理命令（set/get/show）
│       │       └── test.py        #   测试管理命令（run/list/report）
│       │
│       ├── test_runner/           # ═══ 批量测试执行模块 ═══
│       │   ├── models.py          #   测试用例/结果/报告数据模型
│       │   ├── loader.py          #   多格式加载器（.py/.json/.yaml/.xlsx）
│       │   ├── runner.py          #   批量测试运行器
│       │   └── reporter.py        #   报告生成器（console/json/html）
│       │
│       ├── framework/             # ═══ 跨平台核心层 ═══
│       │   ├── orchestrator.py    #   任务级编排 + 死循环检测
│       │   ├── step_runner.py     #   单步推理-行动闭环
│       │   ├── task_context.py    #   任务状态容器
│       │   └── logger.py          #   日志基础设施
│       │
│       ├── mobile/                # ═══ Android 专属适配层 ═══
│       │   ├── device/            #   设备管理（DeviceManager/U2Controller/ADBController）
│       │   ├── executor/          #   动作执行（点击/输入/滑动/等待/元素定位）
│       │   ├── perception/        #   屏幕感知（截图/UI树/页面变化检测）
│       │   └── popup/             #   弹窗处理
│       │
│       ├── llm/                   # ═══ LLM 服务层 ═══
│       │   ├── base.py            #   LLMAdapter 抽象基类
│       │   ├── adapters/          #   多厂商适配器集合
│       │   │   ├── unified_adapter.py  # 统一 OpenAI 兼容适配器（核心）
│       │   │   ├── model_registry.py   # 模型能力注册表
│       │   │   ├── qwen_adapter.py     # Qwen 多模态（文本+视觉）
│       │   │   ├── zhipu_adapter.py    # 智谱 GLM 多模态（文本+视觉）
│       │   │   ├── deepseek_adapter.py # DeepSeek 纯文本
│       │   │   └── longcat_adapter.py  # LongCat 纯文本
│       │   ├── llm_service.py     #   工厂 + 统一入口 + 能力选择
│       │   ├── message_builder.py #   多模态消息组装
│       │   └── token_budget.py    #   Token 预算 + 4 级压缩策略
│       │
│       ├── models/                # ═══ 数据模型层 ═══
│       │   ├── enums.py           #   枚举定义
│       │   ├── action.py          #   Action & ActionParams
│       │   ├── perception.py      #   UINode / UITree / UISpatialIndex
│       │   └── task.py            #   StepRecord / TaskContext
│       │
│       ├── prompts/               # ═══ Prompt 模板 ═══
│       │   ├── system_prompt.py   #   系统指令（含桌面导航/搜索框/应用名识别规则）
│       │   ├── decision_prompt.py #   步骤决策模板
│       │   └── summary_prompt.py  #   历史摘要压缩
│       │
│       ├── reporting/             # ═══ 归档与报告 ═══
│       │   ├── archiver.py        #   DataArchiver：截图/XML/LLM 归档
│       │   └── report_generator.py #  ReportGenerator：Markdown 报告
│       │
│       └── exception/             # ═══ 异常处理 ═══
            ├── exceptions.py      #   自定义异常体系（含 TaskTimeoutError）
            ├── retry_policy.py    #   @retry 指数退避装饰器
            └── error_handler.py   #   异常分类 + 恢复动作映射
│
├── tests/                         # ═══ 测试套件（354+ 个用例）═══
│   ├── conftest.py                # 共享 fixtures
│   ├── test_config.py             # 配置管理
│   ├── test_enums.py              # 枚举值
│   ├── test_action.py             # Action 校验
│   ├── test_perception.py         # UINode / UITree / 空间索引
│   ├── test_task_context.py       # TaskContext / StepRecord
│   ├── test_retry_policy.py       # 重试装饰器
│   ├── test_device_manager.py     # 设备管理
│   ├── test_ui_tree.py            # UI 树解析
│   ├── test_screen_capture.py     # 截图 fallback
│   ├── test_page_diff.py          # 页面变化检测
│   ├── test_llm_service.py        # LLM 工厂 + 能力选择
│   ├── test_message_builder.py    # 消息组装
│   ├── test_token_budget.py       # Token 预算
│   ├── test_popup_handler.py      # 弹窗处理
│   ├── test_action_executor.py    # 动作分发
│   ├── test_orchestrator.py       # 任务编排
│   ├── test_step_runner.py        # 单步执行
│   ├── test_reporting.py          # 归档报告
│   ├── test_decision_prompt.py    # Token 压缩策略
│   └── integration/               # 集成测试
│       └── test_response_parsing.py
│
├── examples/                        # ═══ 示例文件 ═══
│   ├── test_cases.json              #   JSON 数据驱动测试用例示例
│   ├── test_cases.yaml              #   YAML 数据驱动测试用例示例
│   └── test_cases.xlsx             #   Excel 数据驱动测试用例示例（可选）
│
└── scripts/
    └── smoke_test.py              # 真机冒烟测试脚本
```

---

## 模块详解

### 架构设计（三层分离）

| 层级 | 包名 | 职责 | 平台相关性 |
|------|------|------|-----------|
| 核心层 | `framework/` | 任务编排、步骤循环、状态管理、日志基础设施 | 跨平台（纯逻辑） |
| 适配层 | `mobile/` | 设备驱动、动作执行、屏幕感知、弹窗处理 | Android 专属 |
| 横切层 | `llm/`, `models/`, `prompts/`, `reporting/`, `exception/` | 跨层共享的服务和模块 | 跨平台 |

**扩展性设计：**
- 未来 iOS 支持：在 `mobile/` 下新建 `ios/` 包，复用 `framework/` 层
- 新 LLM 厂商：在 `llm/adapters/` 下新增继承 `UnifiedAdapter` 的薄包装类，在 `model_registry.py` 注册即可（开闭原则）
- 能力区分：多模态 / 纯文本由 `ModelRegistry` 管理，无需代码硬编码

### framework/ —— 跨平台核心层

| 模块 | 职责 | 关键方法 |
|------|------|----------|
| `TaskOrchestrator` | 任务级编排，管理任务的创建 → 执行 → 完成/失败/中止全生命周期 | `execute_task()`、`_detect_loop()` |
| `StepRunner` | 单步推理-行动闭环引擎（含 Action 验证 + 时间戳记录） | `run_step()`、`_decide_action()`、`_resolve_element_id()` |
| `TaskContext` | 任务状态容器，管理步骤记录和上下文数据 | `add_step()`、`is_completed()`、`is_timeout()` |

**StepRunner 单步闭环：**
```
步骤 1: ScreenCapture.capture_with_ui_tree() → 双通道感知
步骤 2: 自动归档截图、XML、摘要到本地
步骤 3: PopupHandler.detect() → 弹窗检测
步骤 4: TokenBudget 预估 → 决策压缩策略
步骤 5: LLMService.chat(截图 + 摘要 + 历史) → 决策
步骤 6: 归档 LLM 请求/响应
步骤 7: ActionExecutor.execute() → 执行动作
步骤 8: 二次感知 + 验证页面变化
```

### mobile/device/ —— 设备管理层

- **DeviceManager**（单例模式）：管理设备连接生命周期，支持自动选择设备、健康检查、u2 优先 + ADB fallback
- **U2Controller**：uiautomator2 封装（click / screenshot / dump / swipe / app_start 等）
- **ADBController**：ADB fallback 实现（shell / screenshot / reconnect / wait_for_device）

### mobile/perception/ —— 感知层

- **UITreeExtractor**（核心模块）：XML dump 解析 → 三份本地数据（local_index / structured_summary / spatial_index），结构化摘要实现约 6:1 压缩比
- **ScreenCapture**：双通道截图，优先 u2，失败后自动 fallback 到 ADB screencap
- **PageChangeDetector**：UI 树结构 diff（70% 权重）+ SSIM 视觉比较（30% 权重）

### mobile/executor/ —— 动作执行层

ActionExecutor 接收 Action 对象，校验参数后分发给子执行器：

| 执行器 | 处理的 ActionType |
|--------|------------------|
| ClickExecutor | CLICK / DOUBLE_CLICK / LONG_CLICK |
| TypeExecutor | TYPE / CLEAR_TEXT（自动清空预输入文本） |
| SwipeExecutor | SWIPE / SWIPE_POINT / SCROLL |
| WaitExecutor | WAIT |
| ActionExecutor 直接处理 | BACK / HOME / RECENT_APPS / OPEN_APP / CLOSE_APP |

**ElementLocator**（统一元素定位）：封装 ui_element 优先 + 坐标回退的定位策略，供 ActionExecutor 和 ClickExecutor 共享使用，避免逻辑重复。

### mobile/popup/ —— 弹窗处理

三策略检测 + 五策略处理：

- **检测策略：** Dialog 关键词节点匹配 → 覆盖层检测 → 特征文本匹配
- **处理策略：** ALLOW / DENY / DISMISS / CANCEL / REPORT_TO_LLM

### llm/ —— LLM 服务层

采用 **统一适配器 + 模型注册表**架构：

```
ModelCapability (model_registry.py)  ← 定义模型能力（多模态/纯文本）
    ↑
UnifiedAdapter (unified_adapter.py)   ← 统一 OpenAI 兼容适配器
    ├── QwenAdapter    → DashScope 兼容接口 (32K, 文本+视觉)
    ├── ZhipuAdapter   → 智谱开放平台 (128K, 文本+视觉)
    ├── DeepSeekAdapter → DeepSeek 官方 (128K, 纯文本)
    └── LongCatAdapter  → LongCat API (128K, 纯文本)
            ↑
LLMServiceFactory.create(provider)           → 按名称创建
LLMServiceFactory.create_multimodal(provider) → 按能力创建（多模态）
LLMServiceFactory.create_text_only(provider)  → 按能力创建（纯文本）
LLMService                                     → 统一调用入口
```

---

## 多模型配置

所有供应商**平级配置**在 `settings.models.providers` 字典中，每个供应商独立管理 API Key、模型和 Endpoint。

### 支持的模型

| 供应商 | 默认模型 | 能力 | 可选模型 |
|--------|---------|------|---------|
| **Qwen** | qwen3.6-flash | 多模态（文本+视觉） | qwen3.7-plus |
| **Zhipu** | glm-4.1v-thinking-flash | 多模态（文本+视觉） | glm-4.6v-flashx |
| **DeepSeek** | deepseek-v4-flash | 纯文本 | — |
| **LongCat** | longcat-2.0 | 纯文本 | — |

### 环境变量配置

```ini
# 默认供应商
MODELS__DEFAULT_MULTIMODAL_PROVIDER=qwen
MODELS__DEFAULT_TEXT_PROVIDER=deepseek

# 各供应商配置（平级结构）
MODELS__PROVIDERS__QWEN__API_KEY=sk-xxx
MODELS__PROVIDERS__QWEN__MODEL_NAME=qwen3.6-flash
MODELS__PROVIDERS__QWEN__BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

MODELS__PROVIDERS__ZHIPU__API_KEY=xxx
MODELS__PROVIDERS__DEEPSEEK__API_KEY=sk-xxx
MODELS__PROVIDERS__LONGCAT__API_KEY=ak-xxx
```

### 模型选择逻辑

```python
# 使用多模态模型（需要看截图）- 默认 Qwen
adapter = LLMServiceFactory.create_multimodal()

# 使用纯文本模型（成本更低）- 默认 DeepSeek
text_adapter = LLMServiceFactory.create_text_only()

# 指定供应商
zhipu = LLMServiceFactory.create_multimodal("zhipu")
longcat = LLMServiceFactory.create_text_only("longcat")
```

---

## Token 智能压缩

系统在每次调用 LLM 前自动进行 Token 预算检查，动态选择压缩策略。

| 策略 | 行为 | 触发条件 | Token 节省 |
|------|------|---------|-----------|
| `none` | 不压缩，发送全部历史 + 当前截图 | 预算充足 | 0 |
| `compress_history` | 只保留最近 5 条历史摘要 | 超出预算 | 约 50-80% 历史 Token |
| `drop_images` | 移除当前截图，历史压缩为首尾 | 超出预算 100% 以内 | 约 80-90% |
| `full_summary` | 移除截图，历史极端压缩 | 严重超预算 | 约 85-95% |

---

## 归档报告系统

每次任务执行时自动归档所有步骤数据，并生成 Markdown 报告。

```
reports/yy_mm_dd_hh_mm_ss/
    └── <task_id>/
        ├── task_meta.json            # 任务元数据
        ├── step_01/
        │   ├── screenshot.png        # 操作前截图
        │   ├── screenshot_after.png  # 操作后截图
        │   ├── xml_raw.xml           # 原始 UI 树
        │   ├── summary.txt           # 结构化摘要
        │   ├── llm_request.json      # LLM 请求
        │   └── llm_response.json     # LLM 响应
        ├── step_02/
        │   └── ...
        └── report.md                 # 流程报告
```

---

## 工作流程

```
用户输入自然语言目标
        │
        v
  TaskOrchestrator.execute_task()
        │
        ├── ① 创建 TaskContext
        ├── ② 重置 TokenBudgetManager
        │
        └── 循环: while not completed and step < max_steps
                │
                ├── StepRunner.run_step()
                │       ├── ScreenCapture → 双通道感知
                │       ├── PopupHandler → 弹窗检测
                │       ├── TokenBudget → 压缩策略决策
                │       ├── LLMService → 决策（多模态模型）
                │       ├── ActionExecutor → 执行动作
                │       └── PageChangeDetector → 验证变化
                │
                ├── 记录步骤
                └── 死循环检测
        │
        └── 生成归档报告 (reports/.../report.md)
```

---

## 配置说明

配置系统基于 `pydantic-settings`，支持 `.env` 文件和系统环境变量，嵌套配置通过 `__` 分隔。

### 主要配置组

| 配置组 | 说明 |
|--------|------|
| `models` | 多模型供应商配置（API Key、模型名、Endpoint） |
| `device` | 设备序列号、ADB 路径、重连次数 |
| `execution` | 最大步数、重试策略、截图质量、页面等待 |
| `perception` | SSIM 阈值、节点数上限、网格大小 |
| `popup` | 弹窗自动处理开关 |
| `loop_detection` | 死循环检测阈值 |
| `logger` | 日志目录、级别、轮转大小 |

### 核心环境变量

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `MODELS__DEFAULT_MULTIMODAL_PROVIDER` | `qwen` | 默认多模态供应商 |
| `MODELS__DEFAULT_TEXT_PROVIDER` | `deepseek` | 默认纯文本供应商 |
| `EXECUTION__MAX_STEPS_PER_TASK` | `30` | 单任务最大步数 |
| `LOGGER__LOG_DIR` | `logs` | 日志根目录 |

---

## 测试

项目包含 **354+ 个测试用例**，使用 pytest + pytest-mock，无需真实设备。

```bash
# 运行全部测试
pytest tests/ -v

# 运行特定模块测试
pytest tests/test_llm_service.py -v
pytest tests/test_step_runner.py -v

# CLI 模块测试
pytest tests/test_cli_app.py -v

# 测试运行器模块测试
pytest tests/test_test_loader.py tests/test_test_runner.py -v

# 带覆盖率报告
pytest tests/ --cov=mobile_automation --cov-report=term
```

### 测试覆盖范围

- 数据结构测试：enums、action 校验、UINode、UITree、空间索引
- 业务逻辑测试：StepRunner 闭环、Orchestrator 状态机、死循环检测
- LLM 层测试：Adapter 创建、能力选择、模型注册表、消息组装、Token 预算
- 异常测试：重试装饰器、参数校验、异常分类、wrap_error 装饰器
- 归档报告测试：DataArchiver、ReportGenerator
- CLI 模块测试：命令注册、帮助系统、历史记录、内置命令
- 测试运行器测试：多格式加载（JSON/YAML/Excel/pytest）、批量执行、报告生成
- Mock 场景：设备列表解析、截图 fallback、UI 树解析、弹窗检测

### 真机验证

已在真实 Android 设备（127.0.0.1:5555）上通过完整流程测试：

| 测试场景 | 结果 |
|----------|------|
| 返回桌面 → 打开应用 → 搜索 → 查看详情 | ✅ 22 步完成 |
| 弹窗检测与 LLM 上报 | ✅ 正常 |
| ADB 截图 fallback | ✅ 正常 |
| Token 压缩策略触发 | ✅ 正常 |

---

## 依赖清单

### 核心依赖

| 包名 | 用途 |
|------|------|
| openai | 统一 SDK（兼容 DashScope / 智谱 / DeepSeek / LongCat） |
| uiautomator2 | Android 设备 UI 自动化控制（主要交互方式） |
| adbutils | ADB 设备管理工具 |
| Pillow | 图片缩放与格式转换 |
| opencv-python | SSIM 视觉比较 |
| scikit-image | structural_similarity 函数 |
| lxml | 高性能 XML dump 解析 |
| pydantic | 数据模型和配置管理 |
| pydantic-settings | 环境变量驱动的配置体系 |
| python-dotenv | .env 文件加载 |

### 开发依赖

| 包名 | 用途 |
|------|------|
| pytest | 测试框架 |
| pytest-mock | mock 支持（无需真实设备） |
| pytest-asyncio | 异步测试支持 |
| pytest-cov | 测试覆盖率 |
