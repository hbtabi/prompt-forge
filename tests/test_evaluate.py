import json
from pathlib import Path

from promptforge import Check, EvalSuite, MockModel, PromptRegistry, Rubric, run_suite
from promptforge.cli import main

ROOT = Path(__file__).resolve().parents[1]


def test_checks_basic():
    assert Check("contains", "london").score("Made in London") == 1.0
    assert Check("contains", ["a", "zzz"]).score("abc") == 0.5
    assert Check("not_contains", "As an AI").score("As an AI model...") == 0.0
    assert Check("max_words", 3).score("one two three") == 1.0
    assert 0 < Check("max_words", 4).score("one two three four five six") < 1
    assert Check("json_valid").score('{"a": 1}') == 1.0
    assert Check("json_valid").score("nope") == 0.0
    assert Check("json_keys", ["a", "b"]).score('```json\n{"a": 1}\n```') == 0.5
    assert Check("regex", r"^- ").score("- item") == 1.0
    assert Check("line_count", 3).score("a\nb\nc") == 1.0


def test_rubric_weighted_mean():
    r = Rubric([Check("contains", "x", weight=3), Check("contains", "y", weight=1)])
    score, details = r.score("x marks the spot")
    assert score == 0.75
    assert len(details) == 2


def test_mock_model_follows_instructions():
    m = MockModel()
    out = m.complete([{"role": "user", "content": 'Return JSON with keys: name, price\n<text>Lamp. £20.</text>'}])
    assert set(json.loads(out)) == {"name", "price"}
    out = m.complete([{"role": "user", "content": 'Give 3 bullet points.\n"""One. Two. Three. Four."""'}])
    assert out.count("\n") == 2 and out.startswith("- ")
    long = " ".join(["word"] * 100)
    out = m.complete([{"role": "user", "content": f'Summarise in 10 words.\n"""{long}."""'}])
    assert len(out.split()) == 10


def test_suite_v2_beats_v1_on_mock():
    reg = PromptRegistry(ROOT / "prompts")
    suite = EvalSuite.from_toml(ROOT / "evals" / "summarise.toml")
    v1 = run_suite(suite, MockModel(), reg, "summarise@v1")
    v2 = run_suite(suite, MockModel(), reg, "summarise@v2")
    assert v2.mean >= v1.mean
    assert v2.pass_rate == 1.0


def test_json_suite_passes():
    reg = PromptRegistry(ROOT / "prompts")
    res = run_suite(EvalSuite.from_toml(ROOT / "evals" / "product-json.toml"), MockModel(), reg)
    assert res.pass_rate == 1.0
    assert res.to_dict()["fingerprint"] == reg.get("product-json").fingerprint


def test_cli_end_to_end(capsys):
    prompts = str(ROOT / "prompts")
    assert main(["--prompts", prompts, "list"]) == 0
    assert "summarise" in capsys.readouterr().out
    assert main(["--prompts", prompts, "render", "summarise", "-v", "text=Hello there."]) == 0
    assert "Hello there." in capsys.readouterr().out
    code = main(["--prompts", prompts, "eval", str(ROOT / "evals" / "summarise.toml"), "--json", "--fail-under", "0.5"])
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["prompt"] == "summarise@v2"
    assert main(["--prompts", prompts, "show", "nope"]) == 1
