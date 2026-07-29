"""配置管理模块测试。

测试 pydantic-settings 配置的正确加载、环境变量覆盖
和 get_llm_config 辅助函数的输出。

涵盖：
- Settings 全局配置的默认值和嵌套访问
- ModelSettings/ProviderConfig/ModelEntry 新增配置类
- 模型注册表查询方法的正确性
"""

import pytest
from pydantic import ValidationError

from mobile_automation.config import (
    ModelEntry,
    ModelSettings,
    ProviderConfig,
    Settings,
    get_llm_config,
    settings,
)


class TestProviderConfig:
    """测试 ProviderConfig 数据类。"""

    def test_default_values(self):
        """验证默认值。"""
        cfg = ProviderConfig()
        assert cfg.api_key == ""
        assert cfg.base_url == ""
        assert cfg.timeout == 60

    def test_custom_values(self):
        """验证自定义值。"""
        cfg = ProviderConfig(api_key="sk-test", base_url="https://test.com/v1", timeout=30)
        assert cfg.api_key == "sk-test"
        assert cfg.base_url == "https://test.com/v1"
        assert cfg.timeout == 30


class TestModelEntry:
    """测试 ModelEntry 数据类及能力属性。"""

    def test_default_values(self):
        """验证默认值。"""
        entry = ModelEntry()
        assert entry.provider == ""
        assert entry.model_name == ""
        assert entry.model_type == "multimodal"
        assert entry.context_window == 32000
        assert entry.max_tokens == 4096
        assert entry.temperature == 0.1

    def test_is_multimodal_true(self):
        """验证 model_type=multimodal 时 is_multimodal 返回 True。"""
        entry = ModelEntry(model_type="multimodal")
        assert entry.is_multimodal is True
        assert entry.is_text_only is False

    def test_is_text_only_true(self):
        """验证 model_type=text 时 is_text_only 返回 True。"""
        entry = ModelEntry(model_type="text")
        assert entry.is_text_only is True
        assert entry.is_multimodal is False

    def test_custom_model_entry(self):
        """验证完整的 ModelEntry 自定义。"""
        entry = ModelEntry(
            provider="qwen",
            model_name="qwen3.6-flash",
            model_type="multimodal",
            context_window=64000,
            max_tokens=8192,
            temperature=0.2,
        )
        assert entry.provider == "qwen"
        assert entry.model_name == "qwen3.6-flash"
        assert entry.context_window == 64000
        assert entry.max_tokens == 8192
        assert entry.temperature == 0.2
        assert entry.is_multimodal is True


class TestModelSettings:
    """测试 ModelSettings 多模型配置管理。"""

    def test_default_providers_count(self):
        """验证默认供应商数量（qwen/zhipu/deepseek/longcat/mimo/local）。"""
        ms = ModelSettings()
        assert len(ms.providers) == 6
        assert "qwen" in ms.providers
        assert "zhipu" in ms.providers
        assert "deepseek" in ms.providers
        assert "longcat" in ms.providers
        assert "mimo" in ms.providers
        assert "local" in ms.providers

    def test_default_models_count(self):
        """验证默认模型注册表数量（9 个模型条目）。"""
        ms = ModelSettings()
        assert len(ms.models) == 9
        assert "mimo-omni" in ms.models
        assert "mimo-pro" in ms.models
        assert "local-model" in ms.models
        assert "qwen-flash" in ms.models
        assert "qwen-plus" in ms.models
        assert "zhipu-flash" in ms.models
        assert "zhipu-flashx" in ms.models
        assert "deepseek-flash" in ms.models
        assert "longcat-flash" in ms.models

    def test_default_multimodal_and_text(self):
        """验证默认多模态/纯文本模型 key 正确。"""
        ms = ModelSettings()
        assert ms.default_multimodal == "mimo-omni"
        assert ms.default_text == "deepseek-flash"

    def test_get_model_found(self):
        """验证 get_model 返回存在的模型。"""
        ms = ModelSettings()
        entry = ms.get_model("qwen-flash")
        assert entry is not None
        assert entry.model_name == "qwen3.6-flash"
        assert entry.is_multimodal is True

    def test_get_model_not_found(self):
        """验证 get_model 返回 None 当模型不存在。"""
        ms = ModelSettings()
        assert ms.get_model("nonexistent-model") is None

    def test_get_provider_config_found(self):
        """验证 get_provider_config 返回存在供应商的配置。"""
        ms = ModelSettings()
        cfg = ms.get_provider_config("qwen")
        assert cfg is not None
        assert cfg.base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"

    def test_get_provider_config_not_found(self):
        """验证 get_provider_config 返回 None 当供应商不存在。"""
        ms = ModelSettings()
        assert ms.get_provider_config("unknown-provider") is None

    def test_resolve_api_key_from_provider(self):
        """验证 resolve_api_key 从供应商配置读取 API Key。"""
        ms = ModelSettings()
        ms.providers["qwen"].api_key = "sk-qwen-test"
        assert ms.resolve_api_key("qwen-flash") == "sk-qwen-test"

    def test_resolve_api_key_empty_when_not_configured(self):
        """验证 resolve_api_key 返回空字符串当 API Key 未配置。"""
        ms = ModelSettings()
        assert ms.resolve_api_key("qwen-flash") == ""

    def test_resolve_api_key_empty_for_nonexistent_model(self):
        """验证 resolve_api_key 返回空字符串当模型不存在。"""
        ms = ModelSettings()
        assert ms.resolve_api_key("nonexistent") == ""

    def test_list_multimodal_models(self):
        """验证 list_multimodal_models 仅返回多模态模型。"""
        ms = ModelSettings()
        multimodal = ms.list_multimodal_models()
        assert "qwen-flash" in multimodal
        assert "qwen-plus" in multimodal
        assert "zhipu-flash" in multimodal
        assert "zhipu-flashx" in multimodal
        assert "deepseek-flash" not in multimodal
        assert "longcat-flash" not in multimodal

    def test_list_text_models(self):
        """验证 list_text_models 仅返回纯文本模型。"""
        ms = ModelSettings()
        text_only = ms.list_text_models()
        assert "deepseek-flash" in text_only
        assert "longcat-flash" in text_only
        assert "qwen-flash" not in text_only
        assert "zhipu-flash" not in text_only


class TestSettings:
    """测试 Settings 全局配置对象的默认值和嵌套访问。"""

    def test_default_llm_provider(self):
        """验证 LLM 默认提供商从 .env 读取。"""
        s = Settings()
        assert s.llm.provider == "qwen"

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
