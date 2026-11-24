"""Local model fallback through Ollama (SPEC 11.6)."""
from __future__ import annotations

import os

import httpx

URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")


class Ollama:
    name = "ollama"

    def __init__(self, cfg: dict, budget: dict, client: httpx.Client | None = None):
        self.cfg = cfg
        self.budget = budget
        self.model = os.environ.get("OLLAMA_MODEL_OVERRIDE") or cfg["model"]
        self.client = client or httpx.Client(timeout=cfg.get("per_item_timeout_seconds", 120))

    def model_in_use(self) -> str:
        return self.model

    def ready(self) -> str:
        try:
            r = self.client.get(f"{URL}/api/version", timeout=10)
            return "ok" if r.status_code == 200 else "error"
        except httpx.HTTPError:
            return "error"

    def summarise(self, system: str, user: str) -> tuple[str | None, str]:
        body = {
            "model": self.model,
            "stream": False,
            "think": False,
            "format": {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]},
            "options": {"temperature": self.cfg.get("temperature", 0.2), "num_ctx": self.cfg.get("num_ctx", 4096),
                        "num_predict": 300},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        self.budget["ollama_calls"] = self.budget.get("ollama_calls", 0) + 1
        try:
            r = self.client.post(f"{URL}/api/chat", json=body,
                                 timeout=self.cfg.get("per_item_timeout_seconds", 120))
        except httpx.TimeoutException:
            return None, "ok_skip"
        except httpx.HTTPError:
            return None, "error"
        if r.status_code != 200:
            return None, "error"
        try:
            return r.json()["message"]["content"], "ok"
        except (KeyError, ValueError):
            return None, "ok"
