"""promptforge command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .evaluate import EvalSuite, run_suite
from .models import get_model
from .registry import PromptRegistry

# --- tiny ANSI helpers (auto-disabled when not a TTY or NO_COLOR is set) ---
import os

_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text


bold = lambda t: _c("1", t)  # noqa: E731
dim = lambda t: _c("2", t)  # noqa: E731
green = lambda t: _c("32", t)  # noqa: E731
red = lambda t: _c("31", t)  # noqa: E731
lime = lambda t: _c("38;5;154", t)  # noqa: E731


def _bar(score: float, width: int = 20) -> str:
    filled = round(score * width)
    return lime("█" * filled) + dim("░" * (width - filled))


def _parse_vars(pairs: list[str]) -> dict[str, str]:
    out = {}
    for p in pairs or []:
        if "=" not in p:
            raise SystemExit(f"--var expects key=value, got '{p}'")
        k, v = p.split("=", 1)
        if v.startswith("@"):
            v = Path(v[1:]).read_text(encoding="utf-8")
        out[k] = v
    return out


def cmd_list(args, reg: PromptRegistry) -> int:
    if not reg.names():
        print(f"No prompts found in {reg.root}/")
        return 1
    for name in reg.names():
        latest = reg.get(name)
        vs = ", ".join(f"v{v}" for v in reg.versions(name))
        print(f"{bold(name):<28} {dim(vs):<18} {latest.description}")
    return 0


def cmd_show(args, reg: PromptRegistry) -> int:
    t = reg.get(args.ref)
    print(bold(t.ref), dim(f"#{t.fingerprint}"))
    if t.description:
        print(t.description)
    print(dim(f"variables: {', '.join(t.variables) or '-'}   required: {', '.join(t.required) or '-'}"))
    if t.system:
        print(f"\n{lime('[system]')}\n{t.system}")
    print(f"\n{lime('[template]')}\n{t.template}")
    return 0


def cmd_render(args, reg: PromptRegistry) -> int:
    t = reg.get(args.ref)
    msgs = t.render_messages(**_parse_vars(args.var))
    if args.json:
        print(json.dumps(msgs, indent=2, ensure_ascii=False))
    else:
        for m in msgs:
            print(lime(f"[{m['role']}]"))
            print(m["content"], end="\n\n")
    return 0


def cmd_run(args, reg: PromptRegistry) -> int:
    t = reg.get(args.ref)
    model = get_model(args.model)
    out = model.complete(t.render_messages(**_parse_vars(args.var)), **t.params)
    print(out)
    return 0


def cmd_diff(args, reg: PromptRegistry) -> int:
    d = reg.diff(args.name, args.a, args.b)
    if not d:
        print("No differences.")
        return 0
    for line in d.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            print(green(line))
        elif line.startswith("-") and not line.startswith("---"):
            print(red(line))
        else:
            print(line)
    return 0


def cmd_eval(args, reg: PromptRegistry) -> int:
    suite = EvalSuite.from_toml(args.suite)
    model = get_model(args.model)
    refs = args.prompt or [suite.prompt]
    reports = [run_suite(suite, model, reg, ref) for ref in refs]

    if args.json:
        payload = [r.to_dict() for r in reports]
        print(json.dumps(payload[0] if len(payload) == 1 else payload, indent=2, ensure_ascii=False))
    else:
        for rep in reports:
            print(f"\n{bold(rep.suite)} · {lime(rep.prompt_ref)} {dim('#' + rep.fingerprint)} · model={rep.model}")
            for r in rep.results:
                mark = green("PASS") if r.passed else red("FAIL")
                print(f"  {mark}  {r.case_id:<26} {_bar(r.score)} {r.score:.2f}")
                if args.verbose:
                    for d in r.details:
                        print(dim(f"          {d['check']:<34} {d['score']:.2f} (w={d['weight']})"))
            print(f"  {dim('mean')} {rep.mean:.2f}   {dim('pass rate')} {rep.pass_rate:.0%}")
        if len(reports) > 1:
            best = max(reports, key=lambda r: r.mean)
            print(f"\n{bold('winner:')} {lime(best.prompt_ref)} (mean {best.mean:.2f})")

    if args.fail_under is not None and min(r.mean for r in reports) < args.fail_under:
        return 2
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="promptforge", description="Versioned prompts + rubric evals.")
    p.add_argument("--prompts", default=os.environ.get("PROMPTFORGE_PROMPTS", "prompts"), help="prompt registry dir")
    p.add_argument("--version", action="version", version=f"promptforge {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="list prompts and versions")

    s = sub.add_parser("show", help="show a prompt (name or name@vN)")
    s.add_argument("ref")

    for name, helptext in (("render", "render a prompt with variables"), ("run", "render and send to a model")):
        s = sub.add_parser(name, help=helptext)
        s.add_argument("ref")
        s.add_argument("-v", "--var", action="append", help="key=value (use key=@file.txt to read a file)")
        if name == "render":
            s.add_argument("--json", action="store_true")
        else:
            s.add_argument("-m", "--model", default="mock", help="mock | openai")

    s = sub.add_parser("diff", help="diff two versions of a prompt")
    s.add_argument("name")
    s.add_argument("a", type=int)
    s.add_argument("b", type=int)

    s = sub.add_parser("eval", help="run an evaluation suite")
    s.add_argument("suite")
    s.add_argument("-p", "--prompt", action="append", help="override prompt ref; repeat to A/B compare")
    s.add_argument("-m", "--model", default="mock", help="mock | openai")
    s.add_argument("--json", action="store_true")
    s.add_argument("--verbose", action="store_true")
    s.add_argument("--fail-under", type=float, help="exit 2 if mean score is below this")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    reg = PromptRegistry(args.prompts)
    handlers = {"list": cmd_list, "show": cmd_show, "render": cmd_render, "run": cmd_run, "diff": cmd_diff, "eval": cmd_eval}
    try:
        return handlers[args.cmd](args, reg)
    except (LookupError, ValueError, RuntimeError) as e:
        print(red(f"error: {e}"), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
