# mobile-automation —— 移动端 AI 自动化操作框架

基于 **Qwen-VL 多模态模型**驱动的 Android 自动化测试框架。用户通过自然语言描述任务目标，系统自动完成屏幕感知、UI 解析、操作决策与步骤执行。

| 项目 | 内容 |
|------|------|
| 默认 LLM | Qwen-VL-Max (DashScope 兼容接口) |
| Python 版本 | >= 3.10 |
| 设计原则 | element_id 优先定位 \| 双通道感知 \| 三份数据结构 \| Orchestrator + StepRunner 分离 |
| 架构模式 | Adapter 模式解耦 LLM 调用，支持切换 Qwen / OpenAI / Claude |

---

## 目录

- [核心能力](#核心能力)
- [快速开始](#快速开始)
- [项目结构](#项目结构)
- [模块详解](#模块详解)
- [Token 智能压缩](#token-智能压缩)
- [归档报告系统](#归档报告系统)
- [批量测试用例执行](#批量测试用例执行)
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
| 多 LLM 适配 | 默认 Qwen-VL (DashScope)，可切换 OpenAI / Claude |
| element_id 精确定位 | LLM 输出元素编号，系统从本地索引精确查找 resource-id 执行 |
| Token 智能压缩 | 4 级动态压缩策略，根据预算自动裁剪历史上下文或丢弃截图 |
| 归档报告系统 | 每步截图/XML/LLM 交互自动归档，任务结束生成完整 MD 流程报告 |
| 批量测试执行 | 支持测试用例列表批量执行，JSON 文件导入，失败隔离 |

---

## 快速开始

### 1. 安装依赖

```bash
# 核心依赖
pip install openai anthropic uiautomator2 Pillow opencv-python scikit-image lxml pydantic pydantic-settings python-dotenv

# 开发依赖（可选）
pip install pytest pytest-mock pytest-asyncio pytest-cov black ruff mypy
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，填写 LLM API Key 等配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件，至少需要设置：

```ini
LLM__API_KEY=sk-your-dashscope-api-key
```

### 3. 连接 Android 设备

通过 USB 连接 Android 设备并确认 ADB 可识别：

```bash
adb devices
```

### 4. 运行任务

```bash
python -m src.mobile_automation.main --goal "打开设置，找到 Wi-Fi 选项并截图"

# 指定设备和 LLM 提供商
python -m src.mobile_automation.main --goal "打开淘宝搜索手机" --serial xxxxxx --provider qwen --max-steps 50
```

### 5. 查看报告

任务执行完成后，在 `logs/reports/yy_mm_dd_hh_mm_ss/<task_id>/` 下查看流程报告：

```bash
logs/reports/
└── 26_06_26_23_30_00/           # 时间戳目录
    └── f31fdb94/                # 任务 ID
        ├── task_meta.json
        ├── step_01/
        │   ├── screenshot.png
        │   ├── screenshot_after.png
        │   ├── xml_raw.xml
        │   ├── summary.txt
        │   ├── llm_request.json
        │   └── llm_response.json
        ├── step_02/
        └── report.md            # 流程化报告
```

---

## 项目结构

```
Mobile_App_AutoTest/
│
├── pyproject.toml                 # 项目元数据、核心依赖与构建配置
├── .env.example                   # 环境变量示例
├── README.md                      # 项目说明文档
├── requirements.txt               # pip 依赖清单
│
├── logs/                          # 运行日志（自动按时间戳归档）
│   ├── 26_06_26_23_30_00/         #   logs/yy_mm_dd_hh_mm_ss/mobile_automation.log
│   └── reports/
│       └── 26_06_26_23_30_00/     #   归档报告 logs/reports/yy_mm_dd_hh_mm_ss/<task_id>/
│
├── src/
│   └── mobile_automation/         # 主包
│       │
│       ├── __init__.py            # 包入口
│       ├── config.py              # 【配置管理】8 组 pydantic-settings 配置
│       ├── logger.py              # 【日志系统】RotatingFileHandler + 时间戳子目录
│       ├── main.py                # 【CLI 入口】命令行参数解析与启动
│       │
│       ├── core/                  # ═══ 核心编排层 ═══
│       │   ├── orchestrator.py    #   任务级状态机 + 死循环检测 + Token 预算管理
│       │   ├── step_runner.py     #   单步闭环引擎（含 Token 压缩决策）
│       │   └── task_context.py    #   任务上下文
│       │
│       ├── models/                # ═══ 数据模型层 ═══
│       │   ├── enums.py           #   7 个枚举
│       │   ├── action.py          #   Action & ActionParams
│       │   ├── perception.py      #   UINode / UITree / UISpatialIndex
│       │   └── task.py            #   StepRecord / TaskContext
│       │
│       ├── device/                # ═══ 设备管理层 ═══
│       │   ├── device_manager.py  #   DeviceManager 单例
│       │   ├── u2_controller.py   #   uiautomator2 封装
│       │   └── adb_controller.py  #   ADB fallback
│       │
│       ├── perception/            # ═══ 感知层 ═══
│       │   ├── screen_capture.py  #   双通道截图
│       │   ├── ui_tree.py         #   【核心】XML → 三份数据
│       │   ├── page_diff.py       #   结构 diff + SSIM
│       │   └── image_util.py      #   图像工具
│       │
│       ├── llm/                   # ═══ LLM 服务层 ═══
│       │   ├── base.py            #   LLMAdapter 抽象基类
│       │   ├── qwen_adapter.py    #   DashScope 兼容接口
│       │   ├── openai_adapter.py  #   GPT-4o 标准 API
│       │   ├── claude_adapter.py  #   Anthropic Messages API
│       │   ├── llm_service.py     #   工厂 + 统一入口
│       │   ├── message_builder.py #   多模态消息组装
│       │   └── token_budget.py    #   Token 预算 + 4 级压缩策略
│       │
│       ├── prompts/               # ═══ Prompt 模板 ═══
│       │   ├── system_prompt.py   #   系统指令（含应用启动优先级）
│       │   ├── decision_prompt.py #   步骤决策 + 压缩策略感知
│       │   └── summary_prompt.py  #   历史摘要压缩
│       │
│       ├── executor/              # ═══ 动作执行层 ═══
│       │   ├── action_executor.py #   参数校验 + 分发调度
│       │   ├── click_executor.py  #   单击/双击/长按
│       │   ├── type_executor.py   #   文本输入/清空
│       │   ├── swipe_executor.py  #   滑动/轨迹滑动/滚动
│       │   └── wait_executor.py   #   等待/稳定
│       │
│       ├── popup/                 # ═══ 弹窗处理 ═══
│       │   ├── popup_handler.py   #   三策略检测 + 五策略处理
│       │   ├── pattern_rules.py   #   5 类预置规则
│       │   ├── classifier.py      #   图像分类器（预留）
│       │   └── models.py          #   弹窗数据模型
│       │
│       ├── reporting/             # ═══ 归档与报告 ═══
│       │   ├── archiver.py        #   DataArchiver：截图/XML/LLM 归档
│       │   └── report_generator.py #  ReportGenerator：MD 流程报告
│       │
│       ├── testing/               # ═══ 批量测试执行 ═══
│       │   └── __init__.py        #   BatchTestRunner + TestCase 定义
│       │
│       └── exception/             # ═══ 异常处理 ═══
│           ├── exceptions.py      #   7 层异常体系
│           ├── retry_policy.py    #   @retry 指数退避装饰器
│           └── error_handler.py   #   异常分类 + 恢复动作映射
│
└── tests/                         # ═══ 测试套件（21 个文件，265 个用例）═══
    ├── conftest.py                # 共享 fixtures
    ├── test_config.py             # 配置管理
    ├── test_enums.py              # 枚举值
    ├── test_action.py             # Action 校验
    ├── test_perception.py         # UINode / UITree / 空间索引
    ├── test_task_context.py       # TaskContext / StepRecord
    ├── test_retry_policy.py       # 重试装饰器
    ├── test_device_manager.py     # 设备管理
    ├── test_ui_tree.py            # UI 树解析
    ├── test_screen_capture.py     # 截图 fallback
    ├── test_page_diff.py          # 页面变化检测
    ├── test_llm_service.py        # LLM 工厂
    ├── test_message_builder.py    # 消息组装
    ├── test_token_budget.py       # Token 预算
    ├── test_popup_handler.py      # 弹窗处理
    ├── test_action_executor.py    # 动作分发
    ├── test_orchestrator.py       # 任务编排
    ├── test_step_runner.py        # 单步执行
    ├── test_reporting.py          # 归档报告
    ├── test_decision_prompt.py    # 【新增】Token 压缩策略
    └── test_test_runner.py        # 【新增】批量测试执行
```

---

## 模块详解

### core/ —— 核心编排层

| 模块 | 职责 | 关键方法 |
|------|------|----------|
| `TaskOrchestrator` | 任务级状态机，管理任务的创建→执行→完成/失败/中止全生命周期 | `execute_task()`、`_detect_loop()` |
| `StepRunner` | 单步执行闭环：感知→弹窗→LLM→解析→执行→验证→记录 | `run_step()`、`_decide_action()`、`_resolve_element_id()` |

**TaskOrchestrator 执行循环：**
```
while not done:
    1. 重置 Token 预算，绑定到 StepRunner
    2. 创建 DataArchiver，绑定到 StepRunner
    3. 循环执行 StepRunner.run_step()
    4. 死循环检测 / 超时检测
    5. 生成归档报告
```

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
步骤 9: 注册步骤归档元数据
```

### models/ —— 数据模型层

所有核心数据结构的定义，包含 7 个枚举类、Action/ActionParams、UINode/UITree/UISpatialIndex、PerceptualResult/PageChangeResult、StepRecord/TaskContext。

**三份数据设计（UITree）：**

| 数据 | 类型 | 用途 | 发送给 LLM？ |
|------|------|------|-------------|
| local_index | `Dict[str, UINode]` | 存储所有节点的完整属性 | 否 |
| structured_summary | `str` | 紧凑文本，仅含 LLM 决策所需信息 | 是 |
| spatial_index | `UISpatialIndex` | 基于网格的坐标反查 | 否 |

### device/ —— 设备管理层

- **DeviceManager**（单例模式）：管理设备连接生命周期，支持自动选择设备、健康检查、u2 优先 + ADB fallback
- **U2Controller**：19 个操作方法的 uiautomator2 封装（click/screenshot/dump/swipe/app_start 等）
- **ADBController**：ADB fallback 实现（shell/screenshot/reconnect/wait_for_device）

### perception/ —— 感知层

- **UITreeExtractor**（核心模块）：XML dump 解析 → 6 步数据流 → 三份本地数据。结构化摘要按区域分组（DIALOG/TOP_BAR/FEED/BOTTOM_NAV）+ 重叠集群检测，实现约 6:1 压缩比
- **ScreenCapture**：双通道截图，优先 u2，失败后自动 fallback 到 ADB screencap
- **PageChangeDetector**：UI 树结构 diff（70% 权重）+ SSIM 视觉比较（30% 权重）

### llm/ —— LLM 服务层

采用 **Adapter 模式**设计，通过 `LLMAdapter` 抽象基类定义统一接口：

```
LLMMessage (数据类)
    ↑
LLMAdapter (抽象基类)
    ├── QwenAdapter   → OpenAI SDK + DashScope 兼容接口 (32K 上下文)
    ├── OpenAIAdapter → OpenAI SDK + GPT-4o 标准 API (128K 上下文)
    └── ClaudeAdapter → Anthropic SDK + Messages API (200K 上下文)
            ↑
LLMServiceFactory.create(provider)  → 工厂创建
LLMService                          → 统一调用入口
```

- **MessageBuilder**：按 Qwen-VL 多模态格式组装消息，管理分层上下文（历史摘要文本 + 当前截图）
- **TokenBudgetManager**：Token 预算计算与 4 级动态压缩策略（详见 [Token 智能压缩](#token-智能压缩)）

### executor/ —— 动作执行层

ActionExecutor 接收 Action 对象，校验参数后分发给子执行器：

| 执行器 | 处理的 ActionType |
|--------|------------------|
| ClickExecutor | CLICK / DOUBLE_CLICK / LONG_CLICK |
| TypeExecutor | TYPE / CLEAR_TEXT |
| SwipeExecutor | SWIPE / SWIPE_POINT / SCROLL |
| WaitExecutor | WAIT |
| ActionExecutor 直接处理 | BACK / HOME / RECENT_APPS / OPEN_APP / CLOSE_APP |

**元素定位优先级：**
1. resource-id 精确匹配 → 2. text 匹配 → 3. 坐标点击 → 4. 空间索引反查

### popup/ —— 弹窗处理

三策略检测 + 五策略处理：

- **检测策略：** Dialog 关键词节点匹配 → 覆盖层检测（面积 > 60%）→ 特征文本匹配
- **处理策略：** ALLOW（允许）→ DENY（拒绝）→ DISMISS（关闭）→ CANCEL（取消）→ REPORT_TO_LLM（未知上报）

预置规则库 PatternRules 覆盖：权限请求、更新提示、广告弹窗、评分邀请、用户协议、系统警告。

### exception/ —— 异常处理

| 异常类型 | 示例场景 | 处理策略 |
|----------|---------|---------|
| DeviceConnectionError | 设备离线、ADB 断开 | 自动重连（最多 3 次） |
| PerceptionError | UI dump 失败、截图失败 | 切换截图方式（u2 → ADB） |
| LLMServiceError | API 超时、响应格式错误 | 指数退避重试 |
| ActionExecutionError | 元素未找到、点击无响应 | 切换定位方式 |
| LoopDetectedError | 重复相同操作超过阈值 | 终止任务 |
| TimeoutError | 页面加载超时 | 按策略等待或终止 |

**retry 装饰器**支持指数退避、可配置异常类型和回调函数。

---

## Token 智能压缩

系统在每次调用 LLM 前自动进行 Token 预算检查，根据已消耗 Token 和预估本次消耗，动态选择压缩策略。

### 压缩策略

| 策略 | 行为 | 触发条件 | Token 节省 |
|------|------|---------|-----------|
| `none` | 不压缩，发送全部历史 + 当前截图 | 预算充足 | 0 |
| `compress_history` | 只保留最近 5 条历史摘要 | 超出预算 50% 以内 | 约 50-80% 历史 Token |
| `drop_images` | 移除当前截图，历史压缩为首尾 | 超出预算 100% 以内 | 约 80-90% |
| `full_summary` | 移除截图，历史极端压缩 | 严重超预算 | 约 85-95% |

### 触发流程

```
StepRunner._decide_action()
  → 用摘要构建预览消息
  → TokenBudgetManager.estimate_messages_tokens()
  → needs_compression() → total_used + estimated > budget * 80%?
  → 是 → get_compression_strategy() 返回压缩策略
  → DecisionPromptBuilder.build(compression_strategy="compress_history")
  → 调用 LLM
  → record_usage(实际消耗)
```

### 上下文窗口

| 提供商 | 上下文窗口 | 输入预算 |
|--------|-----------|---------|
| Qwen | 32K | ~28K |
| OpenAI | 128K | ~124K |
| Anthropic | 200K | ~196K |

每次任务启动时 Token 计数器自动重置。

---

## 归档报告系统

每次任务执行时自动归档所有步骤数据，并生成流程化的 Markdown 报告。

### 归档目录结构

```
logs/reports/26_06_26_23_30_00/       # ← 时间戳 (yy_mm_dd_hh_mm_ss)
    └── f31fdb94/                     # ← 任务 ID
        ├── task_meta.json            # 任务元数据
        ├── step_01/
        │   ├── screenshot.png        # 操作前截图
        │   ├── screenshot_after.png  # 操作后截图
        │   ├── xml_raw.xml           # 原始 UI 树
        │   ├── summary.txt           # 结构化摘要
        │   ├── llm_request.json      # LLM 请求（Base64 自动替换占位符）
        │   └── llm_response.json     # LLM 响应
        ├── step_02/
        │   └── ...
        └── report.md                 # 流程化报告（截图 + 操作 + 日志）
```

### report.md 报告内容

```
# 移动端自动化任务报告

## 任务概览
  | 任务 ID | 用户目标 | 状态 | 步数 | 成功率 | Token
  步骤总览：✅ Step 01 → ✅ Step 02 → ✅ Step 03

## 操作流程时间线

### Step 01 — ✅ open_app
  > 状态: success | 耗时: 1234ms

  #### 界面截图
  | 操作前 | 操作后 |
  | <img width="280"/> | <img width="280"/> |

  #### 操作详情（表格）
  | 动作类型 | 包名 | LLM 决策理由 |

  #### LLM 决策过程（可折叠，含请求/响应）
  #### 执行日志（时间线风格代码块）
  #### 原始数据（📄 XML | 🤖 LLM 请求 | ...）
```

### 核心组件

- **DataArchiver**：负责将每一步的截图（PNG）、原始 XML、结构化摘要、LLM 请求/响应保存到时间戳目录
- **ReportGenerator**：读取归档数据，生成完整的 MD 流程报告，嵌入截图对比、操作表格、LLM 交互详情

---

## 批量测试用例执行

框架支持以测试用例列表驱动的批量自动化执行模式，适合回归测试和脚本化场景。

### TestCase 定义

| 字段 | 类型 | 说明 |
|------|------|------|
| `goal` | str | 用户任务目标描述 |
| `max_steps` | int | 本用例最大步数（0 表示用默认值） |
| `expected_status` | str | 预期状态: `completed` / `aborted` / `failed` |
| `description` | str | 用例描述 |
| `tags` | list[str] | 标签，用于分组筛选 |
| `timeout_seconds` | int | 用例级超时（0 表示用默认值） |

### Python API 方式

```python
from src.mobile_automation.testing import BatchTestRunner, TestCase

runner = BatchTestRunner(orchestrator)
cases = [
    TestCase(goal="打开设置，找到 Wi-Fi", max_steps=10, tags=["smoke"]),
    TestCase(goal="打开淘宝搜索手机", max_steps=15, expected_status="completed"),
    TestCase(goal="打开相机拍照", max_steps=8),
]
summary = runner.run_all(cases, stop_on_failure=False)
runner.save_report(summary, "logs/test_report.json")

print(f"通过: {summary.passed}/{summary.total}, 耗时: {summary.total_duration:.1f}s")
```

### JSON 文件方式

**test_cases.json:**
```json
[
    {
        "goal": "打开设置，找到 Wi-Fi",
        "max_steps": 10,
        "tags": ["smoke", "settings"]
    },
    {
        "goal": "打开淘宝搜索手机",
        "max_steps": 15,
        "expected_status": "completed",
        "description": "电商搜索测试"
    }
]
```

**执行：**
```python
runner.run_from_file("test_cases.json", output_path="logs/test_report.json")
```

### 特性

- **失败隔离**：一个用例失败不影响后续用例执行
- **stop_on_failure**：可选择遇到失败时立即停止
- **JSON 报告导出**：包含每个用例的详细结果（状态、步数、耗时、Token、错误信息）
- **与 pytest 集成**：可在 pytest 测试中使用 mock 的 Orchestrator 进行单元测试

---

## 工作流程

### 整体执行流程

```
用户输入自然语言目标
        │
        v
  TaskOrchestrator.execute_task()
        │
        ├── ① 创建 TaskContext
        ├── ② 重置 TokenBudgetManager
        ├── ③ 创建 DataArchiver
        │
        └── 循环: while not completed and step < max_steps
                │
                ├── 超时检测
                │
                ├── StepRunner.run_step()
                │       │
                │       ├── ScreenCapture.capture_with_ui_tree()
                │       │       └── 自动归档截图 + XML + 摘要
                │       │
                │       ├── PopupHandler.detect(ui_tree)
                │       │
                │       ├── TokenBudget 预估 → 压缩策略决策
                │       │
                │       ├── LLMService.chat(截图 + 摘要 + 历史)
                │       │       └── 自动归档 LLM 请求 + 响应
                │       │
                │       ├── _resolve_element_id → 坐标
                │       │
                │       ├── ActionExecutor.execute(action)
                │       │
                │       └── PageChangeDetector.compare()
                │               └── 成功 → 归档 / 失败 → 重试
                │
                ├── 记录步骤
                └── 死循环检测
        │
        └── 生成归档报告 (logs/reports/.../report.md)
```

### element_id 定位流程

```
LLM 输出: {"action_type": "click", "params": {"element_id": "#3"}}
                        │
                        v
            StepRunner._resolve_element_id("#3", ui_tree)
                        │
                        v
            UITree.get_by_element_id("#3") → UINode
                        │
                        v
            UINode.resource_id = "com.example.app:id/buy_now"
            UINode.center() = (920, 520)
                        │
                        v
            uiautomator2 执行:
            优先: u2(resourceId="com.example.app:id/buy_now").click()
            后备: u2.click(920, 520)
```

---

## 配置说明

配置系统基于 `pydantic-settings`，支持 `.env` 文件和系统环境变量两种方式。

### 配置分组

| 配置组 | 类名 | 说明 |
|--------|------|------|
| LLM | `LLMSettings` | 提供商、API Key、模型名、温度、超时 |
| 设备 | `DeviceSettings` | 序列号、ADB 路径、重连次数 |
| 执行 | `ExecutionSettings` | 最大步数、重试、截图层级、页面等待 |
| 感知 | `PerceptionSettings` | SSIM 阈值、节点数上限、网格大小 |
| 弹窗 | `PopupSettings` | 是否启用、权限/广告自动处理 |
| 死循环检测 | `LoopDetectionSettings` | 相同操作阈值、相似度阈值 |
| 坐标微调 | `CoordinateTuningSettings` | X/Y 偏移、缩放系数 |
| 日志 | `LoggerSettings` | 日志目录、级别、轮转大小 |

### 用法示例

```python
from src.mobile_automation.config import settings

provider = settings.llm.provider       # "qwen"
api_key = settings.llm.api_key         # 你的 API Key
max_steps = settings.execution.max_steps_per_task  # 30
```

### 关键配置项

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `LLM__PROVIDER` | `qwen` | LLM 提供商 |
| `EXECUTION__MAX_STEPS_PER_TASK` | `30` | 单任务最大步数 |
| `EXECUTION__MAX_TOTAL_DURATION_SECONDS` | `300` | 单任务最大耗时（秒） |
| `LOGGER__LOG_DIR` | `logs` | 日志根目录 |

---

## 测试

项目包含 **21 个测试文件，265 个测试用例**，使用 pytest + pytest-mock，无需真实设备。

```bash
# 运行全部测试
python -m pytest tests/ -v

# 运行特定模块测试
python -m pytest tests/test_ui_tree.py -v
python -m pytest tests/test_orchestrator.py -v

# 运行 Token 压缩策略测试
python -m pytest tests/test_decision_prompt.py -v

# 运行批量测试执行器测试
python -m pytest tests/test_test_runner.py -v

# 带覆盖率报告
python -m pytest tests/ --cov=src.mobile_automation --cov-report=term
```

测试覆盖：
- 数据结构测试：enums、action 校验、UINode、UITree、空间索引
- 业务逻辑测试：StepRunner 闭环、Orchestrator 状态机、死循环检测
- LLM 层测试：Adapter 创建、消息组装、Token 预算、**4 级压缩策略**
- 异常测试：重试装饰器、ErrorHandler 分类、参数校验
- 归档报告测试：DataArchiver 文件保存、ReportGenerator MD 生成
- **批量测试执行**：TestCase 定义、BatchTestRunner 批量执行、JSON 导入/导出
- Mock 场景：设备列表解析、截图 fallback、UI 树 XML 解析、弹窗检测

---

## 依赖清单

### 核心依赖

| 包名 | 最低版本 | 用途 |
|------|---------|------|
| openai | >=1.0.0 | Qwen DashScope 兼容接口 + OpenAI GPT-4o 调用 |
| anthropic | >=0.30.0 | Claude API 调用 |
| uiautomator2 | >=2.16.0 | Android 设备 UI 自动化控制（主要交互方式） |
| Pillow | >=10.0.0 | 图片缩放与格式转换 |
| opencv-python | >=4.8.0 | SSIM 视觉比较（可选） |
| scikit-image | >=0.21.0 | structural_similarity 函数 |
| lxml | >=4.9.0 | 高性能 XML dump 解析 |
| pydantic | >=2.0.0 | 数据模型和配置管理 |
| pydantic-settings | >=2.0.0 | 环境变量驱动的配置体系 |
| python-dotenv | >=1.0.0 | .env 文件加载 |

### 开发依赖

| 包名 | 最低版本 | 用途 |
|------|---------|------|
| pytest | >=7.0.0 | 测试框架 |
| pytest-mock | >=3.0.0 | mock 支持（无需真实设备） |
| pytest-asyncio | >=0.21.0 | 异步测试支持 |
| pytest-cov | >=4.0.0 | 测试覆盖率 |
| black | >=23.0.0 | 代码格式化 |
| ruff | >=0.1.0 | 代码检查 |
| mypy | >=1.0.0 | 类型检查 |

### 安装方式

```bash
# 核心依赖
pip install openai anthropic uiautomator2 Pillow opencv-python scikit-image lxml pydantic pydantic-settings python-dotenv

# 开发依赖
pip install pytest pytest-mock pytest-asyncio pytest-cov black ruff mypy

# 一键安装全部
pip install -r requirements.txt
```

> 或使用 uv（推荐）：
> ```bash
> uv pip install -r requirements.txt
> ```
