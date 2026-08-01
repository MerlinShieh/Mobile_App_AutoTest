# 领域词汇表

## 核心概念

- **Mobile Automation Framework**: 移动端AI自动化测试框架，使用多模态大模型驱动Android设备操作
- **Step Runner**: 步骤执行器，负责执行单个操作步骤（点击、输入、滑动等）
- **Orchestrator**: 编排器，管理测试用例的执行流程
- **Device Manager**: 设备管理器，负责ADB和u2设备连接和控制
- **Perception Layer**: 感知层，负责截图、UI树获取、页面差异检测
- **LLM Adapters**: 大模型适配器，统一接口支持多模型（Qwen、Zhipu、DeepSeek等）
- **Token Budget**: Token预算管理器，动态压缩上下文以适应模型限制
- **Popup Handler**: 弹窗处理器，检测和处理各类弹窗、权限请求、广告等
- **Decision Prompt**: 决策提示词，引导LLM分析当前状态并决定下一步操作

## 设备相关

- **ADB (Android Debug Bridge)**: Android调试桥，用于设备通信
- **u2 (uiautomator2)**: Android UI自动化工具，提供更丰富的UI操作
- **Screen Capture**: 截图功能，获取设备当前屏幕图像
- **UI Tree**: UI层次结构，获取当前页面的所有UI元素及其属性
- **Page Diff**: 页面差异检测，比较前后两次页面状态的变化

## LLM相关

- **Multimodal Model**: 多模态模型，支持文本+视觉输入（如Qwen-VL、Zhipu GLM-4V）
- **Text-only Model**: 纯文本模型，仅支持文本输入（如DeepSeek、LongCat）
- **Model Registry**: 模型注册表，管理所有可用模型的配置和能力
- **Prompt Template**: 提示词模板，预定义的LLM输入格式
- **CoT (Chain of Thought)**: 思维链推理，让LLM逐步思考决策过程

## 操作相关

- **Click**: 点击操作，点击屏幕指定坐标或UI元素
- **Type**: 输入操作，向输入框输入文本
- **Swipe**: 滑动操作，在屏幕上执行滑动手势
- **Back**: 返回操作，模拟设备返回按钮
- **Wait**: 等待操作，等待指定时间或条件
- **Lock Screen**: 熄屏操作，关闭设备屏幕
- **Open Notifications**: 打开通知栏，从顶部下拉显示通知
- **Rotate Screen**: 旋转屏幕，改变设备显示方向
- **Volume Up/Down**: 音量调节，增加或减少设备音量

## 质量相关

- **Popup False Positive**: 弹窗误报，将正常UI元素错误识别为弹窗
- **Token Compression**: Token压缩，减少上下文长度以适应模型限制
- **Context Window**: 上下文窗口，LLM一次能处理的最大token数
- **Unit Test**: 单元测试，验证单个函数或模块的功能
- **End-to-End Test**: 端到端测试，验证完整用户场景

## 架构分层

- **Framework Layer**: 跨平台核心层，包含orchestrator、step_runner、logger、hooks
- **Mobile Layer**: Android专属适配层，包含device、executor、perception、popup
- **LLM Layer**: 大模型横切层，包含adapters、llm_service、token_budget
- **Models Layer**: 共享数据结构层，定义所有数据模型
- **Prompts Layer**: 提示词模板层，包含中英双语的prompt模板
- **Reporting Layer**: 报告生成层，负责测试结果归档和报告生成
- **Exception Layer**: 异常处理层，统一错误处理和恢复机制

## 关键模式

- **Factory Pattern**: 工厂模式，用于创建LLM适配器和模型实例
- **Singleton Pattern**: 单例模式，用于设备管理和全局配置
- **Strategy Pattern**: 策略模式，用于不同的Token压缩策略
- **Observer Pattern**: 观察者模式，用于日志记录和事件通知
- **Adapter Pattern**: 适配器模式，统一不同LLM的接口