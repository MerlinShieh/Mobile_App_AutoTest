"""配置管理模块测试。

测试 pydantic-settings 配置的正确加载、环境变量覆盖
和 get_llm_config 辅助函数的输出。
"""

import pytest
from pydantic import ValidationError

from mobile_automation.config import Settings, get_llm_config, settings


class TestSettings:
    """测试 Settings 全局配置对象的默认值和嵌套访问。"""

    def test_default_llm_provider(self):
        """验证 LLM 默认提供商从 .env 读取。"""
        s = Settings()
        assert s.llm.provider == "zhipu"

    def test_default_device_settings(self):
        """验证设备配置的默认值正确。"""
        s = Settings()
        assert s.device.adb_path == "adb"
        assert s.device.connect_retries == 3
        assert s.device.serial == ""

    def test_default_execution_settings(self):
        """验证执行配置的默认值正确。"""
        s = Settings()
        assert s.execution.max_steps_per_task == 30
        assert s.execution.max_retries_per_step == 3
        assert s.execution.screenshot_max_size == 720
        assert s.execution.screenshot_quality == 85

    def test_default_popup_settings(self):
        """验证弹窗配置默认启用。"""
        s = Settings()
        assert s.popup.enabled is True
        assert s.popup.permission_auto_allow is True

    def test_nested_access(self):
        """验证嵌套配置的链式访问。"""
        s = Settings()
        assert s.llm.max_tokens == 4096
        assert s.llm.temperature == 0.1
        assert s.loop_detection.max_same_actions == 3
        assert s.coordinate_tuning.enable_tuning is False

    def test_env_override(self, monkeypatch):
        """测试环境变量通过 __ 分隔符覆盖嵌套配置。"""
        monkeypatch.setenv("LLM__PROVIDER", "openai")
        monkeypatch.setenv("LLM__API_KEY", "sk-test-key")
        monkeypatch.setenv("EXECUTION__MAX_STEPS_PER_TASK", "50")
        monkeypatch.setenv("POPUP__ENABLED", "false")

        s = Settings()
        assert s.llm.provider == "openai"
        assert s.llm.api_key == "sk-test-key"
        assert s.execution.max_steps_per_task == 50
        assert s.popup.enabled is False

    def test_env_override_with_invalid_value_raises(self, monkeypatch):
        """测试环境变量设置无效值时 pydantic 抛出 ValidationError。"""
        monkeypatch.setenv("EXECUTION__SCREENSHOT_QUALITY", "invalid")
        with pytest.raises(ValidationError):
            Settings()

    def test_get_llm_config(self, mocker):
        """测试 get_llm_config 返回正确的配置字典。"""
        mocker.patch.object(settings.llm, "api_key", "sk-test")
        mocker.patch.object(settings.llm, "model_name", "gpt-4o")
        mocker.patch.object(settings.llm, "max_tokens", 2048)
        mocker.patch.object(settings.llm, "temperature", 0.5)

        config = get_llm_config()
        assert config["api_key"] == "sk-test"
        assert config["model"] == "gpt-4o"
        assert config["max_tokens"] == 2048
        assert config["temperature"] == 0.5
        assert "base_url" in config
        assert "top_p" in config
        assert "timeout" in config

    def test_settings_extra_ignore(self, monkeypatch):
        """测试未定义的配置项被忽略（extra='ignore'）。"""
        monkeypatch.setenv("UNKNOWN_FIELD", "value")
        s = Settings()
        assert not hasattr(s, "unknown_field")
