"""
集中式日志管理模块。

提供统一的日志配置入口，支持按文件大小轮转、日志保留期限、
控制台与文件双输出通道。所有模块通过 get_logger() 获取日志器，
确保日志格式和输出行为一致。

日志文件默认存储在 logs/yy_mm_dd_hh_mm_ss/ 时间戳子目录下。
"""

import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


def _timestamp_dir(base: str) -> Path:
    """
    在基础路径下添加当前时间戳子目录。

    格式：yy_mm_dd_hh_mm_ss
    例如：logs/ -> logs/26_06_26_23_30_00/

    参数
    ----------
    base : str
        基础目录路径。

    返回
    -------
    Path
        添加时间戳后的完整目录路径。
    """
    ts = datetime.now().strftime("%y_%m_%d_%H_%M_%S")
    return Path(base) / ts


_LOG_INITIALIZED: bool = False
"""全局标志位，防止重复初始化"""


def setup_logger(
    log_dir: str = "logs",
    log_level: str = "DEBUG",
    rotation_mb: int = 10,
    retention_days: int = 7,
) -> logging.Logger:
    """
    配置并返回全局根日志器。

    日志文件会写入 log_dir/yy_mm_dd_hh_mm_ss/mobile_automation.log，
    每次启动创建一个新的时间戳子目录。

    参数
    ----------
    log_dir : str
        日志文件输出根目录，默认为 "logs"。
    log_level : str
        日志级别名，如 "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"。
    rotation_mb : int
        单个日志文件大小上限（MB），达到上限后自动轮转。
    retention_days : int
        日志文件保留天数，超过期限的旧日志自动清理。

    返回
    -------
    logging.Logger
        配置完成的根日志器实例。

    异常
    ------
    OSError
        日志目录创建失败或无写入权限时抛出。
    """
    global _LOG_INITIALIZED

    root_logger = logging.getLogger("mobile_automation")

    if _LOG_INITIALIZED:
        return root_logger

    # 使用时间戳子目录
    log_path = _timestamp_dir(log_dir)
    try:
        log_path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OSError(f"无法创建日志目录 '{log_path}': {exc}") from exc

    log_file = log_path / "mobile_automation.log"
    level = getattr(logging, log_level.upper(), logging.DEBUG)

    # ---------- 文件处理器（按大小轮转） ----------
    file_handler = RotatingFileHandler(
        filename=str(log_file),
        maxBytes=rotation_mb * 1024 * 1024,
        backupCount=retention_days,
        encoding="utf-8",
    )
    file_handler.setLevel(level)

    # ---------- 控制台处理器 ----------
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    # ---------- 格式化器 ----------
    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(filename)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(fmt)
    console_handler.setFormatter(fmt)

    # ---------- 移除已有处理器避免重复 ----------
    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    root_logger.setLevel(level)
    root_logger.propagate = False

    _LOG_INITIALIZED = True
    root_logger.debug("日志系统初始化完成，级别=%s，文件=%s", log_level, log_file)

    return root_logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    获取 mobile_automation 体系内的子日志器。

    使用方式
    --------
    >>> from src.mobile_automation.logger import get_logger
    >>> logger = get_logger(__name__)
    >>> logger.info("这是一条日志")

    参数
    ----------
    name : Optional[str]
        日志器名称，通常传入 __name__。为 None 时返回根日志器。

    返回
    -------
    logging.Logger
        子日志器实例，继承根日志器的处理器和格式。
    """
    if name:
        return logging.getLogger(f"mobile_automation.{name}")
    return logging.getLogger("mobile_automation")
