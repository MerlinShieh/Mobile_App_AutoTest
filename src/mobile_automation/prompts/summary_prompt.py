"""
历史摘要压缩提示词常量。

SUMMARY_PROMPT 用于将历史步骤的 UI 描述压缩为简洁摘要，
在保留关键交互信息的同时大幅降低 Token 消耗。
"""

SUMMARY_PROMPT = """请将以下移动设备页面的 UI 描述压缩为简洁的摘要，保留关键的可交互元素信息。
格式要求：
- 保留 element_id、clickable 状态、text 和 resource-id
- 删除 bounds 坐标、不可见元素和纯容器节点
- 输出不超过 500 字符"""
