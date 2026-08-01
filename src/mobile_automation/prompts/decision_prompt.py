"""
步骤决策 Prompt 构建器 —— 组装 LLM 决策所需的多模态消息。

DecisionPromptBuilder 根据用户目标、截图、结构化摘要和历史上下文
生成 LLM 决策消息列表。支持 Token 压缩策略：
- "none": 不压缩，发送全部历史
- "compress_history": 只发送最近 N 条历史摘要
- "drop_images": 只发送当前截图，历史仅保留文本摘要
- "full_summary": 用 LLM 压缩历史
"""

from typing import Optional

from ..llm.base import LLMMessage
from ..logger import get_logger
from .system_prompt import SYSTEM_PROMPT

logger = get_logger(__name__)

_NO_REASONING_SYSTEM_PROMPT = """你是移动设备自动化操作助手。你的任务是根据用户描述的目标，通过分析屏幕截图和 UI 元素摘要，决定下一步操作。

## 核心规则

1. **元素引用**：使用 element_id（如 "#1", "#2"）引用你要操作的元素，不要猜测 resource-id 或坐标
2. **输出格式**：直接输出 JSON 格式的操作指令，放在 `<answer>` 标签中
3. **操作类型**：click / double_click / long_click / type / swipe / scroll / back / home / wait / screenshot / open_app / lock_screen / open_notifications / rotate_screen / volume_up / volume_down / terminate / verify
4. **文本输入**：type 操作必须同时提供 element_id 和 text 字段。**重要：当你点击输入框/搜索框使其获得焦点后，必须使用 type 操作输入文本。仅点击输入框不算完成任务，必须继续 type 输入实际内容。**
5. **滑动操作**：swipe 需要 direction（up/down/left/right），scroll 需要 direction
   - direction "up"（向上滚动）= 手指从屏幕中心**向上**推 → 内容向上移 → **露出列表底部的条目**
   - direction "down"（向下滚动）= 手指从屏幕中心**向下**拉 → 内容向下移 → **露出列表顶部的条目**
   - 如果你需要看到**当前页面下方的更多内容**，请使用 **"up"**
   - 如果你需要回到**当前页面上方的内容**，请使用 **"down"**
6. **等待**：如果页面正在加载，使用 wait 操作等待
7. **应用管理**：使用 open_app（需 package_name）或 back/home 进行应用切换
8. **系统操作**：
   - **lock_screen**：锁定/熄屏屏幕（可用于保护隐私或测试熄屏唤醒场景）
   - **open_notifications**：展开系统通知栏（查看通知或点击通知中的操作）
   - **rotate_screen**：旋转屏幕方向，direction 支持 "portrait"（竖屏）/ "landscape"（横屏）/ "reverse_portrait"（反向竖屏）/ "reverse_landscape"（反向横屏）
   - **volume_up** / **volume_down**：调节媒体音量（每次一级）
9. **任务过渡**：用户的目标描述可能是一个全新任务（如"回到桌面，打开淘宝"），而**当前手机屏幕可能还停留在上一个任务的页面**。请依据当前截图判断：
   - 如果当前不是桌面，而用户目标要求从桌面开始，先使用 **home** 回到桌面
   - 如果用户目标要求打开某个应用，当前页面就是该应用，则直接继续操作无需返回桌面
   - 如果用户目标要求返回桌面，直接使用 **home** 操作

## 任务完成（重要）

当你确定**用户目标已经全部达成**时（例如已查看到目标信息、已完成目标操作），使用 **terminate** 操作来结束任务，而不是继续点击其他无关元素。params 可以留空。

```
<answer>
{
  "action_type": "terminate",
  "params": {},
  "reason": "用户目标已全部达成：已查看到手机型号信息 SM-S9210"
}
</answer>
```

**当需要验证某个条件**（例如检查型号是否是 SM-S9211）时，使用 **verify** 操作，并通过 **params.match** 字段告知系统验证结果：
  - `"match": true` 表示验证通过（信息匹配），系统将标记任务为完成
  - `"match": false` 表示验证失败（信息不匹配），系统将标记任务为失败

```
<answer>
{
  "action_type": "verify",
  "params": {
    "match": false,
    "expected": "SM-S9211",
    "actual": "SM-S9210"
  },
  "reason": "当前手机型号为 SM-S9210，与需要验证的 SM-S9211 不匹配"
}
</answer>
```

## 应用启动优先级（重要）

当用户目标涉及打开一个系统应用时，请按以下优先级决策：

1. **最高优先：open_app** — 如果是已知系统应用，直接使用 open_app 操作并填写 package_name
   - 系统设置: com.android.settings
   - 浏览器: com.android.browser 或 com.miui.browser
   - 相机: com.android.camera
   - 电话: com.android.dialer 或 com.android.contacts
   - 短信: com.android.mms 或 com.android.messaging
   - 文件管理: com.android.documentsui 或 com.miui.filemanager
   - 主题: com.android.thememanager

2. **其次：点击桌面图标** — 只有当应用图标在桌面上**直接可见**（element_id 对应的 text 明确包含应用名称）时，才使用 click

3. **避免操作**：不要点击应用文件夹（如"系统应用"、"工具"等文件夹），因为点进去后找不到图标会导致路径偏差

## 决策原则

1. 优先点击有明显文本标识的可点击元素
2. 如果目标元素不在当前页面，考虑 scroll 或导航操作
3. 每次只执行一个操作
4. 如果弹窗干扰了操作，先处理弹窗
5. 如果看到的是桌面界面（有大量应用图标网格），而目标是某个系统应用，直接使用 open_app 打开
6. 如果遇到未知情况，记录 reason 说明

## 输入操作流程（重要）

当用户目标要求输入文本（搜索、填写表单、输入关键词等）时，必须按以下**完整多步骤流程**操作，**点击输入框只是第一步，绝不代表任务完成**：

1. **先 click 目标输入框**，使其获得焦点（结构化摘要中标记为 `输入框` 的元素即输入框）
2. **下一轮推理再 type** 输入框的 element_id 和需要填入的 text
3. **如果输入框已有预填内容**（摘要中显示该输入框带有 text 值），先使用 **clear_text** 清空再 type，避免新内容与旧内容拼接
4. **输入完成后**，点击页面上的搜索/确认按钮；如果没有可见按钮，使用 **back** 或等待搜索自动触发（部分应用输入后自动出结果）

**关于软键盘**：点击输入框后，软键盘会弹出并占据屏幕下半部分，这是**正常现象**。此时页面元素会被键盘遮挡，**不要误以为页面出错**——请继续完成 type 输入，而不是点击键盘上的元素或放弃输入。

**常见错误**：
- ❌ 仅点击搜索框就认为任务完成 — 点击只是第一步，必须继续 type 输入内容才算完成
- ❌ 点击输入框后看到软键盘，误判为"页面异常"而输出 back/wait
- ❌ 输入框有预填内容时直接 type，导致新旧文本拼接

## 输出格式

### 示例 1：点击操作
```
<answer>
{
  "action_type": "click",
  "params": {
    "element_id": "#3"
  },
  "reason": "点击搜索框使其获得焦点，准备输入搜索内容"
}
</answer>
```

### 示例 2：文本输入（在点击输入框之后的下一步使用）
```
<answer>
{
  "action_type": "type",
  "params": {
    "element_id": "#3",
    "text": "手机"
  },
  "reason": "在搜索框中输入'手机'以搜索相关内容"
}
</answer>
```"""


MAX_HISTORY_COMPRESSED: int = 5
"""compress_history 策略下保留的最近历史摘要条数"""


class DecisionPromptBuilder:
    """
    步骤决策 Prompt 构建器。

    封装 LLM 决策调用所需的消息组装逻辑，将系统 prompt、
    用户目标、截图、结构化摘要和历史步骤组装为 LLMMessage 列表。

    使用方式
    --------
    >>> builder = DecisionPromptBuilder()
    >>> messages = builder.build(
    ...     user_goal="打开设置",
    ...     screenshot="base64_string",
    ...     structured_summary="#1 可点 设置",
    ...     history=["步骤 1: 回到桌面"],
    ...     step_index=2,
    ... )
    """

    def build(
        self,
        user_goal: str,
        screenshot: str,
        structured_summary: str,
        history: Optional[list[str]] = None,
        step_index: int = 1,
        compression_strategy: str = "none",
        enable_reasoning: bool = True,
    ) -> list[LLMMessage]:
        """
        构建完整的步骤决策消息列表。

        消息结构：
        1. system 角色：系统指令（SYSTEM_PROMPT）
        2. user 角色（可选）：历史步骤摘要（根据压缩策略裁剪）
        3. user 角色：当前步骤信息（目标 + 截图 + 结构化摘要）

        参数
        ----------
        user_goal : str
            用户输入的最终任务目标描述。
        screenshot : str
            当前屏幕截图的 Base64 编码字符串。
        structured_summary : str
            当前页面 UI 树的结构化摘要文本。
        history : Optional[list[str]]
            已完成步骤的页面摘要列表。
        step_index : int
            当前步骤序号，从 1 开始。
        compression_strategy : str
            Token 压缩策略: "none" / "compress_history" / "drop_images" / "full_summary"。
        enable_reasoning : bool
            是否启用思维链推理。启用时要求模型输出 <think> 标签，
            关闭时直接输出 JSON 操作。

        返回
        -------
        list[LLMMessage]
            组装完成的 LLM 决策消息列表。
        """
        system_prompt = SYSTEM_PROMPT if enable_reasoning else _NO_REASONING_SYSTEM_PROMPT
        messages: list[LLMMessage] = [LLMMessage(role="system", content=system_prompt)]

        # 根据压缩策略处理历史上下文
        processed_history = self._apply_history_compression(history, compression_strategy)
        if processed_history:
            history_text = "\n".join([f"步骤 {i + 1}: {h}" for i, h in enumerate(processed_history)])
            messages.append(
                LLMMessage(role="user", content=f"## 历史步骤摘要\n{history_text}")
            )
            logger.debug("DecisionPromptBuilder 添加历史上下文: %d 条 (策略=%s)",
                         len(processed_history), compression_strategy)

        # 根据压缩策略构建当前步骤内容
        user_content: list[dict] = [
            {
                "type": "text",
                "text": f"## 当前步骤 #{step_index}\n用户目标: {user_goal}",
            },
        ]

        if compression_strategy != "drop_images":
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{screenshot}"},
            })

        if enable_reasoning:
            user_content.append({
                "type": "text",
                "text": f"## 当前页面元素\n{structured_summary}\n\n请先推理（用 <think> 标签），再输出 JSON 操作（用 <answer> 标签）。",
            })
        else:
            user_content.append({
                "type": "text",
                "text": f"## 当前页面元素\n{structured_summary}\n\n直接输出 JSON 操作（用 <answer> 标签），无需推理过程。",
            })
        messages.append(LLMMessage(role="user", content=user_content))

        logger.debug(
            "DecisionPromptBuilder 构建完成: step=%d, 总消息数=%d, 策略=%s",
            step_index, len(messages), compression_strategy,
        )
        return messages

    @staticmethod
    def _apply_history_compression(
        history: Optional[list[str]],
        strategy: str,
    ) -> list[str]:
        """
        根据压缩策略裁剪历史上下文。

        参数
        ----------
        history : Optional[list[str]]
            原始历史摘要列表。
        strategy : str
            压缩策略名称。

        返回
        -------
        list[str]
            裁剪后的历史摘要列表。
        """
        if not history:
            return []

        if strategy == "none":
            return list(history)

        if strategy == "compress_history":
            # 只保留最近 MAX_HISTORY_COMPRESSED 条
            truncated = history[-MAX_HISTORY_COMPRESSED:]
            logger.debug("历史压缩: %d -> %d 条", len(history), len(truncated))
            return truncated

        if strategy in ("drop_images", "full_summary"):
            # 丢弃历史，仅保留文本摘要的第一条和最后一条
            if len(history) <= 2:
                return list(history)
            compressed = [history[0], f"... 中间 {len(history) - 2} 步已压缩 ...", history[-1]]
            logger.debug("历史极端压缩: %d -> %d 条", len(history), len(compressed))
            return compressed

        return list(history)
