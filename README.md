# Mobile App AutoTest —— 移动端 AI 自动化操作框架

基于**多模态大模型**驱动的 Android 自动化操作框架。用户以自然语言描述任务目标，系统自主完成屏幕感知、UI 解析、操作决策与步骤执行，适用于应用冒烟测试与跨应用任务链自动化。

| 项目 | 内容 |
|------|------|
| 当前版本 | v1.3.2 |
| 默认多模态模型 | MiMo V2.5（`mimo-omni`，文本 + 视觉，128K 上下文） |
| 默认纯文本模型 | DeepSeek V4（`deepseek-flash`，128K 上下文） |
| Python 版本 | >= 3.10 |
| 设计原则 | element_id 优先定位 · 视觉+结构双通道感知 · 三层分离架构 |
| 模型体系 | 工厂 + 适配器模式，支持 MiMo / Qwen / Zhipu / DeepSeek / LongCat / Claude / 本地 llama |
| 测试覆盖 | 378 个单元测试，覆盖率 66.2%（门槛 60%） |

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
- [测试与验证](#测试与验证)
- [已知问题与路线图](#已知问题与路线图)
- [依赖清单](#依赖清单)

---

## 核心能力

| 能力 | 说明 |
|------|------|
| 自然语言驱动 | 输入中文任务描述，系统自主规划并执行操作步骤 |
| 双通道感知 | 同时利用截图（视觉）与 UI 树 XML dump（结构）理解屏幕状态 |
| 跨应用操作 | 不依赖应用内注入，支持系统级跨应用任务链 |
| 弹窗自适应处理 | 自动检测并处理权限请求、广告、更新提示等干扰，失败达阈值后放行 LLM 决策防死循环 |
| 错误恢复与重试 | 单步失败自动重试 + 设备重连 + LLM 指数退避 |
| 多模型适配 | 6 家供应商平级配置，多模态 / 纯文本能力自动区分 |
| element_id 精确定位 | LLM 输出元素编号，系统从本地索引精确查找 resource-id / 坐标执行 |
| Token 智能压缩 | 4 级动态压缩策略，根据预算自动裁剪历史上下文或丢弃截图 |
| 归档报告系统 | 每步截图 / XML / LLM 交互自动归档，任务结束生成 Markdown 报告 |
| 批量测试执行 | JSON / YAML / pytest 驱动的多用例批量执行与汇总报告 |
| 思维链推理 | CoT 引导逐步决策，可通过配置关闭以加速图片推理场景 |

---

## 快速开始

### 1. 安装依赖

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
# 或
uv pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，填写默认多模态供应商（MiMo）的 API Key：

```bash
cp .env.example .env
```

编辑 `.env`，至少设置：

```ini
MODELS__PROVIDERS__MIMO__API_KEY=sk-your-mimo-api-key
MODELS__PROVIDERS__MIMO__BASE_URL=https://api.xiaomimimo.com/v1
```

### 3. 连接 Android 设备

通过 USB 或网络连接设备并确认 ADB 可识别：

```bash
adb devices
```

模拟器（如 MuMu）默认通过 `adb connect 127.0.0.1:5555` 连接。

### 4. 运行任务

```bash
# 单次执行（自动从配置读取默认模型）
python -m mobile_automation.main -g "打开设置，找到 Wi-Fi 选项"

# 指定设备与模型
python -m mobile_automation.main -g "打开淘宝搜索手机" -s 127.0.0.1:5555 -p mimo -m 50

# 使用纯文本模型（成本更低，不支持视觉）
python -m mobile_automation.main -g "打开设置" -p local -m 30
```

CLI 参数：

| 参数 | 说明 |
|------|------|
| `-g / --goal` | 任务目标描述（必填） |
| `-s / --serial` | 设备序列号，缺省自动选择在线设备 |
| `-p / --provider` | 供应商：`qwen` / `openai` / `anthropic` / `zhipu` / `mimo` / `local` |
| `-m / --max-steps` | 最大步数（0 = 使用配置默认值） |

### 5. 批量测试

批量测试通过 `BatchTestRunner` 以编程方式驱动（`src/mobile_automation/testing/__init__.py`），支持 JSON 用例文件导入、用例级超时与失败隔离：

```python
from mobile_automation.core.orchestrator import TaskOrchestrator
from mobile_automation.testing import BatchTestRunner, TestCase

orchestrator = ...  # 按 main.build_app 方式组装
runner = BatchTestRunner(orchestrator)
cases = [
    TestCase(goal="打开设置，找到 Wi-Fi", max_steps=10, tags=["smoke"]),
    TestCase(goal="打开相机", max_steps=8),
]
summary = runner.run_cases(cases)
print(summary.passed, "/", summary.total)
```

### 6. 查看报告

任务执行完成后，在 `reports/yy_mm_dd_hh_mm_ss/<task_id>/` 下查看流程报告。

---

## 项目结构

```
Mobile_App_AutoTest/
│
├── pyproject.toml                 # 项目元数据、依赖、pytest/coverage 配置
├── .env                           # 环境变量配置（API Key 等，不入库）
├── .env.example                   # 环境变量配置示例
├── requirements.txt               # pip 依赖清单
├── AGENTS.md                      # 项目规范（开发/协作约定）
├── CHANGELOG.md                   # 版本迭代记录
├── README.md                      # 项目说明文档
│
├── logs/                          # 运行日志（自动按时间戳归档）
├── reports/                       # 任务执行报告（每步截图/XML/LLM 归档）
│
├── src/
│   └── mobile_automation/         # 主包（src-layout）
│       ├── __init__.py            # 包入口
│       ├── config.py              # 【配置管理】pydantic-settings 多模型配置
│       ├── logger.py              # 【日志】统一 get_logger / 任务进度日志
│       ├── main.py                # 【CLI 入口】参数解析与任务执行
│       │
│       ├── core/                  # ═══ 任务编排层 ═══
│       │   ├── orchestrator.py    #   TaskOrchestrator：生命周期 + 死循环/超时检测
│       │   ├── step_runner.py     #   StepRunner：感知→决策→执行→验证闭环
│       │   └── task_context.py    #   任务状态容器
│       │
│       ├── device/                # ═══ Android 设备控制 ═══
│       │   ├── device_manager.py  #   DeviceManager：单例 + 连接生命周期
│       │   ├── u2_controller.py   #   uiautomator2 封装（主要交互）
│       │   └── adb_controller.py  #   ADB fallback + shell 注入防护
│       │
│       ├── executor/              # ═══ 动作执行 ═══
│       │   ├── action_executor.py #   动作分发 + 系统按键 + 应用管理
│       │   ├── click_executor.py  #   点击 / 双击 / 长按
│       │   ├── type_executor.py   #   输入 / 清空文本
│       │   ├── swipe_executor.py  #   滑动 / 滚动 / 多段轨迹
│       │   └── wait_executor.py   #   页面稳定等待
│       │
│       ├── perception/            # ═══ 屏幕感知 ═══
│       │   ├── screen_capture.py  #   截图（u2 优先，ADB fallback）
│       │   ├── ui_tree.py         #   XML → 三份本地数据（含输入框标记）
│       │   ├── page_diff.py       #   页面变化检测（结构 diff + SSIM）
│       │   └── image_util.py      #   图像处理工具
│       │
│       ├── popup/                 # ═══ 弹窗处理 ═══
│       │   ├── popup_handler.py   #   检测 + 处理 + 失败退出机制
│       │   ├── classifier.py      #   弹窗类型分类
│       │   ├── pattern_rules.py   #   特征文本规则
│       │   └── models.py          #   检测/处理结果模型
│       │
│       ├── llm/                   # ═══ LLM 横切层 ═══
│       │   ├── base.py            #   LLMAdapter 抽象基类 + Token 估算
│       │   ├── llm_service.py     #   工厂 + 统一调用入口
│       │   ├── token_budget.py    #   4 级动态压缩策略
│       │   ├── message_builder.py #   多模态消息组装（DEPRECATED）
│       │   ├── qwen_adapter.py    #   Qwen（文本 + 视觉）
│       │   ├── zhipu_adapter.py   #   智谱 GLM（文本 + 视觉）
│       │   ├── mimo_adapter.py    #   小米 MiMo（文本 + 视觉 + 思维链）
│       │   ├── openai_adapter.py  #   OpenAI 兼容（含本地 llama）
│       │   └── claude_adapter.py  #   Anthropic Claude
│       │
│       ├── models/                # ═══ 共享数据结构 ═══
│       │   ├── enums.py           #   操作/状态/弹窗/供应商枚举
│       │   ├── action.py          #   Action & ActionParams
│       │   ├── perception.py      #   UINode / UITree / PerceptualResult
│       │   └── task.py            #   TaskContext / StepRecord
│       │
│       ├── prompts/               # ═══ Prompt 模板 ═══
│       │   ├── system_prompt.py   #   系统指令（输入流程强化 / 桌面导航规则）
│       │   ├── decision_prompt.py #   步骤决策模板（含输入框指引）
│       │   └── summary_prompt.py  #   历史摘要压缩
│       │
│       ├── reporting/             # ═══ 归档与报告 ═══
│       │   ├── archiver.py        #   DataArchiver：截图/XML/LLM 归档
│       │   └── report_generator.py #  Markdown 报告生成（表格转义防御）
│       │
│       ├── exception/             # ═══ 异常处理 ═══
│       │   ├── exceptions.py      #   自定义异常体系
│       │   ├── retry_policy.py    #   @retry 指数退避装饰器
│       │   └── error_handler.py   #   异常分类 + 恢复动作映射
│       │
│       └── testing/               # ═══ 批量测试执行器 ═══
│           └── __init__.py        #   BatchTestRunner：JSON/YAML/pytest 驱动
│
├── tests/                         # ═══ 测试套件（378 个用例）═══
│   ├── conftest.py                # 共享 fixtures
│   ├── test_config.py             # 配置管理
│   ├── test_enums.py              # 枚举值
│   ├── test_action.py             # Action 校验
│   ├── test_action_executor.py    # 动作分发
│   ├── test_wait_executor.py      # 等待执行
│   ├── test_adb_controller.py     # ADB 控制
│   ├── test_device_manager.py     # 设备管理
│   ├── test_ui_tree.py            # UI 树解析
│   ├── test_screen_capture.py     # 截图 fallback
│   ├── test_page_diff.py          # 页面变化检测
│   ├── test_popup_handler.py      # 弹窗处理
│   ├── test_llm_service.py        # LLM 工厂 + 能力选择
│   ├── test_message_builder.py    # 消息组装
│   ├── test_token_budget.py       # Token 预算
│   ├── test_mimo_adapter.py       # MiMo 适配器
│   ├── test_claude_adapter.py     # Claude 适配器
│   ├── test_orchestrator.py       # 任务编排
│   ├── test_step_runner.py        # 单步执行
│   ├── test_task_context.py       # 任务上下文
│   ├── test_decision_prompt.py    # 决策 Prompt
│   ├── test_perception.py         # 感知层
│   ├── test_error_handler.py      # 错误处理
│   ├── test_retry_policy.py       # 重试策略
│   ├── test_reporting.py          # 归档报告
│   └── test_test_runner.py        # 批量测试执行器
```

---

## 模块详解

### 架构设计（三层分离）

| 层级 | 包名 | 职责 | 平台相关性 |
|------|------|------|-----------|
| 核心层 | `core/` | 任务编排、步骤闭环、状态管理 | 跨平台（纯逻辑） |
| 适配层 | `device/`、`executor/`、`perception/`、`popup/` | Android 设备驱动、动作执行、屏幕感知、弹窗处理 | Android 专属 |
| 横切层 | `llm/`、`models/`、`prompts/`、`reporting/`、`exception/`、`testing/` | 跨层共享的服务与数据结构 | 跨平台 |

### core/ —— 任务编排层

| 模块 | 职责 | 关键方法 |
|------|------|----------|
| `TaskOrchestrator` | 任务生命周期管理、死循环检测、超时检测 | `execute_task()`、`_detect_loop()`、`_check_timeout()` |
| `StepRunner` | 单步"感知→弹窗→决策→解析→执行→验证→记录"闭环 | `run_step()`、`_decide_action()`、`_resolve_element_id()` |
| `TaskContext` | 任务状态容器，管理步骤记录与上下文数据 | `add_step()`、`is_completed()`、`is_timeout()` |

**StepRunner 单步闭环：**

```
步骤 1: ScreenCapture 双通道感知（截图 + UI 树）
步骤 2: 自动归档截图、XML、摘要
步骤 3: PopupHandler 弹窗检测（检测到则自动处理）
步骤 4: TokenBudget 预估 → 决策压缩策略
步骤 5: LLMService 决策（截图 + 摘要 + 历史 → Action）
步骤 6: 归档 LLM 请求/响应
步骤 7: ActionExecutor 执行动作
步骤 8: 二次感知 + 页面变化验证
```

### device/ —— 设备控制层

- **DeviceManager**（单例 + 线程锁）：连接生命周期管理、健康检查、自动选择设备、u2 优先 + ADB fallback
- **U2Controller**：uiautomator2 封装（click / screenshot / dump / swipe / app_start / long_click）
- **ADBController**：ADB fallback（shell / screencap / reconnect / wait_for_device），含 shell 注入防护

### perception/ —— 感知层

- **UITreeExtractor**：XML dump → 三份本地数据（local_index / structured_summary / spatial_index），约 6:1 压缩比；输入框（EditText/密码框）节点标记为 `输入框` 供 LLM 识别
- **ScreenCapture**：u2 截图优先，失败自动 fallback 到 ADB screencap；bytes / PIL Image 自动转换
- **PageChangeDetector**：UI 树结构 diff（70% 权重）+ SSIM 视觉比较（30% 权重）

### executor/ —— 动作执行层

ActionExecutor 接收 Action，校验参数后分发给子执行器：

| 执行器 | 处理的 ActionType |
|--------|------------------|
| ClickExecutor | CLICK / DOUBLE_CLICK / LONG_CLICK |
| TypeExecutor | TYPE / CLEAR_TEXT（先清空预填内容再输入） |
| SwipeExecutor | SWIPE / SWIPE_POINT（多段轨迹）/ SCROLL |
| WaitExecutor | WAIT |
| ActionExecutor 直接处理 | BACK / HOME / RECENT_APPS / OPEN_APP / CLOSE_APP / LOCK_SCREEN / OPEN_NOTIFICATIONS / ROTATE_SCREEN / VOLUME_UP / VOLUME_DOWN / TERMINATE / VERIFY |

### popup/ —— 弹窗处理

三策略检测 + 五策略处理 + 失败退出机制：

- **检测策略：** Dialog 关键词节点匹配 → 覆盖层检测（含屏幕尺寸防御）→ 特征文本匹配（≥2 种特征才判定）
- **处理策略：** ALLOW / DENY / DISMISS / CANCEL / REPORT_TO_LLM
- **失败退出：** 同一弹窗自动处理失败达 2 次后 `auto_handlable=False`，放行给 LLM 决策，避免死循环

### llm/ —— LLM 服务层

采用**工厂 + 适配器**架构：

```
LLMAdapter (base.py)                 ← 抽象基类（chat / count_tokens / close）
    ├── QwenAdapter     → DashScope 兼容接口（文本 + 视觉）
    ├── ZhipuAdapter    → 智谱开放平台（文本 + 视觉）
    ├── MiMoAdapter     → 小米开放平台（文本 + 视觉 + reasoning_content 思维链）
    ├── OpenAIAdapter   → OpenAI 兼容（DeepSeek / LongCat / 本地 llama 共用）
    └── ClaudeAdapter   → Anthropic（thinking 块防御）
            ↑
LLMServiceFactory.create(provider)   ← 按供应商名创建
LLMService                            ← 统一调用入口（chat / count_tokens）
```

模型能力（多模态 / 纯文本 / 上下文窗口）由配置注册表 `settings.models.models` 定义，添加新模型无需改代码。

---

## 多模型配置

所有供应商平级配置在 `settings.models.providers`，模型注册表在 `settings.models.models`。

### 支持的模型

| 供应商 | 模型 Key | 能力 | 上下文 | 工厂可用 |
|--------|---------|------|--------|---------|
| **MiMo**（默认多模态） | `mimo-omni` / `mimo-pro` | 多模态 / 纯文本 | 128K / 1M | ✅ |
| **Qwen** | `qwen-flash` / `qwen-plus` | 多模态 | 32K | ✅ |
| **Zhipu** | `zhipu-flash` / `zhipu-flashx` | 多模态 | 128K | ✅ |
| **OpenAI 兼容** | `openai` / `local` | 多模态 / 纯文本 | 依模型 | ✅ |
| **Claude** | `anthropic` | 多模态 | 依模型 | ✅ |
| **DeepSeek**（默认纯文本 key） | `deepseek-flash` | 纯文本 | 128K | ⚠️ 已配置未挂载 |
| **LongCat** | `longcat-flash` | 纯文本 | 128K | ⚠️ 已配置未挂载 |

> ⚠️ DeepSeek / LongCat 的 Provider 与模型已在 `config.py` 注册，但 `LLMServiceFactory._adapters` 尚未挂载对应适配器；如需使用，按 OpenAI 兼容协议调用或在工厂中注册 `OpenAIAdapter(provider="deepseek")`。

### 环境变量配置

```ini
# 默认模型
MODELS__DEFAULT_MULTIMODAL=mimo-omni
MODELS__DEFAULT_TEXT=deepseek-flash

# 供应商平级配置
MODELS__PROVIDERS__MIMO__API_KEY=sk-xxx
MODELS__PROVIDERS__MIMO__BASE_URL=https://api.xiaomimimo.com/v1
MODELS__PROVIDERS__QWEN__API_KEY=sk-xxx
MODELS__PROVIDERS__ZHIPU__API_KEY=xxx
MODELS__PROVIDERS__DEEPSEEK__API_KEY=sk-xxx
MODELS__PROVIDERS__LONGCAT__API_KEY=ak-xxx
```

### 模型选择

```python
# 创建默认供应商的适配器（settings.llm.provider，默认 mimo）
adapter = LLMServiceFactory.create()

# 指定供应商
zhipu = LLMServiceFactory.create("zhipu")
local = LLMServiceFactory.create("local")

# 注册新供应商（开闭原则）
LLMServiceFactory.register("custom", CustomAdapter)
```

---

## Token 智能压缩

每次调用 LLM 前自动进行 Token 预算检查，动态选择压缩策略。

| 策略 | 行为 | 触发条件 | Token 节省 |
|------|------|---------|-----------|
| `none` | 不压缩，发送全部历史 + 当前截图 | 预算充足 | 0 |
| `compress_history` | 只保留最近 5 条历史摘要 | 超出预算 | 约 50-80% 历史 Token |
| `drop_images` | 移除当前截图，历史压缩为首尾 | 超出预算 100% 以内 | 约 80-90% |
| `full_summary` | 移除截图，历史极端压缩 | 严重超预算 | 约 85-95% |

上下文窗口从模型注册表动态读取（`ModelEntry.context_window`），不再硬编码。

---

## 归档报告系统

每次任务执行自动归档所有步骤数据，并生成 Markdown 报告。

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
        └── report.md                 # 流程报告（含表格转义防御）
```

---

## 工作流程

```
用户输入自然语言目标
        │
        v
  TaskOrchestrator.execute_task()
        │
        ├── ① 创建 TaskContext + DataArchiver
        ├── ② 重置 TokenBudget
        │
        └── 循环: while not completed and step < max_steps
                │
                ├── 超时检查
                ├── StepRunner.run_step()
                │       ├── ScreenCapture → 双通道感知
                │       ├── PopupHandler → 弹窗检测
                │       ├── TokenBudget → 压缩策略决策
                │       ├── LLMService → 决策（多模态模型）
                │       ├── ActionExecutor → 执行动作
                │       └── PageChangeDetector → 验证变化
                │
                ├── TERMINATE / VERIFY 特殊动作处理
                ├── 记录步骤
                └── 死循环检测
        │
        └── 生成归档报告 (reports/.../report.md)
```

---

## 配置说明

配置基于 `pydantic-settings`，支持 `.env` 文件与环境变量注入，嵌套配置通过 `__` 分隔。

### 主要配置组

| 配置组 | 说明 |
|--------|------|
| `models` | 供应商平级配置 + 模型注册表 + 默认模型 + 思维链开关 |
| `llm` | 全局 LLM 配置（向后兼容） |
| `device` | 设备序列号、ADB 路径、默认分辨率 |
| `execution` | 最大步数、重试策略、截图质量、页面等待 |
| `perception` | SSIM 阈值、节点数上限、网格大小 |
| `popup` | 弹窗自动处理开关 |
| `loop_detection` | 死循环检测阈值 |
| `coordinate_tuning` | 坐标微调偏移 |
| `logger` | 日志目录、级别、轮转大小 |

### 核心环境变量

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `MODELS__DEFAULT_MULTIMODAL` | `mimo-omni` | 默认多模态模型 key |
| `MODELS__DEFAULT_TEXT` | `deepseek-flash` | 默认纯文本模型 key |
| `MODELS__ENABLE_REASONING` | `true` | 思维链开关（图片推理耗时场景可关闭） |
| `EXECUTION__MAX_STEPS_PER_TASK` | `30` | 单任务最大步数 |
| `EXECUTION__MAX_TOTAL_DURATION_SECONDS` | `300` | 单任务最大耗时 |
| `LOGGER__LOG_DIR` | `logs` | 日志根目录 |

---

## 测试与验证

### 单元测试

```bash
# 运行全部测试（378 个用例）
pytest tests/ -v

# 带覆盖率报告（门槛 60%）
pytest tests/ --cov=mobile_automation --cov-report=term-missing

# 运行特定模块
pytest tests/test_step_runner.py -v
pytest tests/test_llm_service.py -v
```

覆盖范围：数据结构、动作执行器、设备控制、感知（UI 树/截图/页面 diff）、弹窗处理、LLM 工厂与适配器、Token 预算、任务编排、单步闭环、错误处理与重试、归档报告、批量测试执行器。全部基于 mock，无需真实设备。

### 真机端到端验证

已在真实设备（MuMu 模拟器 `127.0.0.1:5555`，SM-S9210，Android 12）上验证：

| 场景 | 结果 |
|------|------|
| 输入流程专项（2026-08-01） | ✅ 3/3 通过：搜索框输入"原神 / 王者荣耀 / 和平精英"，click→type→terminate，输入真实生效 |
| 返回桌面 → 打开应用 → 搜索 → 查看详情 | ✅ 完整流程通过 |
| 弹窗检测与 LLM 上报 | ✅ 正常 |
| ADB 截图 fallback | ✅ 正常 |
| Token 压缩策略触发 | ✅ 正常 |

---

## 已知问题与路线图

| 问题 | 状态 |
|------|------|
| LLM Prompt 语义理解：type 替换预填内容时若不清空会文本拼接（搜索结果仍正确，计划增加 clear 语义） | ⏳ 待优化 |
| 弹窗检测偶发误报 | ✅ v1.3.1 加失败退出机制防死循环，特征过滤可继续优化 |
| StepRunner 上帝类（708 行，5 种职责耦合） | ⏳ 规划 v1.4.0 专项拆分 |
| 端到端批量测试通过率（6 用例 33%） | ⏳ 随模型 / Prompt 迭代提升 |

版本路线图见 [CHANGELOG.md](./CHANGELOG.md)。

---

## 依赖清单

### 核心依赖

| 包名 | 用途 |
|------|------|
| openai | OpenAI 兼容 SDK（Qwen / DeepSeek / LongCat / MiMo / 本地 llama） |
| anthropic | Claude API 调用 |
| uiautomator2 | Android UI 自动化（主要交互方式） |
| adbutils | ADB 设备管理 |
| Pillow | 图片缩放与格式转换 |
| opencv-python | SSIM 视觉比较 |
| scikit-image | structural_similarity 函数 |
| lxml | 高性能 XML dump 解析 |
| pydantic | 数据模型 |
| pydantic-settings | 环境变量驱动的配置体系 |
| python-dotenv | .env 文件加载 |

### 开发依赖

| 包名 | 用途 |
|------|------|
| pytest | 测试框架 |
| pytest-mock | mock 支持（无需真实设备） |
| pytest-asyncio | 异步测试支持 |
| pytest-cov | 测试覆盖率 |
