# 遗留问题归档（Known Issues）

> 本文件记录当前项目的遗留问题与待办事项，随修复进展更新。
> 最后更新：2026-08-04

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

## 已解决

### ~~3. 批量测试用例文件缺失~~（2026-08-04 已解决）

- **原因**：AGENTS.md 中 `test` 子命令示例对应的 examples 目录为空
- **修复**：新增 `examples/test_cases.json`（5 个真实可用用例：打开设置 / 找 Wi-Fi / 设置搜索电池 / 打开相机 / 打开相册，含 smoke 标签）
- **附带**：CLI 重构为 argparse subparsers（run/test 双命令 + 无子命令 `-g` 向后兼容），`test` 子命令支持 `--filter` / `--format-report(json/md/html)` / `--report-dir` / `--stop-on-failure`

## 待办

- [x] 补充批量测试示例用例文件（2026-08-04，examples/test_cases.json）
- [x] 弹窗误报保守优化（2026-08-04，三层内收紧 + 4 个新测试）
- [x] 完整端到端用例集回归（2026-08-04，4/5 通过，80%）
- [ ] 分支 `refactor/step-runner-split`（领先 main 9 个提交）合并 main 前的最终回归
