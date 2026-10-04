"""Rubric-based evaluation harness.

A rubric is a list of weighted checks. Each check returns a score in [0, 1];
the case score is the weighted mean. Suites are defined in TOML.
"""

from __future__ import annotations

import json
import re
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .models import Model
from .registry import PromptRegistry
from .template import PromptTemplate

CheckFn = Callable[[str, Any], float]


def _words(text: str) -> int:
    return len(re.findall(r"\b[\w'’-]+\b", text))


def _parse_json(text: str) -> Any:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1)
    return json.loads(text)


def _json_valid(out: str, _: Any) -> float:
    try:
        _parse_json(out)
        return 1.0
    except (ValueError, TypeError):
        return 0.0


def _json_keys(out: str, keys: list[str]) -> float:
    try:
        obj = _parse_json(out)
    except (ValueError, TypeError):
        return 0.0
    if not isinstance(obj, dict) or not keys:
        return 0.0
    return sum(k in obj for k in keys) / len(keys)


def _max_words(out: str, n: int) -> float:
    w = _words(out)
    if w <= n:
        return 1.0
    # soft penalty: lose score linearly until 2x the limit
    return max(0.0, 1 - (w - n) / n)


def _min_words(out: str, n: int) -> float:
    return min(1.0, _words(out) / n) if n else 1.0


def _contains(out: str, value: str | list[str]) -> float:
    values = [value] if isinstance(value, str) else value
    return sum(v.lower() in out.lower() for v in values) / len(values)


def _not_contains(out: str, value: str | list[str]) -> float:
    values = [value] if isinstance(value, str) else value
    return 0.0 if any(v.lower() in out.lower() for v in values) else 1.0


def _regex(out: str, pattern: str) -> float:
    return 1.0 if re.search(pattern, out, re.M) else 0.0


def _line_count(out: str, n: int) -> float:
    lines = [l for l in out.splitlines() if l.strip()]
    return 1.0 if len(lines) == n else max(0.0, 1 - abs(len(lines) - n) / max(n, 1))


CHECKS: dict[str, CheckFn] = {
    "json_valid": _json_valid,
    "json_keys": _json_keys,
    "max_words": _max_words,
    "min_words": _min_words,
    "contains": _contains,
    "not_contains": _not_contains,
    "regex": _regex,
    "line_count": _line_count,
}


def register_check(name: str, fn: CheckFn) -> None:
    """Plug in your own check: fn(output, value) -> float in [0, 1]."""
    CHECKS[name] = fn


@dataclass
class Check:
    type: str
    value: Any = None
    weight: float = 1.0
    label: str = ""

    def score(self, output: str) -> float:
        if self.type not in CHECKS:
            raise ValueError(f"Unknown check type '{self.type}'. Known: {sorted(CHECKS)}")
        return max(0.0, min(1.0, float(CHECKS[self.type](output, self.value))))

    @property
    def name(self) -> str:
        return self.label or (f"{self.type}({self.value})" if self.value is not None else self.type)


@dataclass
class Rubric:
    checks: list[Check] = field(default_factory=list)

    def score(self, output: str) -> tuple[float, list[dict[str, Any]]]:
        if not self.checks:
            return 1.0, []
        details, total, weight = [], 0.0, 0.0
        for c in self.checks:
            s = c.score(output)
            details.append({"check": c.name, "score": round(s, 3), "weight": c.weight})
            total += s * c.weight
            weight += c.weight
        return (total / weight if weight else 0.0), details


@dataclass
class Case:
    id: str
    vars: dict[str, Any]
    checks: list[Check] = field(default_factory=list)


@dataclass
class EvalSuite:
    name: str
    prompt: str
    rubric: Rubric
    cases: list[Case]
    threshold: float = 0.7

    @classmethod
    def from_toml(cls, path: str | Path) -> "EvalSuite":
        data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
        suite = data.get("suite", {})
        mk = lambda items: [Check(**c) for c in items]  # noqa: E731
        return cls(
            name=suite.get("name", Path(path).stem),
            prompt=suite["prompt"],
            threshold=float(suite.get("threshold", 0.7)),
            rubric=Rubric(mk(data.get("rubric", []))),
            cases=[Case(id=c["id"], vars=c.get("vars", {}), checks=mk(c.get("checks", []))) for c in data.get("cases", [])],
        )


@dataclass
class CaseResult:
    case_id: str
    output: str
    score: float
    passed: bool
    details: list[dict[str, Any]]
    latency_ms: float


@dataclass
class SuiteResult:
    suite: str
    prompt_ref: str
    fingerprint: str
    model: str
    threshold: float
    results: list[CaseResult]

    @property
    def mean(self) -> float:
        return sum(r.score for r in self.results) / len(self.results) if self.results else 0.0

    @property
    def pass_rate(self) -> float:
        return sum(r.passed for r in self.results) / len(self.results) if self.results else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite": self.suite,
            "prompt": self.prompt_ref,
            "fingerprint": self.fingerprint,
            "model": self.model,
            "threshold": self.threshold,
            "mean_score": round(self.mean, 3),
            "pass_rate": round(self.pass_rate, 3),
            "cases": [r.__dict__ for r in self.results],
        }


def run_suite(
    suite: EvalSuite,
    model: Model,
    registry: PromptRegistry | None = None,
    prompt: PromptTemplate | str | None = None,
) -> SuiteResult:
    """Run every case through the prompt + model and score with the rubric."""
    if isinstance(prompt, PromptTemplate):
        tpl = prompt
    else:
        if registry is None:
            raise ValueError("A registry is required when prompt is given by reference")
        tpl = registry.get(prompt or suite.prompt)

    results = []
    for case in suite.cases:
        msgs = tpl.render_messages(**case.vars)
        t0 = time.perf_counter()
        out = model.complete(msgs, **tpl.params)
        latency = (time.perf_counter() - t0) * 1000
        rubric = Rubric(suite.rubric.checks + case.checks)
        score, details = rubric.score(out)
        results.append(CaseResult(case.id, out, round(score, 3), score >= suite.threshold, details, round(latency, 2)))
    return SuiteResult(suite.name, tpl.ref, tpl.fingerprint, model.name, suite.threshold, results)
