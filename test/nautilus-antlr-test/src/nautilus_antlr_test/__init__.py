"""Evaluate nautilus-grammar-performance's ANTLR rule-coverage performance across the
antlr/grammars-v4 corpus and report an overall and a per-grammar score."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import subprocess
import tempfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from prettytable import PrettyTable
from tqdm import tqdm

GRAMMARS_V4_URL = "https://github.com/antlr/grammars-v4"
REPO_ROOT = Path(__file__).resolve().parents[4]
FUZZER_DIR = REPO_ROOT / "test" / "nautilus-grammar-performance"
FUZZER_BIN = FUZZER_DIR / "target" / "release" / "nautilus-grammar-performance"

# Comments, but string literals and char sets are matched too (and kept) so that `'//'` or `'/*'` in a rule is
# not read as the start of a comment.
COMMENT_RE = re.compile(
    r"(?s)'(?:\\.|[^'\\\n])*'|\[(?:\\.|[^\]\\\n])*\]|/\*.*?\*/|//[^\n]*"
)
LITERAL_RE = re.compile(r"'(?:\\.|[^'\\\n])*'|\[(?:\\.|[^\]\\\n])*\]")
# `name`, optional `[args]`, `returns [..]`, `locals [..]` (char sets are masked to '' by LITERAL_RE), then the `:`.
# Keep in sync with PARSER_RULE_HEAD in nautilus-grammar-performance/src/antlr.rs.
PARSER_RULE_RE = re.compile(
    r"(?m)^[ \t]*([a-z][A-Za-z0-9_]*)(?:\s|'')*"
    r"(?:(?:returns|locals|throws)(?:\s|'')*(?:\w+(?:\s*,\s*\w+)*)?(?:\s|'')*)*:"
)

DEFAULT_DEPTH = 10000  # tree size budget in nodes, not tree depth (see nautilus-grammar-performance --depth)
DEFAULT_CANDIDATES = 100000  # random trees generated per grammar; only the deepest `repetitions` are parsed
DEFAULT_SEED_TIMEOUT = 20  # seconds antlr4-parse may take for one seed before it is killed


@dataclasses.dataclass
class GrammarUnit:
    name: str
    files: list[Path]


def clone_grammars_v4(dest: Path) -> Path:
    subprocess.run(
        ["git", "clone", "--depth", "1", GRAMMARS_V4_URL, str(dest)], check=True
    )
    return dest


def prune_non_grammar_files(root: Path) -> None:
    for path in root.rglob("*"):
        if ".git" in path.parts:
            continue
        if path.is_file() and path.suffix != ".g4":
            path.unlink()


def discover_units(root: Path) -> list[GrammarUnit]:
    by_dir: dict[Path, list[Path]] = defaultdict(list)
    for path in root.rglob("*.g4"):
        by_dir[path.parent].append(path)

    units: list[GrammarUnit] = []
    for files in by_dir.values():
        by_name = {f.name: f for f in files}
        paired: set[Path] = set()
        for f in files:
            if f.stem.endswith("Lexer"):
                parser_file = by_name.get(f"{f.stem[: -len('Lexer')]}Parser.g4")
                if parser_file is not None:
                    units.append(
                        GrammarUnit(
                            name=f.stem[: -len("Lexer")], files=[parser_file, f]
                        )
                    )
                    paired.update([f, parser_file])
        units.extend(
            GrammarUnit(name=f.stem, files=[f]) for f in files if f not in paired
        )
    return units


def _strip_braced_blocks(source: str) -> str:
    """Removes `{...}` blocks (actions, @members, options): they hold target-language code, not rules."""
    out: list[str] = []
    depth = 0
    for char in source:
        if char == "{":
            depth += 1
        elif char == "}" and depth:
            depth -= 1
        elif not depth:
            out.append(char)
    return "".join(out)


def clean_grammar(source: str) -> str:
    """Only the rule structure of a grammar: no comments, literals and char sets reduced to '', no {...} blocks.
    Keep in sync with clean_grammar in nautilus-grammar-performance/src/antlr.rs."""
    without_comments = COMMENT_RE.sub(
        lambda m: m.group(0) if m.group(0)[0] in "'[" else "", source
    )
    return _strip_braced_blocks(LITERAL_RE.sub("''", without_comments))


def find_start_rule(unit: GrammarUnit) -> str | None:
    """The parser rule a parse should start at.

    The first rule of a file is often not it (Ada2005 starts with `identifier`, algol60 with `empty_`). Entry rules
    are the ones nothing else refers to, and usually the ones that end in EOF, so the order of preference is:
    an unreferenced rule using EOF, any rule using EOF, an unreferenced rule, the first rule.
    """
    source = clean_grammar("\n".join(f.read_text(errors="ignore") for f in unit.files))
    bodies: dict[str, str] = {}  # in order of definition; a rule that is defined twice keeps its first body
    for head in PARSER_RULE_RE.finditer(source):
        end = source.find(";", head.end())
        body = source[head.end() : end if end != -1 else len(source)]
        bodies.setdefault(head.group(1), re.sub(r"#\s*\w+", "", body))  # `# label` is not a reference
    if not bodies:
        return None

    referenced = {
        name
        for rule, body in bodies.items()
        for name in re.findall(r"\b[a-z][A-Za-z0-9_]*\b", body)
        if name in bodies and name != rule
    }
    names = list(bodies)
    unreferenced = [n for n in names if n not in referenced]
    uses_eof = [n for n in names if re.search(r"\bEOF\b", bodies[n])]
    for candidates in (
        [n for n in unreferenced if n in uses_eof],
        uses_eof,
        unreferenced,
        names,
    ):
        if candidates:
            return candidates[0]
    return None


def build_fuzzer() -> None:
    subprocess.run(["cargo", "build", "--release"], cwd=FUZZER_DIR, check=True)


def translate_to_nautilus(
    unit: GrammarUnit, start_symbol: str, output: Path, whitespace: str = "auto"
) -> None:
    subprocess.run(
        [
            "uv",
            "run",
            "babel-cli",
            "translate",
            "-i",
            *(str(f) for f in unit.files),
            "-o",
            str(output),
            "-s",
            start_symbol,
            "--whitespace",
            whitespace,
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def run_fuzzer(
    nautilus_grammar: Path,
    unit: GrammarUnit,
    start_rule: str,
    repetitions: int,
    depth: int = DEFAULT_DEPTH,
    candidates: int = DEFAULT_CANDIDATES,
    seed_timeout: int = DEFAULT_SEED_TIMEOUT,
    timeout: int | None = None,
) -> dict:
    """Generates `candidates` random trees, parses the `repetitions` deepest ones with ANTLR and reports the coverage."""
    if timeout is None:  # every seed may use up its limit, plus time for translating and generating
        timeout = repetitions * seed_timeout + 600
    try:
        result = subprocess.run(
            [
                str(FUZZER_BIN),
                "-n",
                str(repetitions),
                "--depth",
                str(depth),
                "--candidates",
                str(candidates),
                "--start-rule",
                start_rule,
                "--antlr-timeout",
                str(seed_timeout),
                *(arg for f in unit.files for arg in ("--antlr", str(f))),
                str(nautilus_grammar),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as err:
        raise RuntimeError(f"fuzzer timed out after {timeout}s") from err
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip().splitlines()[-1]
            if result.stderr.strip()
            else "fuzzer exited with a non-zero status"
        )
    raw = json.loads(result.stdout.strip().splitlines()[-1])
    return {
        "coverage": raw["antlr_coverage"],
        "visited_rules": raw["antlr_rules_visited"],
        "total_rules": raw["antlr_rules_total"],
        "production_coverage": raw["production_coverage"],
        "seeds": raw["seeds"],
        "unique_seeds": raw["unique_seeds"],
        "avg_seed_bytes": raw["avg_seed_bytes"],
        "elapsed_secs": raw["elapsed_secs"],
        "start_rule": raw["antlr_start_rule"],
        "vocabulary_size": raw["antlr_vocabulary_size"],
        "empty_traces": raw["antlr_empty_traces"],
        "timed_out_seeds": raw["antlr_timeouts"],
    }


def tool_failure(report: dict) -> str | None:
    """antlr4-parse always enters the start rule, so a seed without any trace means the ANTLR tooling failed
    (grammar needs a target-specific base class, wrong start rule, ...). That is not a coverage of 0."""
    if report["seeds"] > 0 and report["empty_traces"] == report["seeds"]:
        return f"antlr4-parse produced no trace for any of the {report['seeds']} seeds (start rule {report['start_rule']!r})"
    if report["seeds"] > 0 and report["timed_out_seeds"] == report["seeds"]:
        return f"antlr4-parse timed out on all {report['seeds']} seeds (start rule {report['start_rule']!r})"
    return None


def evaluate_unit(
    unit: GrammarUnit,
    repetitions: int,
    work_dir: Path,
    translate_only: bool = False,
    depth: int = DEFAULT_DEPTH,
    candidates: int = DEFAULT_CANDIDATES,
    seed_timeout: int = DEFAULT_SEED_TIMEOUT,
    timeout: int | None = None,
    whitespace: str = "auto",
    file_stem: str | None = None,
) -> dict:
    start_symbol = find_start_rule(unit)
    if start_symbol is None:
        return {
            "name": unit.name,
            "status": "skipped",
            "reason": "no parser rules found",
        }

    # unit names are not unique across the corpus, the file name must be
    nautilus_grammar = work_dir / f"{file_stem or unit.name}.py"
    try:
        translate_to_nautilus(unit, start_symbol, nautilus_grammar, whitespace)
        if translate_only:
            return {"name": unit.name, "status": "ok"}
        report = run_fuzzer(
            nautilus_grammar,
            unit,
            start_symbol,
            repetitions,
            depth,
            candidates,
            seed_timeout,
            timeout,
        )
    except subprocess.CalledProcessError as err:
        return {
            "name": unit.name,
            "status": "error",
            "reason": (err.stderr or str(err)).strip(),
        }
    except Exception as err:  # noqa: BLE001 - every failure is a data point for the score
        return {"name": unit.name, "status": "error", "reason": str(err).strip()}

    failure = tool_failure(report)
    if failure is not None:
        return {"name": unit.name, "status": "error", "reason": failure, **report}
    return {"name": unit.name, "status": "ok", **report}


def summarize(results: list[dict]) -> dict:
    ok = [r for r in results if r["status"] == "ok"]
    measured = [r for r in ok if "coverage" in r]
    coverages = [r["coverage"] for r in measured]
    visited = sum(r["visited_rules"] for r in measured)
    total = sum(r["total_rules"] for r in measured)
    return {
        "grammars_total": len(results),
        "grammars_ok": len(ok),
        "grammars_skipped": sum(r["status"] == "skipped" for r in results),
        "grammars_errored": sum(r["status"] == "error" for r in results),
        "grammars_antlr_tool_failed": sum(
            r["status"] == "error" and "no trace" in r.get("reason", "")
            for r in results
        ),
        "grammars_with_timed_out_seeds": sum(r.get("timed_out_seeds", 0) > 0 for r in results),
        "seeds_timed_out": sum(r.get("timed_out_seeds", 0) for r in results),
        "average_coverage": sum(coverages) / len(coverages) if coverages else 0.0,
        # every rule counts the same, so big grammars weigh more than in the per-grammar average
        "rule_weighted_coverage": visited / total if total else 0.0,
        "grammars_fully_covered": sum(c >= 1.0 for c in coverages),
    }


def report(results: list[dict], translate_only: bool = False) -> None:
    table = PrettyTable()
    table.field_names = ["Grammar", "Status", "Coverage", "Rules", "Seeds", "Time", "Details"]
    table.align["Grammar"] = "l"
    table.align["Details"] = "l"
    table.max_width["Details"] = 80

    for r in results:
        if r["status"] == "ok" and "coverage" not in r:
            table.add_row([r["name"], r["status"], "-", "-", "-", "-", "translated"])
        elif r["status"] == "ok":
            table.add_row(
                [
                    r["name"],
                    r["status"],
                    f"{r['coverage']:.2%}",
                    f"{r['visited_rules']}/{r['total_rules']}",
                    f"{r['unique_seeds']}/{r['seeds']}",
                    f"{r['elapsed_secs']:.0f}s",
                    f"{r['timed_out_seeds']} seed(s) timed out" if r["timed_out_seeds"] else "",
                ]
            )
        else:
            table.add_row(
                [r["name"], r["status"], "-", "-", "-", "-", r.get("reason", "")]
            )

    print(table)

    summary = summarize(results)
    print()
    print(
        f"Evaluated {summary['grammars_total']} grammar unit(s): "
        f"{summary['grammars_ok']} ok, {summary['grammars_skipped']} skipped, {summary['grammars_errored']} errored"
        f" ({summary['grammars_antlr_tool_failed']} of them because antlr4-parse produced no trace)"
    )
    if summary["seeds_timed_out"]:
        print(
            f"{summary['seeds_timed_out']} seed(s) in {summary['grammars_with_timed_out_seeds']} grammar(s) "
            "hit the antlr4-parse limit; their traces are partial"
        )
    if not translate_only:
        print(
            f"Average rule coverage across successful runs: {summary['average_coverage']:.2%} "
            f"(all rules pooled: {summary['rule_weighted_coverage']:.2%}, "
            f"{summary['grammars_fully_covered']} grammar(s) fully covered)"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repetitions",
        type=int,
        default=100,
        help="seeds per grammar that are parsed with ANTLR (the slow step, about 0.5s each)",
    )
    parser.add_argument(
        "--candidates",
        type=int,
        default=DEFAULT_CANDIDATES,
        help="random trees generated per grammar of which only the deepest --repetitions are kept "
        "(0 = no selection, the seeds are plain random trees)",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=DEFAULT_DEPTH,
        help="size budget of a generated tree in nodes (not its depth)",
    )
    parser.add_argument(
        "--whitespace",
        choices=["auto", "space", "none", "skipped"],
        default="auto",
        help="passed to babel-cli translate: what goes between parser elements",
    )
    parser.add_argument(
        "--seed-timeout",
        type=int,
        default=DEFAULT_SEED_TIMEOUT,
        help="seconds antlr4-parse may take for one seed; a slower seed is killed and counted as timed out",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="seconds the fuzzer may take per grammar (default: repetitions * seed timeout + 600)",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=max(1, (os.cpu_count() or 2) // 2),
        help="grammars evaluated in parallel (each runs JVMs; times in the report grow with it)",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="write the per-grammar results and the summary to this file",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="only evaluate the first N grammar units",
    )
    parser.add_argument(
        "--grammars-dir",
        type=Path,
        default=None,
        help="reuse an existing grammars-v4 checkout instead of cloning",
    )
    parser.add_argument(
        "--tree-size",
        type=int,
        default=None,
        help="max rule applications in a generated tree (fuzzer default if unset)",
    )
    parser.add_argument(
        "--translate-only",
        action="store_true",
        help="only translate every grammar to a nautilus grammar (no fuzzing) "
        "to find grammars that break the translation",
    )
    args = parser.parse_args()

    if not args.translate_only:
        build_fuzzer()

    with tempfile.TemporaryDirectory(prefix="babel-eval-") as tmp:
        tmp_path = Path(tmp)

        if args.grammars_dir is not None:
            grammars_root = args.grammars_dir
        else:
            grammars_root = clone_grammars_v4(tmp_path / "grammars-v4")
            prune_non_grammar_files(grammars_root)

        units = sorted(discover_units(grammars_root), key=lambda u: str(u.files[0]))
        if args.limit is not None:
            units = units[: args.limit]

        work_dir = tmp_path / "nautilus-grammars"
        work_dir.mkdir(exist_ok=True)

        results_by_index: dict[int, dict] = {}
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            futures = {
                pool.submit(
                    evaluate_unit,
                    unit,
                    args.repetitions,
                    work_dir,
                    args.translate_only,
                    args.depth,
                    args.candidates,
                    args.seed_timeout,
                    args.timeout,
                    args.whitespace,
                    f"{index:04d}_{unit.name}",
                ): index
                for index, unit in enumerate(units)
            }
            for future in tqdm(as_completed(futures), total=len(futures)):
                results_by_index[futures[future]] = future.result()
        results = [results_by_index[i] for i in range(len(units))]

    report(results, args.translate_only)

    if args.output_json is not None:
        args.output_json.write_text(
            json.dumps(
                {
                    "settings": {
                        key: str(value) if isinstance(value, Path) else value
                        for key, value in vars(args).items()
                    },
                    "summary": summarize(results),
                    "grammars": results,
                },
                indent=2,
            )
        )
