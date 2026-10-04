<div align="center">

# 🔨 prompt-forge

**Versioned prompt templates and a rubric-based evaluation harness for LLM apps. Offline-first.**

[![CI](https://github.com/hbtabi/prompt-forge/actions/workflows/ci.yml/badge.svg)](https://github.com/hbtabi/prompt-forge/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)
![Dependencies](https://img.shields.io/badge/runtime%20deps-0-brightgreen)
![Tests](https://img.shields.io/badge/tests-pytest-0A9EDC?logo=pytest&logoColor=white)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

</div>

Prompts are code. They deserve versions, diffs and regression tests. **prompt-forge** treats each prompt as a
versioned TOML file, renders it with variables, runs it against a model, and scores the output with simple,
explainable rubrics, so you can tell whether `v2` is actually better than `v1` before it ships.

It runs **fully offline** with a deterministic mock model (great for CI), and switches to any
**OpenAI-compatible API** (OpenAI, OpenRouter, Groq, Ollama, LM Studio...) with one flag.

## ✨ Features

- **Prompt templates as files**: `prompts/<name>/v<N>.toml` with system + user templates, defaults and model params
- **Variables**: `{{ var }}`, inline defaults `{{ locale | British English }}`, required-variable checks, `key=@file.txt` loading
- **Versioning**: resolve `name`, `name@latest` or `name@v1`, content **fingerprints** catch silent edits, coloured `diff` between versions
- **Evaluation harness**: weighted rubric checks (`max_words`, `min_words`, `contains`, `not_contains`, `regex`, `json_valid`, `json_keys`, `line_count`) plus your own via `register_check()`
- **A/B compare**: run the same suite across several prompt versions and get a winner
- **CI gate**: `--fail-under 0.8` exits non-zero when quality regresses
- **Zero runtime dependencies**: stdlib only (Python 3.11+ `tomllib`, `urllib`)

## 📸 Demo

```text
$ promptforge eval evals/summarise.toml -p summarise@v1 -p summarise@v2

summarise-regression · summarise@v1 #803a5669e595 · model=mock
  PASS  studio-launch              ████████████████████ 1.00
  PASS  cafe-news                  ████████████████████ 1.00
  FAIL  long-report                ██████████████░░░░░░ 0.69
  mean 0.90   pass rate 67%

summarise-regression · summarise@v2 #221da29f35f7 · model=mock
  PASS  studio-launch              ████████████████████ 1.00
  PASS  cafe-news                  ████████████████████ 1.00
  PASS  long-report                ████████████████████ 0.99
  mean 1.00   pass rate 100%

winner: summarise@v2 (mean 1.00)
```

## 🚀 Quick start

```bash
git clone https://github.com/hbtabi/prompt-forge.git
cd prompt-forge
pip install -e ".[dev]"

promptforge list                                   # what's in the registry
promptforge show summarise@v2                      # template, variables, fingerprint
promptforge render summarise -v text="Hello from London."
promptforge run ugc-hook -v product="Glow serum" -v audience="busy mums" -v benefit="Rested skin in 7 days"
promptforge diff summarise 1 2                     # what changed between versions
promptforge eval evals/product-json.toml --verbose # per-check scores
pytest -q                                          # run the test suite
```

No install? `PYTHONPATH=src python -m promptforge list` works too.

### Using a real model

```bash
export OPENAI_API_KEY=sk-...
export OPENAI_BASE_URL=https://api.openai.com/v1   # or any OpenAI-compatible endpoint
export PROMPTFORGE_MODEL=gpt-4o-mini
promptforge eval evals/summarise.toml --model openai
```

## 🧩 Writing a prompt

```toml
# prompts/summarise/v2.toml
[meta]
name = "summarise"
version = 2
description = "Summarise text for a busy reader, with a hard word limit."

[prompt]
system = "You are a precise editor. You write in {{ locale | British English }}."
template = """
Summarise the text below for {{ audience }} in {{ max_words }} words or fewer.
\"\"\"{{ text }}\"\"\"
"""

[defaults]
audience = "a busy founder"
max_words = "40"

[params]
temperature = 0.2
```

## 🧪 Writing an eval suite

```toml
# evals/summarise.toml
[suite]
name = "summarise-regression"
prompt = "summarise"     # latest version unless overridden with -p
threshold = 0.75         # per-case pass mark

[[rubric]]               # applies to every case
type = "max_words"
value = 40
weight = 2

[[cases]]
id = "studio-launch"
vars = { text = "Hasenix, a London studio, launched..." }
checks = [{ type = "contains", value = ["London", "48 hours"] }]   # case-specific
```

## 🐍 Library usage

```python
from promptforge import PromptRegistry, EvalSuite, MockModel, run_suite
from promptforge.evaluate import register_check

reg = PromptRegistry("prompts")
msgs = reg.get("summarise@v2").render_messages(text="...")

register_check("ends_with_cta", lambda out, _: 1.0 if out.rstrip().endswith("!") else 0.0)

report = run_suite(EvalSuite.from_toml("evals/summarise.toml"), MockModel(), reg)
print(report.mean, report.pass_rate)
```

## 🗂️ Project structure

```
prompt-forge/
├── src/promptforge/
│   ├── template.py     # PromptTemplate: variables, defaults, fingerprint, chat messages
│   ├── registry.py     # folder-based versioned registry + diff
│   ├── models.py       # MockModel (offline) + OpenAICompatibleModel (stdlib HTTP)
│   ├── evaluate.py     # checks, rubrics, suites, runner
│   └── cli.py          # `promptforge` command
├── prompts/            # summarise (v1, v2), ugc-hook, product-json
├── evals/              # summarise.toml, product-json.toml
├── tests/              # pytest suite
└── .github/workflows/  # CI: tests + prompt regression gate
```

## 🛣️ Roadmap

- [ ] LLM-as-judge check type (with a pinned judge prompt)
- [ ] Results history (`.promptforge/runs/*.json`) and trend charts
- [ ] Parallel case execution + response caching
- [ ] Anthropic / Gemini native adapters
- [ ] HTML report export

## 📄 License

[MIT](LICENSE) © 2026 Mohammed Hassan bin Tayyeb · Built by [Hasenix](https://github.com/hbtabi)
