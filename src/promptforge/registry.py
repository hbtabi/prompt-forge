"""A folder-based prompt registry: prompts/<name>/v<N>.toml"""

from __future__ import annotations

import difflib
from pathlib import Path

from .template import PromptTemplate


class PromptNotFoundError(LookupError):
    pass


class PromptRegistry:
    def __init__(self, root: str | Path = "prompts"):
        self.root = Path(root)
        self._cache: dict[str, dict[int, PromptTemplate]] = {}
        self.reload()

    def reload(self) -> None:
        self._cache.clear()
        if not self.root.exists():
            return
        for file in sorted(self.root.glob("*/v*.toml")):
            tpl = PromptTemplate.from_toml(file)
            self._cache.setdefault(tpl.name, {})[tpl.version] = tpl

    def names(self) -> list[str]:
        return sorted(self._cache)

    def versions(self, name: str) -> list[int]:
        if name not in self._cache:
            raise PromptNotFoundError(f"No prompt named '{name}' in {self.root}")
        return sorted(self._cache[name])

    def get(self, ref: str) -> PromptTemplate:
        """Resolve 'name', 'name@latest' or 'name@v2' / 'name@2'."""
        name, _, ver = ref.partition("@")
        versions = self.versions(name)
        if not ver or ver == "latest":
            return self._cache[name][versions[-1]]
        num = int(ver.lstrip("v"))
        if num not in self._cache[name]:
            raise PromptNotFoundError(f"'{name}' has no v{num} (available: {versions})")
        return self._cache[name][num]

    def diff(self, name: str, a: int, b: int) -> str:
        ta, tb = self.get(f"{name}@v{a}"), self.get(f"{name}@v{b}")
        left = (f"[system]\n{ta.system}\n\n[template]\n{ta.template}\n").splitlines(keepends=True)
        right = (f"[system]\n{tb.system}\n\n[template]\n{tb.template}\n").splitlines(keepends=True)
        return "".join(difflib.unified_diff(left, right, fromfile=ta.ref, tofile=tb.ref))
