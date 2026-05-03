from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib import request

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


@dataclass(frozen=True)
class ModelRole:
    role: str
    provider: str
    model: str
    fallback: str = "heuristic"


class ModelRegistry:
    """Small v0.1 model router. xAI first, LM Studio/Ollama/heuristic fallback."""

    def __init__(self) -> None:
        provider = os.getenv("OMNIBOT_PROVIDER", "xai").lower()
        self.xai_base_url = os.getenv("XAI_BASE_URL", "https://api.x.ai/v1")
        self.lmstudio_base_url = os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
        self.lmstudio_model = os.getenv("OMNIBOT_LMSTUDIO_MODEL", "local-model")
        self.lmstudio_api_key = os.getenv("LMSTUDIO_API_KEY", "")
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.ollama_model = os.getenv("OMNIBOT_OLLAMA_MODEL", "llama3.2")

        default = os.getenv("OMNIBOT_MODEL", "grok-4.3" if provider == "xai" else self.lmstudio_model)
        self.roles = {
            "reflex": ModelRole("reflex", provider, default, fallback="lmstudio"),
            "researcher": ModelRole("researcher", provider, default, fallback="lmstudio"),
            "coder": ModelRole("coder", provider, default, fallback="lmstudio"),
            "arbiter": ModelRole("arbiter", provider, default, fallback="lmstudio"),
        }

    async def complete(self, role: str, prompt: str) -> str:
        spec = self.roles.get(role, self.roles["reflex"])
        if spec.provider == "xai":
            try:
                return self._xai_complete(spec.model, prompt)
            except Exception:
                return self._local_fallback(role, prompt)
        if spec.provider == "lmstudio":
            try:
                return self._lmstudio_complete(spec.model, prompt)
            except Exception:
                return self._ollama_or_heuristic(role, prompt)
        if spec.provider == "ollama":
            return self._ollama_or_heuristic(role, prompt, model=spec.model)
        return self._heuristic_complete(role, prompt)

    def _xai_complete(self, model: str, prompt: str) -> str:
        api_key = os.getenv("XAI_API_KEY")
        if not api_key:
            raise RuntimeError("XAI_API_KEY is not set")
        return self._chat_completions_complete(
            base_url=self.xai_base_url,
            model=model,
            prompt=prompt,
            api_key=api_key,
            timeout=45,
        )

    def _lmstudio_complete(self, model: str, prompt: str) -> str:
        return self._chat_completions_complete(
            base_url=self.lmstudio_base_url,
            model=model,
            prompt=prompt,
            api_key=self.lmstudio_api_key,
            timeout=45,
        )

    def _chat_completions_complete(
        self,
        *,
        base_url: str,
        model: str,
        prompt: str,
        api_key: str = "",
        timeout: int = 45,
    ) -> str:
        data = json.dumps(
            {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are an OmniBot worker. Be concise, source-grounded, "
                            "and explicit about uncertainty."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        req = request.Request(
            f"{base_url.rstrip('/')}/chat/completions",
            data=data,
            headers=headers,
            method="POST",
        )
        with request.urlopen(req, timeout=timeout) as response:
            payload: dict[str, Any] = json.loads(response.read().decode("utf-8"))
        return str(payload["choices"][0]["message"]["content"]).strip()

    def _ollama_complete(self, model: str, prompt: str) -> str:
        data = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8")
        req = request.Request(
            f"{self.ollama_base_url.rstrip('/')}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=20) as response:
            payload: dict[str, Any] = json.loads(response.read().decode("utf-8"))
        return str(payload.get("response", "")).strip()

    def _local_fallback(self, role: str, prompt: str) -> str:
        try:
            return self._lmstudio_complete(self.lmstudio_model, prompt)
        except Exception:
            return self._ollama_or_heuristic(role, prompt)

    def _ollama_or_heuristic(self, role: str, prompt: str, model: str | None = None) -> str:
        try:
            return self._ollama_complete(model or self.ollama_model, prompt)
        except Exception:
            return self._heuristic_complete(role, prompt)

    def _heuristic_complete(self, role: str, prompt: str) -> str:
        return (
            f"[{role} fallback]\n"
            "No xAI or local model response was available, so OmniBot used deterministic v0.1 logic. "
            "Set XAI_API_KEY for grok-4.3, run LM Studio, or run Ollama for local fallback."
        )
