from __future__ import annotations

from omnibot.models.registry import ModelRegistry


def test_model_registry_defaults_to_xai_grok_43(monkeypatch):
    monkeypatch.delenv("OMNIBOT_PROVIDER", raising=False)
    monkeypatch.delenv("OMNIBOT_MODEL", raising=False)

    registry = ModelRegistry()

    assert registry.roles["arbiter"].provider == "xai"
    assert registry.roles["arbiter"].model == "grok-4.3"
