from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib import request


@dataclass(frozen=True)
class ModelRole:
    role: str
    provider: str
    model: str
    fallback: str = "heuristic"


class ModelRegistry:
    """Small v0.1 model router. Ollama first, deterministic fallback."""

    def __init__(self) -> None:
        default = os.getenv("OMNIBOT_MODEL", "llama3.2")
        self.roles = {
            "reflex": ModelRole("reflex", "ollama", default),
            "researcher": ModelRole("researcher", "ollama", default),
            "coder": ModelRole("coder", "ollama", default),
            "arbiter": ModelRole("arbiter", "ollama", default),
        }
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    async def complete(self, role: str, prompt: str) -> str:
        spec = self.roles.get(role, self.roles["reflex"])
        if spec.provider == "ollama":
            try:
                return self._ollama_complete(spec.model, prompt)
            except Exception:
                return self._heuristic_complete(role, prompt)
        return self._heuristic_complete(role, prompt)

    def _ollama_complete(self, model: str, prompt: str) -> str:
        data = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=20) as response:
            payload: dict[str, Any] = json.loads(response.read().decode("utf-8"))
        return str(payload.get("response", "")).strip()

    def _heuristic_complete(self, role: str, prompt: str) -> str:
        return (
            f"[{role} fallback]\n"
            "No local model response was available, so OmniBot used deterministic v0.1 logic. "
            "Install/run Ollama for richer synthesis."
        )
