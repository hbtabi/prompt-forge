"""Prompt templates with typed-ish variables, defaults and a stable fingerprint."""

from __future__ import annotations

import hashlib
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# {{ name }} or {{ name | default text }}
_VAR = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:\|\s*([^}]*?))?\s*\}\}")


class MissingVariableError(KeyError):
    """Raised when a template is rendered without a required variable."""

    def __init__(self, template: str, missing: list[str]):
        self.missing = missing
        super().__init__(f"Template '{template}' is missing variables: {', '.join(missing)}")


@dataclass
class PromptTemplate:
    name: str
    version: int
    template: str
    system: str = ""
    description: str = ""
    defaults: dict[str, str] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------ io
    @classmethod
    def from_toml(cls, path: str | Path) -> "PromptTemplate":
        path = Path(path)
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        meta = data.get("meta", {})
        version = meta.get("version")
        if version is None:
            m = re.fullmatch(r"v(\d+)", path.stem)
            version = int(m.group(1)) if m else 1
        return cls(
            name=meta.get("name", path.parent.name),
            version=int(version),
            description=meta.get("description", ""),
            tags=list(meta.get("tags", [])),
            system=data.get("prompt", {}).get("system", "").strip(),
            template=data["prompt"]["template"].strip(),
            defaults={k: str(v) for k, v in data.get("defaults", {}).items()},
            params=dict(data.get("params", {})),
        )

    # ------------------------------------------------------------ helpers
    @property
    def ref(self) -> str:
        return f"{self.name}@v{self.version}"

    @property
    def variables(self) -> list[str]:
        seen: list[str] = []
        for text in (self.system, self.template):
            for m in _VAR.finditer(text):
                if m.group(1) not in seen:
                    seen.append(m.group(1))
        return seen

    @property
    def required(self) -> list[str]:
        inline = {m.group(1) for t in (self.system, self.template) for m in _VAR.finditer(t) if m.group(2)}
        return [v for v in self.variables if v not in self.defaults and v not in inline]

    @property
    def fingerprint(self) -> str:
        """Short content hash so you can tell if a 'version' was silently edited."""
        h = hashlib.sha256()
        for part in (self.system, self.template, repr(sorted(self.defaults.items())), repr(sorted(self.params.items()))):
            h.update(part.encode("utf-8"))
            h.update(b"\x00")
        return h.hexdigest()[:12]

    # ------------------------------------------------------------- render
    def _render_text(self, text: str, values: dict[str, Any]) -> str:
        def sub(m: re.Match[str]) -> str:
            key, inline_default = m.group(1), m.group(2)
            if key in values:
                return str(values[key])
            if key in self.defaults:
                return self.defaults[key]
            if inline_default is not None:
                return inline_default.strip()
            raise MissingVariableError(self.ref, [key])

        return _VAR.sub(sub, text)

    def render(self, **values: Any) -> str:
        missing = [v for v in self.required if v not in values]
        if missing:
            raise MissingVariableError(self.ref, missing)
        return self._render_text(self.template, values)

    def render_messages(self, **values: Any) -> list[dict[str, str]]:
        """Render to OpenAI-style chat messages."""
        user = self.render(**values)
        msgs = []
        if self.system:
            msgs.append({"role": "system", "content": self._render_text(self.system, values)})
        msgs.append({"role": "user", "content": user})
        return msgs
