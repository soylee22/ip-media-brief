"""Gemini provider (SPEC 11.5). Never log the key, the headers or the request body."""
from __future__ import annotations

import os
import time

import httpx


class Gemini:
    name = "gemini"

    def __init__(self, cfg: dict, budget: dict, client: httpx.Client | None = None, sleep=time.sleep):
        self.cfg = cfg
        self.budget = budget
        self.key = os.environ.get("GEMINI_API_KEY", "").strip()
        self.client = client or httpx.Client(timeout=60)
        self.sleep = sleep
        self.run_calls = 0
        self.last_call = 0.0
        self.models = [budget.get("gemini_model_in_use") or cfg["model"]] + [
            m for m in cfg.get("fallback_models", []) if m != (budget.get("gemini_model_in_use") or cfg["model"])]
        self.model = self.models[0]
        self.errors = 0

    def model_in_use(self) -> str:
        return self.model

    def ready(self) -> str:
        if not self.key:
            return "no_key"
        if self.budget.get("gemini_state") in ("exhausted", "rejected"):
            return self.budget["gemini_state"]
        return "ok"

    def _body(self, system: str, user: str) -> dict:
        gen = {
            "temperature": self.cfg.get("temperature", 0.2),
            "maxOutputTokens": self.cfg.get("max_output_tokens", 400),
            "responseMimeType": "application/json",
            "responseSchema": {"type": "OBJECT", "properties": {"summary": {"type": "STRING"}}, "required": ["summary"]},
        }
        if self.cfg.get("thinking_config") and not self.budget.get("omit_thinking_config"):
            gen["thinkingConfig"] = self.cfg["thinking_config"]
        return {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": gen,
        }

    def _post(self, system: str, user: str) -> httpx.Response | None:
        gap = time.monotonic() - self.last_call
        if self.last_call and gap < self.cfg["min_seconds_between_calls"]:
            self.sleep(self.cfg["min_seconds_between_calls"] - gap)
        self.run_calls += 1
        self.budget["gemini_calls"] = self.budget.get("gemini_calls", 0) + 1
        self.last_call = time.monotonic()
        try:
            return self.client.post(self.cfg["endpoint"].format(model=self.model),
                                    headers={"x-goog-api-key": self.key, "Content-Type": "application/json"},
                                    json=self._body(system, user))
        except httpx.HTTPError:
            return None

    def summarise(self, system: str, user: str) -> tuple[str | None, str]:
        rate_retry = thinking_retry = False
        while True:
            if self.run_calls >= self.cfg["per_run_cap"]:
                return None, "cap"
            if self.budget.get("gemini_calls", 0) >= self.cfg["daily_call_cap"]:
                return None, "exhausted"
            resp = self._post(system, user)
            if resp is None:
                self.errors += 1
                return None, "error" if self.errors >= 3 else "ok_skip"
            code = resp.status_code
            if code == 200:
                self.errors = 0
                try:
                    return resp.json()["candidates"][0]["content"]["parts"][0]["text"], "ok"
                except (KeyError, IndexError, ValueError):
                    return None, "ok"
            body = resp.text
            if code == 429:
                if "PerDay" in body or "per day" in body.lower():
                    self.budget["gemini_state"] = "exhausted"
                    return None, "exhausted"
                if rate_retry:
                    return None, "cap"
                rate_retry = True
                self.sleep(60)
                continue
            if code == 400 and "thinking" in body.lower() and not thinking_retry:
                thinking_retry = True
                self.budget["omit_thinking_config"] = True
                continue
            if code == 404 and len(self.models) > 1:
                self.models.pop(0)
                self.model = self.models[0]
                self.budget["gemini_model_in_use"] = self.model
                continue
            if code in (401, 403):
                self.budget["gemini_state"] = "rejected"
                return None, "rejected"
            self.errors += 1
            return None, "error" if self.errors >= 3 else "ok_skip"
