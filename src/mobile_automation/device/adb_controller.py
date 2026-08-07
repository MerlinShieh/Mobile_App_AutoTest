"""
ADB 控制器封装模块。

提供对 Android Debug Bridge 的命令行封装，作为 uiautomator2
不可用时的 fallback 方案。支持截图、shell 命令、重连等基础操作。
"""

import re
import shlex
import subprocess
import time
from typing import Optional

from ..config import settings
from ..logger import get_logger

logger = get_logger(__name__)


class ADBController:
    """
    ADB 控制器（uiautomator2 的 fallback 方案）。

    通过调用 adb 命令行工具与 Android 设备交互。当 uiautomator2
    会话异常断开或不可用时，使用此控制器执行基础设备操作。

    参数
    ----------
    serial : str
        目标设备的序列号。
    max_retries : int
        ADB 命令执行失败时的最大重试次数，默认 3。
    """

    # shell 注入防御：合法 ADB 命令（input/settings/wm/statusbar/keyevent 等）
    # 不应包含这些 shell 元字符。检测到即拒绝执行。
    _SHELL_INJECTION_PATTERN = re.compile(
        r"[\n;&|><$`]|\b(?:rm|mv|dd|reboot|su|sh)\b",
        re.IGNORECASE,
    )

    # 短信读取支持的类型（对应 content://sms 的 URI 段）
    _SMS_TYPES = ("inbox", "sent")

    # content query 行解析（命令不带 projection/sort-order/limit，Row 行
    # 为完整字段行，字段顺序在不同 ROM 上不固定，故逐字段独立匹配）：
    # - address 不含逗号/空白（NULL 原样保留）
    # - date 为毫秒时间戳数字
    # - body 非贪婪，取到下一个字段名（, 字段名=）或行尾
    _SMS_ADDRESS_PATTERN = re.compile(r"address=([^,\s]+)")
    _SMS_DATE_PATTERN = re.compile(r"date=(\d+)")
    _SMS_BODY_PATTERN = re.compile(r"body=(.*?)(?:,\s*[a-z_]+=|$)")

    # dumpsys notification 输出中 NotificationRecord 段落定位：
    # 形如 NotificationRecord(0x0197e345 pkg=com.android.mms user=... )，
    # 捕获 pkg 之后的包名（到空白或右括号为止）。
    _NOTIFICATION_RECORD_PATTERN = re.compile(
        r"NotificationRecord\(\s*0x[0-9a-fA-F]+\s*:?\s+pkg=([^\s\)]+)"
    )

    # dumpsys window 输出中的焦点应用定位（优先于 mCurrentFocus 使用）：
    # mFocusedApp=ActivityRecord{hash u0 包名/Activity tN}
    _FOCUSED_APP_PATTERN = re.compile(
        r"mFocusedApp=ActivityRecord\{[^}]*\s([A-Za-z0-9_.]+/[A-Za-z0-9_.]+)\s+t\d+\}"
    )

    # dumpsys telephony.registry 通话状态码 → 人类可读名
    # （对应 PhoneConstants.CALL_STATE_IDLE/RINGING/OFFHOOK）
    _CALL_STATE_NAMES = {0: "idle", 1: "ringing", 2: "offhook"}

    # 通话状态字段定位：mCallState 可能出现在输出多处，取第一个有效值
    _CALL_STATE_PATTERN = re.compile(r"mCallState=(\d+)")

    # 来电号码字段定位：值取到行尾或首个逗号，防止与同行其他字段粘连
    _CALL_INCOMING_NUMBER_PATTERN = re.compile(r"mCallIncomingNumber=([^\r\n,]*)")

    # 包名校验：仅允许字母数字、下划线与点（对应 Android 包名规范）
    _PACKAGE_PATTERN = re.compile(r"^[a-zA-Z0-9_.]+$")

    # wm size 输出中的物理分辨率定位：形如 "Physical size: 1440x3200"
    _PHYSICAL_SIZE_PATTERN = re.compile(r"Physical size:\s*(\d+)x(\d+)")

    def __init__(self, serial: str, max_retries: int = 3) -> None:
        self.serial: str = serial
        self.max_retries: int = max_retries
        logger.debug("ADBController 初始化，设备: %s", serial)

    def _adb_cmd(self, args: list[str]) -> list[str]:
        """
        构建完整的 adb 命令参数列表。

        参数
        ----------
        args : list[str]
            附加的 adb 子命令与参数列表。

        返回
        -------
        list[str]
            完整的 adb 命令参数，形如 [adb_path, "-s", serial, ...]。
        """
        return [settings.device.adb_path, "-s", self.serial] + args

    @classmethod
    def _validate_shell_command(cls, command: str) -> None:
        """
        校验 shell 命令合法性，拒绝注入风险命令。

        拒绝规则：
        - 空命令或纯空白命令
        - 包含 shell 元字符（; & | > < $ ` 换行）的命令
        - 包含危险系统命令关键字（rm/mv/dd/reboot/su/sh）的命令

        参数
        ----------
        command : str
            待校验的 shell 命令字符串。

        异常
        ------
        ValueError
            命令为空或疑似注入时抛出。
        """
        if not command or not command.strip():
            raise ValueError("ADB shell 命令不能为空")

        if cls._SHELL_INJECTION_PATTERN.search(command):
            raise ValueError(f"ADB shell 命令含可疑字符，已拒绝执行: {command!r}")

    def shell(self, command: str, timeout: int = 30) -> tuple[str, str]:
        """
        在设备上执行 ADB shell 命令。

        执行前会校验命令合法性，拒绝空命令与疑似注入的命令。

        参数
        ----------
        command : str
            要执行的 shell 命令字符串。
        timeout : int
            命令执行超时（秒），默认 30。

        返回
        -------
        tuple[str, str]
            (标准输出, 标准错误) 的文本内容。

        异常
        ------
        ValueError
            命令为空或含注入风险字符时抛出。
        """
        self._validate_shell_command(command)
        cmd = self._adb_cmd(["shell", command])
        logger.debug("执行 ADB shell: %s", " ".join(cmd))
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if result.returncode != 0:
                logger.warning("ADB shell 返回非零: %s, stderr: %s", command, result.stderr.strip())
            return result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            logger.error("ADB shell 超时: %s", command)
            raise
        except Exception as exc:
            logger.error("ADB shell 执行异常: %s", exc)
            raise

    def screenshot(self, timeout: int = 30) -> bytes:
        """
        通过 ADB screencap 截取设备屏幕。

        返回
        -------
        bytes
            PNG 格式的原始图片字节数据。
        """
        cmd = self._adb_cmd(["exec-out", "screencap", "-p"])
        logger.debug("执行 ADB 截图")
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=timeout)
            if result.returncode != 0:
                logger.error("ADB 截图失败，returncode: %d", result.returncode)
                raise RuntimeError(f"ADB 截图失败，returncode: {result.returncode}")
            logger.debug("ADB 截图成功，大小: %d 字节", len(result.stdout))
            return result.stdout
        except subprocess.TimeoutExpired:
            logger.error("ADB 截图超时")
            raise
        except Exception as exc:
            logger.error("ADB 截图异常: %s", exc)
            raise

    def reconnect(self) -> bool:
        """
        尝试重新连接设备。

        先尝试 adb reconnect 命令；如果失败则重启 adb server。
        每次尝试后等待 2 秒让设备重新上线。

        返回
        -------
        bool
            True 表示重连操作已触发（不保证设备已完全就绪）。
        """
        logger.info("尝试重连设备: %s", self.serial)

        # 尝试 adb reconnect
        try:
            result = subprocess.run(
                self._adb_cmd(["reconnect"]),
                capture_output=True, timeout=10,
            )
            if result.returncode == 0:
                logger.info("adb reconnect 成功")
                time.sleep(2)
                return True
            else:
                logger.warning("adb reconnect 返回非零: %s", result.stderr.strip())
        except Exception as exc:
            logger.warning("adb reconnect 异常: %s", exc)

        # fallback: 重启 adb server
        try:
            logger.info("尝试重启 ADB server")
            subprocess.run(
                [settings.device.adb_path, "kill-server"],
                capture_output=True, timeout=10,
            )
            time.sleep(1)
            subprocess.run(
                [settings.device.adb_path, "start-server"],
                capture_output=True, timeout=10,
            )
            time.sleep(2)
            logger.info("ADB server 重启完成")
            return True
        except Exception as exc:
            logger.error("ADB server 重启失败: %s", exc)
            return False

    def lock_screen(self) -> None:
        """
        锁定/熄屏设备（toggle 操作）。

        通过 ADB 发送 KeyEvent 26（电源键）切换屏幕锁定状态。
        此操作为 toggle 性质：若屏幕当前亮起则锁定；若已锁定则可能
        唤醒屏幕。调用方应确保在屏幕亮起时调用以获得锁定效果。
        """
        self.shell("input keyevent 26")
        logger.info("设备已执行熄屏/电源键操作")

    def open_notifications(self) -> None:
        """
        展开系统通知栏。

        通过 ADB statusbar 命令展开通知面板。部分定制 ROM 可能
        不支持此命令，此时可考虑通过滑动屏幕顶部下拉替代。
        """
        self.shell("cmd statusbar expand-notifications")
        logger.info("通知栏已展开")

    def get_sms_messages(self, sms_type: str = "inbox", limit: int = 20) -> list[dict]:
        """
        读取设备短信（系统级能力）。

        通过 content provider 查询短信数据库，支持收件箱与已发送，
        按时间倒序返回。每条消息包含 address（号码）、body（内容）、
        date（毫秒时间戳，已转为 int）。

        参数
        ----------
        sms_type : str
            短信类型："inbox"（收件箱）或 "sent"（已发送），默认 "inbox"。
        limit : int
            最多返回的条数，默认 20。

        返回
        -------
        list[dict]
            短信列表，每项形如 {"address": str, "body": str, "date": int}；
            无结果、命令失败或解析失败时返回空列表（容错，不抛异常）。

        异常
        ------
        ValueError
            sms_type 非法、serial 含注入字符或 limit 非法时抛出。
        """
        # 1. 参数校验
        if sms_type not in self._SMS_TYPES:
            logger.warning("无效的短信类型: %s，仅支持 inbox/sent", sms_type)
            raise ValueError(f"无效的短信类型: {sms_type!r}，仅支持 inbox/sent")

        try:
            limit = int(limit)
        except (TypeError, ValueError):
            logger.warning("无效的 limit: %r，必须为整数", limit)
            raise ValueError(f"limit 必须是整数: {limit!r}")
        if limit < 0:
            logger.warning("无效的 limit: %d，不能为负数", limit)
            raise ValueError(f"limit 不能为负数: {limit}")

        # serial 虽作为独立参数传入 subprocess 不经 shell 解析，仍统一做注入防御
        if self._SHELL_INJECTION_PATTERN.search(self.serial):
            logger.warning("serial 含可疑字符，已拒绝读取短信: %r", self.serial)
            raise ValueError(f"serial 含可疑字符，已拒绝执行: {self.serial!r}")

        # 2. 构造并执行 content query 命令
        # 部分定制 ROM 的 content query 不支持 --projection/--sort-order/
        # --limit 参数（报 usage），故不带任何附加参数；由 Python 侧
        # 按 date 降序排序并截取 limit 条
        command = f"content query --uri content://sms/{sms_type}"
        try:
            stdout, stderr = self.shell(command)
        except Exception as exc:
            logger.error("读取短信命令执行异常: %s", exc)
            return []

        # 3. 命令失败判定：输出无效或 stderr 非空均视为失败，容错返回空列表
        if not isinstance(stdout, str) or not stdout.strip():
            logger.warning("读取短信命令无有效输出，stderr: %s", stderr)
            return []
        if stderr.strip():
            logger.warning("读取短信命令返回 stderr，视为失败: %s", stderr.strip())
            return []

        # 4. 解析 content query 输出（逐行，跳过无法解析的行）
        # Row 行为完整字段行（_id/thread_id/address/.../body/...），
        # body 可能含中文、逗号与 URL，逐字段独立正则提取
        messages: list[dict] = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line or not line.startswith("Row:"):
                continue
            address_match = self._SMS_ADDRESS_PATTERN.search(line)
            date_match = self._SMS_DATE_PATTERN.search(line)
            if not address_match or not date_match:
                logger.warning("短信行解析失败（缺 address/date），跳过: %s", line)
                continue
            body_match = self._SMS_BODY_PATTERN.search(line)
            body = body_match.group(1).strip() if body_match else ""
            try:
                date = int(date_match.group(1))
            except ValueError:
                logger.warning("短信日期解析失败，跳过: %s", date_match.group(1))
                continue
            messages.append(
                {
                    "address": address_match.group(1).strip(),
                    "body": body,
                    "date": date,
                }
            )

        # 5. 命令不带 --sort-order，Python 侧按 date 降序排序并截取 limit 条
        messages.sort(key=lambda item: item["date"], reverse=True)
        messages = messages[:limit]

        logger.info("读取短信完成，类型: %s，条数: %d", sms_type, len(messages))
        return messages

    def get_clipboard(self) -> str:
        """
        读取系统剪贴板文本（系统级能力，Android 10+）。

        优先通过 `service call clipboard 1`（TRANSACTION_getPrimaryClip）
        读取剪贴板 Parcel 中的 UTF-16 文本（部分定制 ROM 无 `cmd clipboard`
        命令）；该通道失败时回退到 `cmd clipboard get`。剪贴板为空
        （Parcel 内为 "No items"）、命令失败、无权限或 shell 异常时
        返回空字符串（容错，不抛异常）。

        返回
        -------
        str
            剪贴板文本（已 trim）；失败或为空时返回 ""。

        异常
        ------
        ValueError
            serial 含注入字符时抛出。
        """
        # serial 虽作为独立参数传入 subprocess 不经 shell 解析，仍统一做注入防御
        if self._SHELL_INJECTION_PATTERN.search(self.serial):
            logger.warning("serial 含可疑字符，已拒绝读取剪贴板: %r", self.serial)
            raise ValueError(f"serial 含可疑字符，已拒绝执行: {self.serial!r}")

        # 主通道：service call clipboard 1（该 ROM 无 cmd clipboard）
        text = self._get_clipboard_via_service_call()
        if text is not None:
            logger.info("读取剪贴板完成（service call），长度: %d", len(text))
            return text

        # 回退通道：cmd clipboard get（标准 ROM）
        try:
            stdout, stderr = self.shell("cmd clipboard get")
        except Exception as exc:
            logger.error("读取剪贴板命令执行异常: %s", exc)
            return ""

        # 命令失败判定：输出无效或 stderr 非空均视为失败，容错返回空字符串
        if not isinstance(stdout, str) or not stdout.strip():
            logger.warning("读取剪贴板命令无有效输出，stderr: %s", stderr)
            return ""
        if stderr.strip():
            logger.warning("读取剪贴板命令返回 stderr，视为失败: %s", stderr.strip())
            return ""

        text = stdout.strip()
        logger.info("读取剪贴板完成（cmd clipboard），长度: %d", len(text))
        return text

    def _get_clipboard_via_service_call(self) -> Optional[str]:
        """
        通过 service call 读取剪贴板文本（无 cmd clipboard 的 ROM 通道）。

        `service call clipboard 1` 返回 Parcel，剪贴板文本为 UTF-16LE 编码
        （跳过前 8 字节头）。剪贴板为空时文本为 "No items"。

        返回
        -------
        Optional[str]
            剪贴板文本；空剪贴板返回 ""；命令失败、stderr 非空或 Parcel
            解析失败返回 None（表示该通道不可用，由调用方回退 cmd clipboard）。
        """
        try:
            stdout, stderr = self.shell("service call clipboard 1")
        except Exception as exc:
            logger.warning("service call 读取剪贴板异常: %s", exc)
            return None
        if not isinstance(stdout, str) or not stdout.strip():
            return None
        if stderr.strip():
            logger.warning(
                "service call 剪贴板返回 stderr，回退 cmd clipboard: %s",
                stderr.strip(),
            )
            return None

        raw = self._extract_parcel_hex(stdout)
        if not raw:
            logger.warning("service call 剪贴板输出无有效 Parcel 数据，回退 cmd clipboard")
            return None

        text = self._decode_clipboard_payload(raw)
        # 空剪贴板：Parcel 内为 UTF-16LE 的 "No items"
        if text == "No items":
            logger.info("剪贴板为空（service call 返回 No items）")
            return ""
        # 解码为空或含不可见控制字符（可能含长度字段等额外结构），
        # 视为格式不匹配，回退 cmd clipboard
        if not text or any(ord(ch) < 32 and ch not in "\t\n\r" for ch in text):
            logger.warning(
                "service call 剪贴板解码异常（无内容或含控制字符），回退 cmd clipboard"
            )
            return None
        return text

    @staticmethod
    def _extract_parcel_hex(output: str) -> bytes:
        """
        从 service call 输出的 Parcel 中提取数据字节。

        兼容两种输出格式：
        - 多行块格式：``0x00000000: 00000000 006f004e '........N.o'``
        - 单行格式：``Result: Parcel(00000000 006f004e ...)``

        返回
        -------
        bytes
            拼接后的 Parcel 原始字节；无法解析时返回 b""。
        """
        hex_parts: list[str] = []
        for line in output.splitlines():
            # 去掉行内 ASCII 注解（单引号片段），避免误提取 hex 字符
            line = re.sub(r"'[^']*'", "", line)
            # 单行 Parcel(...) 格式
            match = re.search(r"Parcel\(\s*([0-9a-fA-F\s]+?)\s*\)", line)
            if match:
                hex_parts.append(match.group(1))
                continue
            # 多行块格式：冒号后为 4 字节一组的数据
            match = re.search(r":\s*([0-9a-fA-F]{8}(?:\s+[0-9a-fA-F]{8})*)", line)
            if match:
                hex_parts.append(match.group(1))
        if not hex_parts:
            return b""
        joined = "".join(hex_parts).replace(" ", "").replace("\t", "")
        # service call 以 4 字节小端字显示（如 006f004e 对应内存 4e 00 6f 00），
        # 需按字节对（每 2 个 hex 字符）倒序翻转还原真实字节
        flipped_hex = "".join(
            "".join(joined[i : i + 8][j : j + 2] for j in range(6, -1, -2))
            for i in range(0, len(joined), 8)
        )
        try:
            return bytes.fromhex(flipped_hex)
        except ValueError:
            return b""

    @staticmethod
    def _decode_clipboard_payload(raw: bytes) -> str:
        """
        将剪贴板 Parcel 数据解码为 UTF-16LE 文本。

        跳过前 8 字节 Parcel 头，按 2 字节小端解码，遇 0x0000 截断。

        返回
        -------
        str
            解码后的文本；无有效数据时返回 ""。
        """
        payload = raw[8:]
        chars: list[str] = []
        for i in range(0, len(payload) - 1, 2):
            code = payload[i] | (payload[i + 1] << 8)
            if code == 0:
                break
            chars.append(chr(code))
        return "".join(chars)

    def set_clipboard(self, text: str) -> bool:
        """
        写入系统剪贴板文本（系统级能力，Android 10+）。

        通过 `cmd clipboard set` 写入剪贴板。文本经 shlex.quote 转义，
        保证含空格/引号等特殊字符时在设备 shell 中正确传参。

        注意：部分定制 ROM（如 MIUI/HyperOS）不提供 cmd clipboard 服务
        （get 需经 service call 通道读取）；该 ROM 上 set 需手工构造
        ClipData Parcel 过于复杂，保持现状不支持——命令失败时返回 False
        并记录警告日志。

        参数
        ----------
        text : str
            要写入剪贴板的文本内容。

        返回
        -------
        bool
            True 表示写入成功（shell 执行成功且无 stderr）；
            False 表示失败（text 为空/None、shell 失败或异常，容错不抛出）。

        异常
        ------
        ValueError
            serial 含注入字符时抛出。
        """
        # serial 虽作为独立参数传入 subprocess 不经 shell 解析，仍统一做注入防御
        if self._SHELL_INJECTION_PATTERN.search(self.serial):
            logger.warning("serial 含可疑字符，已拒绝写入剪贴板: %r", self.serial)
            raise ValueError(f"serial 含可疑字符，已拒绝执行: {self.serial!r}")

        if not text:
            logger.warning("写入剪贴板失败: 文本为空或 None")
            return False

        # 部分定制 ROM（MIUI/HyperOS）无 cmd clipboard 服务，set 需构造
        # ClipData Parcel 过于复杂，保持现状不支持（失败时记录警告日志）
        logger.debug("set_clipboard 使用 cmd clipboard set；该命令在无此服务的 ROM 上不支持")
        command = f"cmd clipboard set {shlex.quote(text)}"
        try:
            _, stderr = self.shell(command)
        except Exception as exc:
            logger.error("写入剪贴板命令执行异常: %s", exc)
            return False

        if stderr.strip():
            logger.warning("写入剪贴板命令返回 stderr，视为失败: %s", stderr.strip())
            return False

        logger.info("写入剪贴板完成，长度: %d", len(text))
        return True

    @staticmethod
    def _extract_bundle_value(block: str, key: str) -> str:
        """
        从通知段落文本中提取指定 Bundle key 的值（兼容多种格式）。

        dumpsys notification 输出中 extra 的展示格式不固定，常见几种：
        - key=StringValue{内容}（--noredact 时对象包裹）
        - key=String [length=N]（无 --noredact 时脱敏，仅长度无内容）
        - key=明文（直接展示，如 android.title=验证码通知）
        按优先级依次尝试，脱敏、未找到或解析失败均返回空字符串
        （容错，不抛异常）。

        参数
        ----------
        block : str
            NotificationRecord 段落文本。
        key : str
            要提取的 extra key，如 "android.title" / "android.text"。

        返回
        -------
        str
            提取到的值（已 trim）；脱敏、未找到或解析失败时返回 ""。
        """
        # 格式1: key=StringValue{...}（--noredact 常见），非贪婪匹配到首个右花括号
        match = re.search(
            rf"{re.escape(key)}=StringValue\{{(.*?)\}}", block, re.DOTALL
        )
        if match:
            return match.group(1).strip()
        # 格式2: key=String [length=N]（无 --noredact 时脱敏，仅长度无内容），置空
        match = re.search(
            rf"{re.escape(key)}=String\s*\[\s*length=\d+\s*\]", block
        )
        if match:
            return ""
        # 格式3: key=明文（取到行尾或下一个 ", key="，兼容直接明文格式）
        match = re.search(
            rf"{re.escape(key)}=([^\r\n]*?)(?:,\s*[A-Za-z_.]+=|\r?\n|$)",
            block,
        )
        if match:
            return match.group(1).strip()
        return ""

    def get_notifications(self, limit: int = 20) -> list[dict]:
        """
        读取系统通知（系统级能力）。

        通过 `dumpsys notification` 读取通知列表。部分定制 ROM 下
        --noredact 会导致输出无 NotificationRecord（仅 "Notification List:"
        头），故去掉该参数；无 --noredact 时 title/text 可能被脱敏为
        "String [length=N]"（仅长度无内容），此时置空字符串。
        解析输出中的 NotificationRecord 条目，提取每个通知的包名、标题
        与正文。无通知、命令失败或解析失败时返回空列表（容错，不抛异常）。
        返回顺序遵循 dumpsys 输出顺序（系统通常按通知时间排列）。

        参数
        ----------
        limit : int
            最多返回的条数，默认 20。

        返回
        -------
        list[dict]
            通知列表，每项形如 {"package": str, "title": str, "text": str}；
            title/text 提取失败或脱敏时为 ""。

        异常
        ------
        ValueError
            limit 非法或 serial 含注入字符时抛出。
        """
        # 1. 参数校验
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            logger.warning("无效的 limit: %r，必须为整数", limit)
            raise ValueError(f"limit 必须是整数: {limit!r}")
        if limit < 0:
            logger.warning("无效的 limit: %d，不能为负数", limit)
            raise ValueError(f"limit 不能为负数: {limit}")

        # serial 虽作为独立参数传入 subprocess 不经 shell 解析，仍统一做注入防御
        if self._SHELL_INJECTION_PATTERN.search(self.serial):
            logger.warning("serial 含可疑字符，已拒绝读取通知: %r", self.serial)
            raise ValueError(f"serial 含可疑字符，已拒绝执行: {self.serial!r}")

        # 2. 构造并执行 dumpsys notification 命令
        # 部分定制 ROM 下 --noredact 会导致无 NotificationRecord 输出，
        # 去掉该参数；title/text 可能被脱敏为 "String [length=N]"
        try:
            stdout, stderr = self.shell("dumpsys notification")
        except Exception as exc:
            logger.error("读取通知命令执行异常: %s", exc)
            return []

        # 3. 命令失败判定：输出无效或 stderr 非空均视为失败，容错返回空列表
        if not isinstance(stdout, str) or not stdout.strip():
            logger.warning("读取通知命令无有效输出，stderr: %s", stderr)
            return []
        if stderr.strip():
            logger.warning("读取通知命令返回 stderr，视为失败: %s", stderr.strip())
            return []

        # 4. 定位 NotificationRecord 段落并解析
        matches = list(self._NOTIFICATION_RECORD_PATTERN.finditer(stdout))
        notifications: list[dict] = []
        for idx, match in enumerate(matches):
            package = match.group(1)
            block_start = match.start()
            block_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(stdout)
            block = stdout[block_start:block_end]
            title = self._extract_bundle_value(block, "android.title")
            text = self._extract_bundle_value(block, "android.text")
            notifications.append({"package": package, "title": title, "text": text})

        logger.info("读取通知完成，条数: %d", len(notifications))
        return notifications[:limit]

    def get_call_state(self) -> dict:
        """
        读取设备通话状态（系统级能力）。

        通过 `dumpsys telephony.registry` 获取电话注册信息，解析通话状态
        与来电号码，用于自动化测试中来电/通话场景的检测。

        返回
        -------
        dict
            形如 {"state": str, "state_code": int, "incoming_number": str}：
            - state: idle（空闲）/ ringing（来电）/ offhook（通话中）/
              unknown（无法解析）
            - state_code: 原始数值（0/1/2，解析失败为 -1）
            - incoming_number: 来电号码；无来电、未解析到或命令失败时为 ""

        异常
        ------
        ValueError
            serial 含注入字符时抛出。
        """
        # serial 虽作为独立参数传入 subprocess 不经 shell 解析，仍统一做注入防御
        if self._SHELL_INJECTION_PATTERN.search(self.serial):
            logger.warning("serial 含可疑字符，已拒绝读取通话状态: %r", self.serial)
            raise ValueError(f"serial 含可疑字符，已拒绝执行: {self.serial!r}")

        # 1. 执行 dumpsys telephony.registry 命令
        try:
            stdout, stderr = self.shell("dumpsys telephony.registry")
        except Exception as exc:
            logger.error("读取通话状态命令执行异常: %s", exc)
            return {"state": "unknown", "state_code": -1, "incoming_number": ""}

        # 2. 命令失败判定：输出无效或 stderr 非空均视为失败，容错返回 unknown
        if not isinstance(stdout, str) or not stdout.strip():
            logger.warning("读取通话状态命令无有效输出，stderr: %s", stderr)
            return {"state": "unknown", "state_code": -1, "incoming_number": ""}
        if stderr.strip():
            logger.warning("读取通话状态命令返回 stderr，视为失败: %s", stderr.strip())
            return {"state": "unknown", "state_code": -1, "incoming_number": ""}

        # 3. 解析通话状态码（mCallState 可能出现在输出多处，取第一个有效值）
        state_match = self._CALL_STATE_PATTERN.search(stdout)
        if not state_match:
            logger.warning("通话状态输出中未找到 mCallState 字段，视为 unknown")
            return {"state": "unknown", "state_code": -1, "incoming_number": ""}
        try:
            state_code = int(state_match.group(1))
        except ValueError:
            logger.warning("通话状态码解析失败: %r", state_match.group(1))
            return {"state": "unknown", "state_code": -1, "incoming_number": ""}

        # 4. 状态码 → 人类可读名；未知数值保留原始 code，state 记 unknown
        state = self._CALL_STATE_NAMES.get(state_code, "unknown")

        # 5. 解析来电号码（无该字段或值为空时返回 ""）
        incoming_number = ""
        number_match = self._CALL_INCOMING_NUMBER_PATTERN.search(stdout)
        if number_match:
            incoming_number = number_match.group(1).strip()

        logger.info(
            "读取通话状态完成，state: %s (%d)，incoming_number: %s",
            state,
            state_code,
            incoming_number or "(无)",
        )
        return {
            "state": state,
            "state_code": state_code,
            "incoming_number": incoming_number,
        }

    def set_rotation(self, rotation: int = 0) -> None:
        """
        设置屏幕旋转方向。

        通过 ADB 修改 system user_rotation 设置项。
        修改立即生效，但部分应用可能锁定方向不响应。

        参数
        ----------
        rotation : int
            目标旋转值：
            - 0 = 竖屏（portrait）
            - 1 = 横屏（landscape）
            - 2 = 反向竖屏（reverse_portrait）
            - 3 = 反向横屏（reverse_landscape）
        """
        if rotation not in (0, 1, 2, 3):
            logger.warning("无效的旋转值: %d，使用 0（竖屏）代替", rotation)
            rotation = 0
        self.shell(f"settings put system user_rotation {rotation}")
        logger.info("屏幕旋转已设置为: %d", rotation)

    def volume_up(self) -> None:
        """
        调高媒体音量。

        通过 ADB 发送 KeyEvent 24（音量+键）。
        每次调用增加一级音量。
        """
        self.shell("input keyevent 24")
        logger.info("音量 +1")

    def volume_down(self) -> None:
        """
        调低媒体音量。

        通过 ADB 发送 KeyEvent 25（音量-键）。
        每次调用减少一级音量。
        """
        self.shell("input keyevent 25")
        logger.info("音量 -1")

    def wait_for_device(self, timeout_ms: int = 30000) -> bool:
        """
        等待设备处于可用的在线状态。

        轮询 adb get-state 命令，直到设备状态变为 "device"。

        参数
        ----------
        timeout_ms : int
            最大等待时间（毫秒），默认 30000。

        返回
        -------
        bool
            True 表示设备已在超时前就绪，False 表示超时。
        """
        deadline = time.time() + timeout_ms / 1000.0
        logger.info("等待设备就绪: %s，超时 %d ms", self.serial, timeout_ms)

        while time.time() < deadline:
            try:
                result = subprocess.run(
                    self._adb_cmd(["get-state"]),
                    capture_output=True, text=True, timeout=5,
                )
                state = result.stdout.strip()
                if state == "device":
                    logger.info("设备已就绪: %s", self.serial)
                    return True
                logger.debug("设备状态: %s", state)
            except Exception as exc:
                logger.debug("等待设备状态时出错: %s", exc)
            time.sleep(1)

        logger.warning("等待设备就绪超时: %s", self.serial)
        return False

    # ------------------------------------------------------------------
    # 基础交互命令封装（u2 会话异常时的 ADB 兜底通道）
    # 以下方法统一复用 shell() 与 _SHELL_INJECTION_PATTERN 防御：
    # 执行前校验 serial 注入、参数合法性；执行失败一律返回安全默认值，
    # 不向上抛异常（参数校验 / serial 注入除外，抛 ValueError）。
    # ------------------------------------------------------------------

    def _assert_serial_safe(self) -> None:
        """
        serial 注入防御检查。

        serial 虽作为独立参数传入 subprocess 不经 shell 解析，仍统一做
        注入防御，与既有读取类方法（短信/剪贴板/通知/通话）保持一致。

        异常
        ------
        ValueError
            serial 含注入字符时抛出。
        """
        if self._SHELL_INJECTION_PATTERN.search(self.serial):
            logger.warning("serial 含可疑字符，已拒绝执行: %r", self.serial)
            raise ValueError(f"serial 含可疑字符，已拒绝执行: {self.serial!r}")

    @staticmethod
    def _validate_coordinate(value: int, name: str) -> int:
        """
        校验屏幕坐标参数为非负整数。

        参数
        ----------
        value : int
            待校验的坐标值。
        name : str
            参数名（用于错误信息，如 "x" / "y" / "x1"）。

        返回
        -------
        int
            校验通过后的坐标值。

        异常
        ------
        ValueError
            坐标为 bool、非 int 或负数时抛出。
        """
        if isinstance(value, bool) or not isinstance(value, int):
            logger.warning("无效的 %s: %r，必须为非负整数", name, value)
            raise ValueError(f"{name} 必须是非负整数: {value!r}")
        if value < 0:
            logger.warning("无效的 %s: %d，不能为负数", name, value)
            raise ValueError(f"{name} 不能为负数: {value}")
        return value

    def _run_shell_bool(self, command: str, action: str) -> bool:
        """
        执行单条 shell 命令并返回 bool 结果。

        shell 抛异常或 stderr 非空均视为失败，返回 False（容错，不抛出）。

        参数
        ----------
        command : str
            待执行的 shell 命令。
        action : str
            操作名（用于日志前缀，如 "点击" / "滑动"）。

        返回
        -------
        bool
            True 表示执行成功（无异常且 stderr 为空）；False 表示失败。
        """
        try:
            _, stderr = self.shell(command)
        except Exception as exc:
            logger.error("%s命令执行异常: %s", action, exc)
            return False
        if stderr.strip():
            logger.warning("%s命令返回 stderr，视为失败: %s", action, stderr.strip())
            return False
        return True

    def input_tap(self, x: int, y: int) -> bool:
        """
        模拟点击屏幕坐标。

        通过 ADB input tap 在指定屏幕坐标 (x, y) 处执行点击。

        参数
        ----------
        x : int
            横坐标（非负整数，像素）。
        y : int
            纵坐标（非负整数，像素）。

        返回
        -------
        bool
            True 表示命令执行成功；False 表示失败（shell 异常或 stderr 非空）。

        异常
        ------
        ValueError
            坐标非法或 serial 含注入字符时抛出。
        """
        x = self._validate_coordinate(x, "x")
        y = self._validate_coordinate(y, "y")
        self._assert_serial_safe()
        return self._run_shell_bool(f"input tap {x} {y}", "点击")

    def input_swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration_ms: int = 300,
    ) -> bool:
        """
        模拟滑动屏幕。

        通过 ADB input swipe 从 (x1, y1) 滑动到 (x2, y2)，持续
        duration_ms 毫秒。

        参数
        ----------
        x1 : int
            起点横坐标（非负整数）。
        y1 : int
            起点纵坐标（非负整数）。
        x2 : int
            终点横坐标（非负整数）。
        y2 : int
            终点纵坐标（非负整数）。
        duration_ms : int
            滑动持续时间（毫秒），默认 300。

        返回
        -------
        bool
            True 表示命令执行成功；False 表示失败。

        异常
        ------
        ValueError
            坐标或 duration_ms 非法、serial 含注入字符时抛出。
        """
        x1 = self._validate_coordinate(x1, "x1")
        y1 = self._validate_coordinate(y1, "y1")
        x2 = self._validate_coordinate(x2, "x2")
        y2 = self._validate_coordinate(y2, "y2")
        if isinstance(duration_ms, bool) or not isinstance(duration_ms, int):
            logger.warning("无效的 duration_ms: %r，必须为整数", duration_ms)
            raise ValueError(f"duration_ms 必须是整数: {duration_ms!r}")
        if duration_ms < 0:
            logger.warning("无效的 duration_ms: %d，不能为负数", duration_ms)
            raise ValueError(f"duration_ms 不能为负数: {duration_ms}")
        self._assert_serial_safe()
        return self._run_shell_bool(
            f"input swipe {x1} {y1} {x2} {y2} {duration_ms}", "滑动"
        )

    def input_text(self, text: str) -> bool:
        """
        输入文本。

        通过 ADB input text 向当前焦点输入框输入文本。文本经
        shlex.quote 转义，保证含空格/引号等特殊字符时在设备 shell 中
        正确传参。含非 ASCII 字符（中文等）时 input text 在部分设备
        上支持不稳定，记录警告后仍尝试原样传递（不阻断）。

        参数
        ----------
        text : str
            要输入的文本内容。

        返回
        -------
        bool
            True 表示输入成功；False 表示失败（text 为空/None、
            shell 异常或 stderr 非空）。

        异常
        ------
        ValueError
            serial 含注入字符时抛出。
        """
        self._assert_serial_safe()
        if not text:
            logger.warning("输入文本失败: 文本为空或 None")
            return False

        if any(ord(ch) > 127 for ch in text):
            logger.warning(
                "input text 含非 ASCII 字符（中文等），设备支持不稳定，"
                "尝试原样传递: %r",
                text,
            )

        command = f"input text {shlex.quote(text)}"
        return self._run_shell_bool(command, "输入文本")

    def input_keyevent(self, keycode: int) -> bool:
        """
        发送按键事件。

        通过 ADB input keyevent 发送指定 keycode 的按键事件。

        参数
        ----------
        keycode : int
            Android 标准 keycode（如 4=返回、3=Home、187=最近任务）。

        返回
        -------
        bool
            True 表示命令执行成功；False 表示失败。

        异常
        ------
        ValueError
            keycode 非整数或 serial 含注入字符时抛出。
        """
        self._assert_serial_safe()
        if isinstance(keycode, bool) or not isinstance(keycode, int):
            logger.warning("无效的 keycode: %r，必须为整数", keycode)
            raise ValueError(f"keycode 必须是整数: {keycode!r}")
        return self._run_shell_bool(f"input keyevent {keycode}", "按键")

    def press_back(self) -> bool:
        """
        模拟按下返回键（KeyEvent 4）。

        返回
        -------
        bool
            True 表示命令执行成功；False 表示失败。
        """
        return self.input_keyevent(4)

    def press_home(self) -> bool:
        """
        模拟按下 Home 键（KeyEvent 3）。

        返回
        -------
        bool
            True 表示命令执行成功；False 表示失败。
        """
        return self.input_keyevent(3)

    def press_recent(self) -> bool:
        """
        模拟按下最近任务键（KeyEvent 187）。

        返回
        -------
        bool
            True 表示命令执行成功；False 表示失败。
        """
        return self.input_keyevent(187)

    def app_start(self, package: str) -> bool:
        """
        启动应用。

        优先使用 `am start` 按包名匹配 LAUNCHER 活动启动（比 -n 更通用，
        无需活动名）；失败（stderr 非空或异常）时回退到 `monkey` 启动器
        兜底。

        参数
        ----------
        package : str
            应用包名（仅允许字母数字/下划线/点，如 com.example.app）。

        返回
        -------
        bool
            True 表示任一启动方式成功；False 表示均失败。

        异常
        ------
        ValueError
            包名非法或 serial 含注入字符时抛出。
        """
        self._assert_serial_safe()
        if not isinstance(package, str) or not self._PACKAGE_PATTERN.match(package):
            logger.warning("无效的包名: %r", package)
            raise ValueError(f"无效的包名: {package!r}")

        # 主通道：am start 按包名匹配 LAUNCHER 活动
        am_command = (
            f"am start -a android.intent.action.MAIN "
            f"-c android.intent.category.LAUNCHER -p {package}"
        )
        if self._run_shell_bool(am_command, "启动应用(am start)"):
            logger.info("启动应用成功: %s", package)
            return True

        # 兜底通道：monkey 启动器
        monkey_command = (
            f"monkey -p {package} -c android.intent.category.LAUNCHER 1"
        )
        if self._run_shell_bool(monkey_command, "启动应用(monkey)"):
            logger.info("启动应用成功（monkey 兜底）: %s", package)
            return True

        logger.warning("启动应用失败: %s", package)
        return False

    def app_stop(self, package: str) -> bool:
        """
        强制停止应用。

        通过 `am force-stop` 停止指定包名的应用（含后台进程）。

        参数
        ----------
        package : str
            应用包名（仅允许字母数字/下划线/点）。

        返回
        -------
        bool
            True 表示命令执行成功；False 表示失败。

        异常
        ------
        ValueError
            包名非法或 serial 含注入字符时抛出。
        """
        self._assert_serial_safe()
        if not isinstance(package, str) or not self._PACKAGE_PATTERN.match(package):
            logger.warning("无效的包名: %r", package)
            raise ValueError(f"无效的包名: {package!r}")
        return self._run_shell_bool(f"am force-stop {package}", "停止应用")

    def list_packages(self, include_system: bool = False) -> list[str]:
        """
        列出已安装应用包名。

        通过 `pm list packages` 查询。include_system=False（默认）使用
        -3 仅列三方包；include_system=True 使用 -s 仅列系统包。
        解析输出中 "package:" 前缀，跳过无法识别的行。

        参数
        ----------
        include_system : bool
            是否仅列出系统包，默认 False（仅列三方包）。

        返回
        -------
        list[str]
            包名列表；命令失败、输出无效或 stderr 非空时返回空列表。

        异常
        ------
        ValueError
            serial 含注入字符时抛出。
        """
        self._assert_serial_safe()
        flag = "-s" if include_system else "-3"
        command = f"pm list packages {flag}"
        try:
            stdout, stderr = self.shell(command)
        except Exception as exc:
            logger.error("列出包命令执行异常: %s", exc)
            return []

        # 命令失败判定：输出无效或 stderr 非空均视为失败，容错返回空列表
        if not isinstance(stdout, str) or not stdout.strip():
            logger.warning("列出包命令无有效输出，stderr: %s", stderr)
            return []
        if stderr.strip():
            logger.warning("列出包命令返回 stderr，视为失败: %s", stderr.strip())
            return []

        packages: list[str] = []
        for line in stdout.splitlines():
            line = line.strip()
            if line.startswith("package:"):
                packages.append(line[len("package:"):].strip())
        logger.info("列出包完成，条数: %d", len(packages))
        return packages

    def get_window_focus(self) -> str:
        """
        获取当前焦点窗口。

        通过 `dumpsys window` 查询。优先解析 mFocusedApp 提取
        「包名/Activity」（如 com.miui.calculator/.cal.CalculatorActivity，
        对自动化更实用）；未找到时回退解析 mCurrentFocus 的 Window 名。
        注意：不使用 "grep" 管道形式（管道符会被 shell 注入防御拒绝），
        改为 Python 侧过滤输出，更安全。

        返回
        -------
        str
            焦点应用描述（包名/Activity）或焦点窗口描述（Window{...}）；
            未找到、焦点为 null、命令失败或异常时返回 ""。

        异常
        ------
        ValueError
            serial 含注入字符时抛出。
        """
        self._assert_serial_safe()
        try:
            stdout, stderr = self.shell("dumpsys window")
        except Exception as exc:
            logger.error("查询焦点窗口命令执行异常: %s", exc)
            return ""

        # 命令失败判定：输出无效或 stderr 非空均视为失败，容错返回空字符串
        if not isinstance(stdout, str) or not stdout.strip():
            logger.warning("查询焦点窗口无有效输出，stderr: %s", stderr)
            return ""
        if stderr.strip():
            logger.warning("查询焦点窗口返回 stderr，视为失败: %s", stderr.strip())
            return ""

        # 1. 优先解析 mFocusedApp 提取「包名/Activity」（更实用）
        focus_match = self._FOCUSED_APP_PATTERN.search(stdout)
        if focus_match:
            return focus_match.group(1).strip()

        # 2. 回退：解析 mCurrentFocus 的 Window 名
        for line in stdout.splitlines():
            line = line.strip()
            if "mCurrentFocus" not in line:
                continue
            # 形如 mCurrentFocus=Window{...} 或 mCurrentFocus=null
            focus = line.split("=", 1)[1].strip() if "=" in line else ""
            if not focus or focus == "null":
                continue
            return focus
        return ""

    def get_resolution(self) -> tuple[int, int]:
        """
        获取屏幕分辨率。

        通过 `wm size` 查询并解析 "Physical size: WxH"。

        返回
        -------
        tuple[int, int]
            (宽, 高)；命令失败或解析失败时返回 (0, 0)（容错，不抛出）。

        异常
        ------
        ValueError
            serial 含注入字符时抛出。
        """
        self._assert_serial_safe()
        try:
            stdout, stderr = self.shell("wm size")
        except Exception as exc:
            logger.error("查询分辨率命令执行异常: %s", exc)
            return (0, 0)

        # 命令失败判定：输出无效或 stderr 非空均视为失败，容错返回 (0, 0)
        if not isinstance(stdout, str) or not stdout.strip():
            logger.warning("查询分辨率无有效输出，stderr: %s", stderr)
            return (0, 0)
        if stderr.strip():
            logger.warning("查询分辨率返回 stderr，视为失败: %s", stderr.strip())
            return (0, 0)

        match = self._PHYSICAL_SIZE_PATTERN.search(stdout)
        if not match:
            logger.warning("分辨率输出中未找到 Physical size 字段，返回 (0, 0)")
            return (0, 0)
        return int(match.group(1)), int(match.group(2))
