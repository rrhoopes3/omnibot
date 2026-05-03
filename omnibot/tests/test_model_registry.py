from __future__ import annotations

from omnibot.models.registry import ModelRegistry


def test_model_registry_defaults_to_xai_grok_43(monkeypatch):
    monkeypatch.delenv("OMNIBOT_PROVIDER", raising=False)
    monkeypatch.delenv("OMNIBOT_MODEL", raising=False)

    registry = ModelRegistry()

    assert registry.roles["arbiter"].provider == "xai"
    assert registry.roles["arbiter"].model == "grok-4.3"


def test_model_registry_can_run_lmstudio_first(monkeypatch):
    monkeypatch.setenv("OMNIBOT_PROVIDER", "lmstudio")
    monkeypatch.delenv("OMNIBOT_MODEL", raising=False)
    monkeypatch.setenv("OMNIBOT_LMSTUDIO_MODEL", "qwen2.5-7b-instruct")

    registry = ModelRegistry()

    assert registry.roles["arbiter"].provider == "lmstudio"
    assert registry.roles["arbiter"].model == "qwen2.5-7b-instruct"
    assert registry.lmstudio_base_url == "http://localhost:1234/v1"
