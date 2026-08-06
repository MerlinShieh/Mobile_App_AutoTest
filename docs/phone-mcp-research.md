# phone-mcp 研究报告与本地项目优化建议

> 研究日期：2026-08-06
> 研究对象：https://github.com/hao-cyber/phone-mcp（ADB 驱动的 Android 手机控制 MCP 服务，244 星）
> 本地项目：Mobile_App_AutoTest（多模态 LLM 自动化测试框架）

---

## 一、phone-mcp 是什么

纯 ADB 驱动的 Android 手机控制 **MCP 服务**（Python）。AI 助手（Cursor/Claude 等）通过自然语言调用它暴露的 18 个工具，实现对手机的**系统级控制**。核心：`asyncio` 直调 `adb shell` 命令 + 官方 `FastMCP` 协议，每个工具返回 JSON 字符串。

**功能清单**（按能力分组）：

| 类别 | 工具 |
|------|------|
| 通话 | 拨号、挂断、来电检测（`dumpsys telephony.registry` 解析） |
| 短信 | 发短信（UI 自动化点发送）、读收件箱/已发（`content query sms`） |
| 通讯录 | 读联系人（6 级降级含 sqlite 直查）、创建联系人 |
| 应用 | 启动（`am start -n` + monkey fallback）、列出、强制停止、闹钟 |
| 系统 | 当前窗口/前台应用/屏幕状态（`dumpsys` 多路拼装）、快捷方式 |
| 媒体 | 录屏（`screenrecord`）、播放/暂停（keyevent） |
| 屏幕 | `analyze_screen` 屏幕结构化分析、`interact_with_screen` 统一交互（tap/swipe/key/text/find/wait/scroll 七类）、UI 变化监控（MD5 快照 diff） |
| 地图 | 高德周边 POI 搜索（REST API，无 Key 不注册工具） |
| 其他 | 浏览器打开 URL、设备连接检查（ADB server 自愈） |

**关键实现范式**：`uiautomator dump` → XML 解析 → bounds 算中心坐标 → `input tap` 的「文本找控件 → 坐标点击」闭环；文本输入 4 级降级（input text → URI 广播 → 逐字符 → keyevent）；截图 5 路径降级 + stdout 直采。

**核心架构**：
- `core.py`：`run_command`（异步 subprocess 封装，统一超时 30s + terminate 兜底）+ `check_device_connection`（`adb devices` + kill/start-server 自愈重试 3 次）
- 工具层：12 个业务模块（apps/call/contacts/interactions/maps/media/messaging/screen_interface/system/ui/ui_enhanced/ui_monitor），每个导出 async 函数返回 JSON 字符串
- MCP 组装：`FastMCP("phone_call")` + 显式逐行 `mcp.tool()(func)` 注册 + stdio 传输；无 Key 工具条件注册
- 双入口：`phone-mcp`（MCP 服务器）+ `phone-cli`（argparse CLI，复用同一套 tools 函数）

---

## 二、本地项目 vs phone-mcp 对比

| 维度 | 本地 Mobile_App_AutoTest | phone-mcp |
|------|------------------------|-----------|
| 驱动方式 | u2 为主 + ADB fallback | 纯 ADB subprocess |
| 决策层 | 多模态 LLM（截图+UI树）→ Action | 无视觉模型，纯规则/语义 |
| 点击定位 | element_id → 坐标 + ui_element 双重定位 | 文本/坐标点击 |
| UI 树 | lxml 解析 + 三份索引 + 空间网格 + 区域摘要 | XML 解析 + bounds |
| 短信/通话/通讯录 | **无** | 有（content provider + intent） |
| 地图/媒体/剪贴板/通知 | **无** | 部分有 |
| app 管理（装/卸/清数据） | **无**（仅启/停） | 有启动/列出/停止 |
| 系统操作 | 旋转/音量/锁屏/通知栏 | dumpsys 状态读取 |
| 降级策略 | u2→ADB 双通道 | 多层降级（4-6 级） |
| 对外接口 | CLI | MCP 服务 |
| 输入文本 | u2.send_keys（无编码问题） | 拼音转换（workaround） |

**定位差异**：本地是「多模态 LLM 自动化**测试框架**」，phone-mcp 是「**系统级控制工具集**」。本地 UI 自动化深度远超 phone-mcp（坐标解析、页面 diff、弹窗处理都是它没有的），但**系统级能力几乎为零**。

---

## 三、优化建议（按价值分级）

### 🔴 高价值（建议实施）

1. **补系统级能力**（本地测试场景刚需）
   - **短信读取**：`content query --uri content://sms/inbox` — 自动化测试中短信验证码场景的必备能力
   - **通话检测**：`dumpsys telephony.registry` 解析来电状态
   - **剪贴板**：`cmd clipboard get/set` 或 `content` — 复制粘贴场景
   - **通知读取**：`dumpsys notification --noredact` — 检测推送
   - 优先级：短信 > 剪贴板 > 通知 > 通话

2. **ADB 命令封装补全**（adb_controller.py 目前缺 input tap/swipe/text、am、pm、dumpsys）
   - 本地 ADB 层没有 `input tap/swipe/text`（全走 u2）——u2 会话异常时 ADB 直调是有效兜底
   - `am start`（app 启动 ADB 通道）、`pm`（包管理）补全后，与 u2 双通道更完整

3. **MCP 化改造**（参考其 FastMCP 接入，**当前阶段暂不涉及**）
   - 本地框架能力远超 phone-mcp，若暴露为 MCP 服务，任何支持 MCP 的 AI 宿主都能直接驱动自动化框架
   - 已有 CLI 层（run/test 子命令），包装一层 MCP 适配即可

### 🟡 中价值（按需）

4. **多层降级策略**：文本输入、截图、联系人读取的多级 fallback 思路值得吸收——本地截图已有 u2→ADB 双通道，可借鉴「多路径 + 验证 + 终极 fallback」模式
5. **等待/滚动封装**：`wait_for_element` 轮询 + `scroll_to_element`（按屏幕比例算滑动轨迹）可补充本地 WaitExecutor 的场景
6. **无配置不注册**：地图工具「无 Key 即不注册」的优雅降级，可应用到本地可选能力

### ⚪ 不建议照搬

- 拼音输入（本地 u2.send_keys 无编码问题，反而更优）
- 坐标盲点发送按钮（异形屏脆弱，本地有 UI 树定位更好）

---

## 四、结论

本地项目的**多模态 UI 自动化能力已远超 phone-mcp**，缺的是**系统级操作能力**（短信/剪贴板/通知/通话）和**对外 MCP 接口**。优先补短信读取 + 剪贴板（测试刚需），再做 MCP 化改造。

## 五、实施记录

| 日期 | 项目 | 提交 | 状态 |
|------|------|------|------|
| 2026-08-06 | 短信读取能力 | - | 待实施 |
| 2026-08-06 | 剪贴板能力 | - | 待实施 |
| 2026-08-06 | 通知读取能力 | - | 待实施 |
| 2026-08-06 | 通话检测能力 | - | 待实施 |
| 2026-08-06 | ADB 命令封装补全 | - | 待实施 |
| - | MCP 化改造 | - | 暂不涉及 |
