"""Model adapters. MockModel runs fully offline; OpenAICompatibleModel speaks /chat/completions."""

from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass
from typing import Protocol


class Model(Protocol):
    name: str

    def complete(self, messages: list[dict[str, str]], **params) -> str: ...


@dataclass
class MockModel:
    """Deterministic, heuristic 'model' for offline development and CI.

    It reads simple instructions from the prompt so pipelines behave realistically:
      * "JSON ... keys: a, b, c"   -> returns a JSON object with those keys
      * "in N words" / "under N words" -> trims prose to N words
      * "N bullet(s)"              -> returns N bullet points
    Otherwise it produces a short extractive summary of the user message.
    """

    name: str = "mock"

    def complete(self, messages: list[dict[str, str]], **params) -> str:
        prompt = "\n".join(m["content"] for m in messages)
        user = messages[-1]["content"]
        source = self._source_text(user)
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", source) if s.strip()]

        keys = re.search(r"keys?\s*:\s*([a-zA-Z0-9_,\s]+)", prompt, re.I)
        if "json" in prompt.lower() and keys:
            names = [k.strip() for k in keys.group(1).split(",") if k.strip()]
            names = [n.split()[0] for n in names]
            obj = {k: (sentences[i % len(sentences)] if sentences else k) for i, k in enumerate(names)}
            return json.dumps(obj, ensure_ascii=False)

        bullets = re.search(r"(\d+)\s+bullet", prompt, re.I)
        if bullets:
            n = int(bullets.group(1))
            pool = sentences or [source]
            return "\n".join(f"- {pool[i % len(pool)].rstrip('.')}" for i in range(n))

        text = " ".join(sentences[:2]) if sentences else source
        limit = re.search(r"(?:in|under|max(?:imum)?(?: of)?)\s+(\d+)\s+words", prompt, re.I)
        if limit:
            words = text.split()
            if len(words) > int(limit.group(1)):
                text = " ".join(words[: int(limit.group(1))]).rstrip(",;:.") + "."
        return text

    @staticmethod
    def _source_text(user: str) -> str:
        # Prefer content inside a fenced/quoted block: """...""" or <text>...</text>
        for pat in (r'"""(.*?)"""', r"<text>(.*?)</text>", r"```(.*?)```"):
            m = re.search(pat, user, re.S)
            if m:
                return " ".join(m.group(1).split())
        return " ".join(user.split())


@dataclass
class OpenAICompatibleModel:
    """Minimal client for any OpenAI-compatible /chat/completions endpoint (stdlib only)."""

    model: str
    api_key: str
    base_url: str = "https://api.openai.com/v1"
    timeout: float = 60.0

    @property
    def name(self) -> str:
        return self.model

    @classmethod
    def from_env(cls) -> "OpenAICompatibleModel":
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("Set OPENAI_API_KEY (and optionally OPENAI_BASE_URL, PROMPTFORGE_MODEL).")
        return cls(
            model=os.environ.get("PROMPTFORGE_MODEL", "gpt-4o-mini"),
            api_key=key,
            base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        )

    def complete(self, messages: list[dict[str, str]], **params) -> str:
        body = {"model": self.model, "messages": messages}
        body.update({k: v for k, v in params.items() if k in {"temperature", "max_tokens", "top_p"}})
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"]


def get_model(name: str = "mock") -> Model:
    if name == "mock":
        return MockModel()
    if name in {"openai", "api"}:
        return OpenAICompatibleModel.from_env()
    raise ValueError(f"Unknown model '{name}'. Use 'mock' or 'openai'.")
