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

    # content query 行解析：
    # - address 非贪婪，遇到首个 ", body=" 即停止
    # - body 贪婪，可包含逗号/等号，直到行内最后一个 ", date="
    # - date 为毫秒时间戳数字
    _SMS_ROW_PATTERN = re.compile(
        r"^Row:\s*\d+\s+address=(.*?),\s+body=(.*),\s+date=(\d+)\s*$"
    )

    # dumpsys notification 输出中 NotificationRecord 段落定位：
    # 形如 NotificationRecord(0x0197e345 pkg=com.android.mms user=... )，
    # 捕获 pkg 之后的包名（到空白或右括号为止）。
    _NOTIFICATION_RECORD_PATTERN = re.compile(
        r"NotificationRecord\(\s*0x[0-9a-fA-F]+\s+pkg=([^\s\)]+)"
    )

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
        # --sort-order 的值含空格，用双引号包裹以保证设备 shell 正确传参
        command = (
            f"content query --uri content://sms/{sms_type} "
            "--projection address,body,date "
            '--sort-order "date DESC" '
            f"--limit {limit}"
        )
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
        messages: list[dict] = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line or not line.startswith("Row:"):
                continue
            match = self._SMS_ROW_PATTERN.match(line)
            if not match:
                logger.warning("短信行解析失败，跳过: %s", line)
                continue
            address = match.group(1).strip()
            body = match.group(2).strip()
            try:
                date = int(match.group(3))
            except ValueError:
                logger.warning("短信日期解析失败，跳过: %s", match.group(3))
                continue
            messages.append({"address": address, "body": body, "date": date})

        logger.info("读取短信完成，类型: %s，条数: %d", sms_type, len(messages))
        return messages

    def get_clipboard(self) -> str:
        """
        读取系统剪贴板文本（系统级能力，Android 10+）。

        通过 `cmd clipboard get` 读取剪贴板内容。命令失败、无权限、
        无内容或 shell 异常时返回空字符串（容错，不抛异常）。

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
        logger.info("读取剪贴板完成，长度: %d", len(text))
        return text

    def set_clipboard(self, text: str) -> bool:
        """
        写入系统剪贴板文本（系统级能力，Android 10+）。

        通过 `cmd clipboard set` 写入剪贴板。文本经 shlex.quote 转义，
        保证含空格/引号等特殊字符时在设备 shell 中正确传参。

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

        dumpsys notification --noredact 输出中 extra 的展示格式不固定，
        常见两种：
        - key=StringValue{内容}（对象包裹）
        - key=内容（直接明文，如 android.title=验证码通知）
        按优先级依次尝试，均失败返回空字符串（容错，不抛异常）。

        参数
        ----------
        block : str
            NotificationRecord 段落文本。
        key : str
            要提取的 extra key，如 "android.title" / "android.text"。

        返回
        -------
        str
            提取到的值（已 trim）；未找到时返回 ""。
        """
        # 格式1: key=StringValue{...}，非贪婪匹配到首个右花括号
        match = re.search(
            rf"{re.escape(key)}=StringValue\{{(.*?)\}}", block, re.DOTALL
        )
        if match:
            return match.group(1).strip()
        # 格式2: key=值（取到行尾）
        match = re.search(rf"{re.escape(key)}=([^\r\n]+)", block)
        if match:
            return match.group(1).strip()
        return ""

    def get_notifications(self, limit: int = 20) -> list[dict]:
        """
        读取系统通知（系统级能力）。

        通过 `dumpsys notification --noredact` 读取通知列表（--noredact
        显示完整文本）。解析输出中的 NotificationRecord 条目，提取每个
        通知的包名、标题与正文。无通知、命令失败或解析失败时返回空列表
        （容错，不抛异常）。返回顺序遵循 dumpsys 输出顺序（系统通常
        按通知时间排列）。

        参数
        ----------
        limit : int
            最多返回的条数，默认 20。

        返回
        -------
        list[dict]
            通知列表，每项形如 {"package": str, "title": str, "text": str}；
            title/text 提取失败时为 ""。

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
        try:
            stdout, stderr = self.shell("dumpsys notification --noredact")
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
