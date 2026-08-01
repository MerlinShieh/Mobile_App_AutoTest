# Mobile_App_AutoTest 项目规范

> 本文件用于 Mobile_App_AutoTest 项目目录下自动加载的上下文规范。

## 项目概述

移动端 AI 自动化测试框架，使用多模态大模型（Qwen-VL）驱动 Android 设备自动化操作。

- **位置**：`wsl2：/mnt/c/Users/Mulin/Documents/Mobile_App_AutoTest（windows：C:\Users\Mulin\Documents\Mobile_App_AutoTest）`
- **语言**：Python 3.10+
- **包管理**：uv / pip，venv 在 `.venv/`
- **测试框架**：pytest

## 架构设计（方案B 三层分离）

```
mobile_automation/
├── framework/          ← 跨平台核心（orchestrator, step_runner, logger, hooks）
├── mobile/             ← Android 专属适配层
│   ├── device/         ← ADB / u2 设备控制
│   ├── executor/       ← 动作执行器（click/swipe/type/wait/back）
│   ├── perception/     ← 截图/UI树/页面差异
│   └── popup/          ← 弹窗检测与处理
├── llm/                ← 横切基础服务
│   ├── adapters/       ← 统一适配器 + 能力注册表
│   │   ├── unified_adapter.py  ← 统一 OpenAI 兼容适配器
│   │   ├── qwen_adapter.py     ← Qwen 多模态
│   │   ├── zhipu_adapter.py    ← 智谱 GLM 多模态
│   │   ├── deepseek_adapter.py ← DeepSeek 纯文本
│   │   └── longcat_adapter.py  ← LongCat 纯文本
│   ├── llm_service.py  ← 工厂模式 + 能力选择
│   └── token_budget.py ← 4级动态压缩策略
├── models/             ← 共享数据结构
├── prompts/            ← Prompt 模板（中英双语）
├── reporting/          ← 归档与报告生成
└── exception/          ← 异常处理与错误恢复

## 默认设备配置（依据adb devices 输出）

| 项目 | 值 |
|------|-----|
| 设备地址 | `127.0.0.1:5555` |
| 设备型号 | SM-S9210 |
| Android 版本 | 12 |
| 分辨率 | 1080×1920 |

## 大模型配置

| 供应商 | 默认模型 | 能力 | API 端点 |
|--------|---------|------|----------|
| **MiMo** | mimo-v2.5 | 多模态（文本+视觉+思维链） | `https://api.xiaomimimo.com/v1` |
| **Qwen** | qwen3.6-flash | 多模态（文本+视觉） | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| **Zhipu** | glm-4.1v-thinking-flash | 多模态 | `https://open.bigmodel.cn/api/paas/v4` |
| **DeepSeek** | deepseek-v4-flash | 纯文本 | `https://api.deepseek.com` |
| **LongCat** | LongCat-2.0 | 纯文本 | `https://api.longcat.chat/openai` |
| **Local** | LocalModel | 纯文本（llama-server 本地） | `http://localhost:8080/v1` |

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

**测试数据：**
- 单元测试：371 个，100% 通过
- 端到端自动测试：6 用例，通过率 33%（2/6）

## 已知问题

1. **LLM Prompt 语义理解**：模型只点击搜索框不输入文本 → 需要优化 decision_prompt（Prompt 已强化，需端到端验证）
2. **弹窗检测误报**：仍偶发误报，v1.3.1 已加处理失败退出机制（自动处理失败达 2 次后放行 LLM）防死循环 → 特征文本过滤仍可继续优化
3. **StepRunner 上帝类**：708 行，5 种职责耦合 → 拆分方案已出，待专项执行

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

