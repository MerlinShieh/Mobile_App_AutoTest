# Mobile_App_AutoTest 项目规范

> 本文件用于 Mobile_App_AutoTest 项目目录下自动加载的上下文规范。

## 项目概述

移动端 AI 自动化测试框架，使用多模态大模型（Qwen-VL）驱动 Android 设备自动化操作。

- **位置**：`windows：C:\Users\Mulin\Documents\Mobile_App_AutoTest`
- **语言**：Python 3.10+
- **环境**：Windows 11（需要考虑Linux和MacOS环境兼容）
- **包管理**：uv / pip，venv 在 `.venv/`
- **测试框架**：pytest

## 架构设计（方案B 三层分离）

```
mobile_automation/
├── core/                 ← 核心编排（orchestrator, step_runner, task_context）
│   └── pipelines/        ← 拆分后的独立流水线（v1.4.0）
│       ├── perception_pipeline.py  ← 感知 + 弹窗处理 + 操作前归档
│       ├── execution_pipeline.py   ← 执行验证 + 步骤归档
│       └── decision_engine.py      ← LLM 决策 + 响应解析 + 坐标解析
├── device/               ← Android 设备控制（ADB / u2）
│   ├── device_manager.py ← 设备管理器（连接/健康检查/屏幕尺寸）
│   ├── adb_controller.py ← ADB 控制
│   └── u2_controller.py  ← u2 控制
├── executor/             ← 动作执行器（click/swipe/type/wait/back）
│   ├── action_executor.py
│   ├── click_executor.py
│   ├── swipe_executor.py
│   ├── type_executor.py
│   └── wait_executor.py
├── perception/           ← 截图/UI树/页面差异
│   ├── screen_capture.py ← 截图与 UI 树获取
│   ├── ui_tree.py        ← UI 树解析
│   ├── page_diff.py      ← 页面差异对比
│   └── image_util.py     ← 图像工具
├── popup/                ← 弹窗检测与处理
│   ├── popup_handler.py  ← 弹窗处理器
│   ├── classifier.py     ← 弹窗分类
│   ├── pattern_rules.py  ← 模式规则
│   └── models.py         ← 弹窗数据结构
├── llm/                  ← 横切基础服务（扁平结构，无独立适配器子包）
│   ├── base.py           ← LLMMessage 数据类 + LLMAdapter 抽象基类
│   ├── qwen_adapter.py   ← Qwen 多模态
│   ├── openai_adapter.py ← OpenAI 兼容适配器（DeepSeek/LongCat/Local 复用）
│   ├── claude_adapter.py ← Anthropic Claude
│   ├── zhipu_adapter.py  ← 智谱 GLM 多模态
│   ├── mimo_adapter.py   ← 小米 MiMo 多模态
│   ├── llm_service.py    ← 工厂模式 + 能力选择
│   ├── message_builder.py ← 已弃用（由 DecisionPromptBuilder 替代）
│   └── token_budget.py   ← 4级动态压缩策略
├── models/               ← 共享数据结构（action/enums/perception/task）
├── prompts/              ← Prompt 模板（中英双语）
├── reporting/            ← 归档与报告生成
├── exception/            ← 异常处理与错误恢复
└── testing/              ← 测试运行器
```

## 设备选择

- 设备动态获取：不预设固定设备，以 `adb devices` 输出为准，默认选择第一个状态为 `device` 的设备
- 可通过 CLI `-s <serial>` 参数或配置 `DEVICE__SERIAL` 显式指定设备

## 大模型配置

| 供应商 | 默认模型 | 能力 | 适配器 | API 端点 |
|--------|---------|------|--------|----------|
| **MiMo** | mimo-v2.5 | 多模态（文本+视觉+思维链） | MiMoAdapter | `https://api.xiaomimimo.com/v1` |
| **Qwen** | qwen3.6-flash | 多模态（文本+视觉） | QwenAdapter | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| **Zhipu** | glm-4.1v-thinking-flash | 多模态 | ZhipuAdapter | `https://open.bigmodel.cn/api/paas/v4` |
| **DeepSeek** | deepseek-v4-flash | 纯文本 | OpenAIAdapter（复用） | `https://api.deepseek.com` |
| **LongCat** | LongCat-2.0 | 纯文本 | OpenAIAdapter（复用） | `https://api.longcat.chat/openai` |
| **Local** | LocalModel | 纯文本（llama-server 本地） | OpenAIAdapter（复用） | `http://localhost:8080/v1` |

> DeepSeek / LongCat / Local 均为 OpenAI 兼容协议，复用 OpenAIAdapter（无独立适配器文件），
> 由 provider 参数驱动从 `settings.models.providers` 读取各自配置。

**多模态默认**：mimo-omni（`MODELS__DEFAULT_MULTIMODAL` 可覆盖）
**纯文本默认**：deepseek-flash（`MODELS__DEFAULT_TEXT` 可覆盖）
**思维链开关**：`MODELS__ENABLE_REASONING`（默认 true，图片推理耗时可关闭）

## 当前项目状态

**已完成：**
- 模块化架构（core 编排 + device/executor/perception/popup + llm 横切层）
- 多模型适配重构（统一适配器 + 模型注册表，支持 Qwen/Zhipu/MiMo/DeepSeek/LongCat/本地 llama）
- CoT 思维链 Prompt 引导（`MODELS__ENABLE_REASONING` 可关闭）
- 弹窗检测误报修复（三层过滤 + 屏幕尺寸防御）
- u2 截图类型修复（bytes/PIL Image 自动转换）
- u2 连接超时保护（30s）
- 报告格式标准化（纯 Markdown，含特殊字符转义）
- 日志自动初始化
- 异常体系重构（ErrorHandler 集成重连/指数退避恢复）
- 行尾符规范化（.gitattributes, LF）
- StepRunner 上帝类拆分（v1.4.0：core/pipelines 三个独立流水线 + 薄编排层）

**测试数据：**
- 单元测试：410 个，100% 通过
- 端到端自动测试：6 用例，通过率 33%（2/6）
- 2026-08-01 真机输入流程专项验证：3/3 通过（搜索框输入原神/王者荣耀/和平精英）
- 2026-08-02 v1.4.1 真机验证：3/3 通过（打开设置 / 设置搜索"电池" / 预填替换"电池"→"王者荣耀"无拼接）

## 已知问题

1. **LLM 输入文本拼接**：v1.4.1 已在 TypeExecutor 执行器层增加预填清空（`click → clear_text → send_text`），Prompt 层指引与执行器层兜底双重保障
2. **弹窗检测误报**：仍偶发误报，v1.3.1 已加处理失败退出机制（自动处理失败达 2 次后放行 LLM）防死循环；v1.4.1 新增碰撞案例锁定测试（4 例），不改过滤逻辑

## 常用命令

```bash
# 首次设置
cd /mnt/c/Users/Mulin/Documents/Mobile_App_AutoTest
python -m venv .venv
. .venv/Scripts/activate  # Windows
pip install -r requirements.txt

# 运行单元测试
python -m pytest tests/ -v

# 运行覆盖率测试
python -m pytest --cov=mobile_automation --cov-report=term-missing tests/

# CLI 单次执行
python -m mobile_automation.main run -g "打开设置"

# 交互式模式
python -m mobile_automation.main interactive

# 批量测试（JSON）
python -m mobile_automation.main test ./examples/test_cases.json

# 批量测试（YAML）
python -m mobile_automation.main test ./examples/test_cases.yaml

# 批量测试（带筛选和HTML报告）
python -m mobile_automation.main test ./examples/test_cases.json --filter smoke --format-report html
```

## 编码规范

- 使用 `pathlib.Path` 处理路径
- 日志使用 `get_logger()` 获取，禁止 print
- Windows 兼容：路径用 `/` 分隔
- 截图数据统一为 `bytes` 类型
- API Key 从 `.env` 读取，禁止硬编码
- 所有 `open()` 调用显式指定 `encoding="utf-8"`
- 运行/调试项目时，若未明确指定 Python 解释器，优先使用项目 `.venv` 环境（`.venv\Scripts\python.exe`），禁止直接使用全局 Python

## 风险规避

- 操作前检查 `adb devices` 设备连接状态
- API 调用设置超时（u2 连接 30s，LLM 调用 30s）
- 日志输出使用 `errors="replace"` 防止编码崩溃
- Windows 下 stdout/stderr 使用 `reconfigure(encoding="utf-8")`

## 协作与输出规范
- 开发新功能输出内容
  • 改动文件列表、核心逻辑说明
  • 适配的LLM模型、设备兼容性说明
  • 新增的单元测试用例、覆盖率变化
  • 需要用户手动验证的端到端场景、潜在兼容性风险
- 修复Bug输出内容
  • Bug触发场景、复现方法
  • 修复方案、影响范围
  • 验证方法、是否引入其他风险
  • 对应的单元测试/端到端用例更新情况
- 测试优化输出内容
  • 优化前后的测试通过率、覆盖率对比
  • 修改的Prompt内容、适配的设备场景
  • 需要用户验证的端到端用例列表
- 风险规避
  • 操作前检查 adb devices 设备连接状态，禁止在未连接设备的情况下运行端到端测试
  • API 调用设置超时（u2 连接 30s，LLM 调用 30s）
  • 日志输出使用 errors="replace" 防止编码崩溃
  • Windows 下 stdout/stderr 使用 reconfigure(encoding="utf-8")
  • 修改decision_prompt时必须先跑至少3次端到端测试验证效果，不允许随意修改弹窗检测的三层过滤逻辑，除非用户明确要求
- 禁止事项
  • 禁止硬编码API Key、设备地址、分辨率等敏感配置
  • 禁止未经用户确认修改常用命令参数、默认LLM模型配置
  • 禁止降低现有测试覆盖率、删除已有的单元测试用例
  • 禁止擅自升级依赖包版本，避免引入兼容性问题
  • 禁止清空测试报告目录、删除已有的测试归档文件
  • 禁止关闭日志输出、修改日志格式为纯文本以外的格式
  • 大量改动时拆分提交，不要一次推送所有修改，方便代码回滚
---
**当前下项目已连接github仓库https://github.com/MerlinShieh/Mobile_App_AutoTest**

