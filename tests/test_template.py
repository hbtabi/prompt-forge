from pathlib import Path

import pytest

from promptforge import MissingVariableError, PromptRegistry, PromptTemplate

ROOT = Path(__file__).resolve().parents[1]


def make(template: str, **kw) -> PromptTemplate:
    return PromptTemplate(name="t", version=1, template=template, **kw)


def test_render_substitutes_variables():
    assert make("Hi {{ name }}!").render(name="Ada") == "Hi Ada!"


def test_defaults_and_inline_defaults():
    t = make("{{ greeting }} {{ name | world }}", defaults={"greeting": "Hello"})
    assert t.render() == "Hello world"
    assert t.render(name="London") == "Hello London"
    assert t.required == []


def test_missing_variable_raises():
    with pytest.raises(MissingVariableError) as e:
        make("{{ a }} and {{ b }}").render(a="x")
    assert e.value.missing == ["b"]


def test_fingerprint_changes_with_content():
    assert make("a {{ x }}").fingerprint != make("b {{ x }}").fingerprint
    assert make("a").fingerprint == make("a").fingerprint


def test_render_messages_includes_system():
    t = make("Q: {{ q }}", system="Write in {{ locale | British English }}.")
    msgs = t.render_messages(q="colour?")
    assert msgs[0] == {"role": "system", "content": "Write in British English."}
    assert msgs[1]["content"] == "Q: colour?"


def test_registry_resolves_versions():
    reg = PromptRegistry(ROOT / "prompts")
    assert "summarise" in reg.names()
    assert reg.versions("summarise") == [1, 2]
    assert reg.get("summarise").version == 2
    assert reg.get("summarise@v1").version == 1
    assert reg.get("summarise@latest").version == 2
    with pytest.raises(LookupError):
        reg.get("summarise@v9")


def test_registry_diff():
    diff = PromptRegistry(ROOT / "prompts").diff("summarise", 1, 2)
    assert diff.startswith("--- summarise@v1")
    assert "+Summarise the text below" in diff
