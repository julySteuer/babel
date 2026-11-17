"""Evaluate nautilus-grammar-performance's ANTLR rule-coverage performance across the
antlr/grammars-v4 corpus and report an overall and a per-grammar score."""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path

from prettytable import PrettyTable
from tqdm import tqdm

GRAMMARS_V4_URL = "https://github.com/antlr/grammars-v4"
REPO_ROOT = Path(__file__).resolve().parents[4]
FUZZER_DIR = REPO_ROOT / "test" / "nautilus-grammar-performance"
FUZZER_BIN = FUZZER_DIR / "target" / "release" / "nautilus-grammar-performance"

COMMENT_RE = re.compile(r"(?s)/\*.*?\*/|//[^\n]*")
LITERAL_RE = re.compile(r"'(?:\\.|[^'\\\n])*'|\[(?:\\.|[^\]\\\n])*\]")
PARSER_RULE_RE = re.compile(r"(?m)^\s*([a-z][A-Za-z0-9_]*)\s*:")


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


def first_parser_rule(unit: GrammarUnit) -> str | None:
    source = "\n".join(f.read_text(errors="ignore") for f in unit.files)
    source = COMMENT_RE.sub("", source)
    source = LITERAL_RE.sub("''", source)  # a quoted `{` must not open a block
    match = PARSER_RULE_RE.search(_strip_braced_blocks(source))
    return match.group(1) if match else None


def build_fuzzer() -> None:
    subprocess.run(["cargo", "build", "--release"], cwd=FUZZER_DIR, check=True)


def translate_to_nautilus(unit: GrammarUnit, start_symbol: str, output: Path) -> None:
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
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def run_fuzzer(nautilus_grammar: Path, unit: GrammarUnit, repetitions: int) -> dict:
    result = subprocess.run(
        [
            str(FUZZER_BIN),
            "-n",
            str(repetitions),
            "--depth",
            "200",
            *(arg for f in unit.files for arg in ("--antlr", str(f))),
            str(nautilus_grammar),
        ],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip() or "fuzzer exited with a non-zero status"
        )
    raw = json.loads(result.stdout.strip().splitlines()[-1])
    return {
        "coverage": raw["antlr_coverage"],
        "visited_rules": raw["antlr_rules_visited"],
        "total_rules": raw["antlr_rules_total"],
        "production_coverage": raw["production_coverage"],
    }


def evaluate_unit(
    unit: GrammarUnit, repetitions: int, work_dir: Path, translate_only: bool = False
) -> dict:
    start_symbol = first_parser_rule(unit)
    if start_symbol is None:
        return {
            "name": unit.name,
            "status": "skipped",
            "reason": "no parser rules found",
        }

    nautilus_grammar = work_dir / f"{unit.name}.py"
    try:
        translate_to_nautilus(unit, start_symbol, nautilus_grammar)
        if translate_only:
            return {"name": unit.name, "status": "ok"}
        report = run_fuzzer(nautilus_grammar, unit, repetitions)
    except subprocess.CalledProcessError as err:
        return {
            "name": unit.name,
            "status": "error",
            "reason": (err.stderr or str(err)).strip(),
        }
    except Exception as err:  # noqa: BLE001 - every failure is a data point for the score
        return {"name": unit.name, "status": "error", "reason": str(err).strip()}

    return {"name": unit.name, "status": "ok", **report}


def summarize(results: list[dict]) -> dict:
    ok = [r for r in results if r["status"] == "ok"]
    coverages = [r["coverage"] for r in ok if "coverage" in r]
    return {
        "grammars_total": len(results),
        "grammars_ok": len(ok),
        "grammars_skipped": sum(r["status"] == "skipped" for r in results),
        "grammars_errored": sum(r["status"] == "error" for r in results),
        "average_coverage": sum(coverages) / len(coverages) if coverages else 0.0,
    }


def report(results: list[dict], translate_only: bool = False) -> None:
    table = PrettyTable()
    table.field_names = ["Grammar", "Status", "Coverage", "Rules", "Details"]
    table.align["Grammar"] = "l"
    table.align["Details"] = "l"
    table.max_width["Details"] = 80

    for r in results:
        if r["status"] == "ok" and "coverage" not in r:
            table.add_row([r["name"], r["status"], "-", "-", "translated"])
        elif r["status"] == "ok":
            table.add_row(
                [
                    r["name"],
                    r["status"],
                    f"{r['coverage']:.2%}",
                    f"{r['visited_rules']}/{r['total_rules']}",
                    "",
                ]
            )
        else:
            table.add_row([r["name"], r["status"], "-", "-", r.get("reason", "")])

    print(table)

    summary = summarize(results)
    print()
    print(
        f"Evaluated {summary['grammars_total']} grammar unit(s): "
        f"{summary['grammars_ok']} ok, {summary['grammars_skipped']} skipped, {summary['grammars_errored']} errored"
    )
    if not translate_only:
        print(
            f"Average rule coverage across successful runs: {summary['average_coverage']:.2%}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repetitions", type=int, default=200, help="fuzzer generations per grammar"
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

        units = discover_units(grammars_root)
        if args.limit is not None:
            units = units[: args.limit]

        work_dir = tmp_path / "nautilus-grammars"
        work_dir.mkdir(exist_ok=True)

        results = [
            evaluate_unit(unit, args.repetitions, work_dir, args.translate_only)
            for unit in tqdm(units)
        ]

    report(results, args.translate_only)
