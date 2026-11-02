"""Compare rule coverage of the nautilus-antlr-coverage-fuzzer against grammarinator.

Both tools generate the same number of inputs for one ANTLR grammar. Every input is
traced with `antlr4-parse`, and for each rule we count how many inputs visited it.
The two histograms share the same unit (inputs per rule) and the same rule column,
so they can be plotted or diffed directly:

    <out>/nautilus.csv       rule,count,fraction
    <out>/grammarinator.csv  rule,count,fraction
    <out>/discovery.csv      step,nautilus_new,nautilus_cumulative,grammarinator_new,grammarinator_cumulative
                             (rules first discovered at each generation step, and the running total)
    <out>/comparison.csv     rule,nautilus_count,nautilus_fraction,grammarinator_count,grammarinator_fraction

With --plot (or --plot-only on an existing output directory) it also writes
comparison.png, nautilus.png and grammarinator.png next to the CSVs.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from tqdm import tqdm

from .plot import plot_all

ANTLR_VERSION = "4.13.2"
REPO_ROOT = Path(__file__).resolve().parents[4]
FUZZER_DIR = REPO_ROOT / "test" / "nautilus-antlr-coverage-fuzzer"
FUZZER_BIN = FUZZER_DIR / "target" / "release" / "nautilus-antlr-coverage-fuzzer"

COMMENT_RE = re.compile(r"(?s)/\*.*?\*/|//[^\n]*")
PARSER_RULE_RE = re.compile(r"(?m)^\s*([a-z][A-Za-z0-9_]*)\s*:")
LEXER_RULE_RE = re.compile(r"(?ms)^[ \t]*(fragment\s+)?([A-Z][A-Za-z0-9_]*)\s*:(.*?);")
TOKEN_TYPE_RE = re.compile(r"<(-?\d+)>")


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    result = subprocess.run(
        cmd, cwd=REPO_ROOT, capture_output=True, text=True, **kwargs
    )
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed:\n{result.stderr or result.stdout}")
    return result


def grammar_rules(grammar_files: list[Path]) -> list[str]:
    """Parser rules plus lexer rules that surface as tokens (mirrors antlr.rs)."""
    rules: dict[str, None] = {}
    sources = [COMMENT_RE.sub("", f.read_text(errors="ignore")) for f in grammar_files]
    for source in sources:
        for name in PARSER_RULE_RE.findall(source):
            rules.setdefault(name)
    for source in sources:
        for fragment, name, body in LEXER_RULE_RE.findall(source):
            if fragment:
                continue
            if "->" in body and "skip" in body:
                continue
            if "channel(HIDDEN)" in body:
                continue
            rules.setdefault(name)
    return list(rules)


def token_vocabulary(grammar_files: list[Path]) -> dict[int, str]:
    """Token type number -> lexer rule name, since the trace only prints numbers."""
    vocabulary: dict[int, str] = {}
    with tempfile.TemporaryDirectory(prefix="babel-bench-tokens-") as tmp:
        subprocess.run(
            ["uv", "run", "antlr4", "-v", ANTLR_VERSION, "-o", tmp]
            + [str(f) for f in grammar_files],
            cwd=REPO_ROOT,
            capture_output=True,
        )
        for tokens_file in Path(tmp).glob("*.tokens"):
            for line in tokens_file.read_text().splitlines():
                name, _, number = line.rpartition("=")
                if not name or name.startswith("'") or name.startswith("T__"):
                    continue
                if number.strip().lstrip("-").isdigit():
                    vocabulary.setdefault(int(number), name)
    return vocabulary


def trace_visited_rules(
    grammar_files: list[Path],
    start_rule: str,
    text: str,
    vocabulary: dict[int, str],
) -> set[str]:
    proc = subprocess.run(
        ["uv", "run", "antlr4-parse", "-v", ANTLR_VERSION]
        + [str(f) for f in grammar_files]
        + [start_rule, "-trace"],
        cwd=REPO_ROOT,
        input=text,
        capture_output=True,
        text=True,
        errors="replace",
    )
    visited: set[str] = set()
    for line in (proc.stdout + "\n" + proc.stderr).splitlines():
        line = line.strip()
        if line.startswith("enter") and line[5:6].isspace():
            visited.add(line[5:].split(",")[0].strip())
        elif line.startswith("consume"):
            match = TOKEN_TYPE_RE.search(line)
            if match and (rule := vocabulary.get(int(match.group(1)))):
                visited.add(rule)
    return visited


def write_histogram(
    path: Path, rules: list[str], counts: Counter[str], total_inputs: int
) -> None:
    all_rules = sorted(set(rules) | set(counts))
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["rule", "count", "fraction"])
        for rule in all_rules:
            writer.writerow(
                [rule, counts[rule], f"{counts[rule] / max(total_inputs, 1):.6f}"]
            )


def write_discovery(path: Path, first_seen: dict[str, int]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["rule", "step"])
        for rule, step in sorted(first_seen.items(), key=lambda kv: (kv[1], kv[0])):
            writer.writerow([rule, step])


def read_discovery(path: Path) -> Counter[int]:
    """step -> number of rules first visited at that step."""
    with path.open(newline="") as f:
        return Counter(int(row["step"]) for row in csv.DictReader(f))


def write_discovery_steps(
    path: Path, nautilus: Path, grammarinator: Path, total_steps: int
) -> None:
    naut, gram = read_discovery(nautilus), read_discovery(grammarinator)
    steps = max(total_steps, *naut, *gram)
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "step",
                "nautilus_new",
                "nautilus_cumulative",
                "grammarinator_new",
                "grammarinator_cumulative",
            ]
        )
        nc = gc = 0
        for step in range(1, steps + 1):
            nc += naut[step]
            gc += gram[step]
            writer.writerow([step, naut[step], nc, gram[step], gc])


def read_histogram(path: Path) -> dict[str, tuple[int, float]]:
    with path.open(newline="") as f:
        return {
            row["rule"]: (int(row["count"]), float(row["fraction"]))
            for row in csv.DictReader(f)
        }


def write_comparison(path: Path, nautilus: Path, grammarinator: Path) -> None:
    naut, gram = read_histogram(nautilus), read_histogram(grammarinator)
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "rule",
                "nautilus_count",
                "nautilus_fraction",
                "grammarinator_count",
                "grammarinator_fraction",
            ]
        )
        for rule in sorted(set(naut) | set(gram)):
            nc, nf = naut.get(rule, (0, 0.0))
            gc, gf = gram.get(rule, (0, 0.0))
            writer.writerow([rule, nc, f"{nf:.6f}", gc, f"{gf:.6f}"])


def run_nautilus(
    grammar_dir: Path,
    grammar_files: list[Path],
    start_rule: str,
    repetitions: int,
    histogram: Path,
    discovery: Path,
    work_dir: Path,
) -> dict:
    subprocess.run(["cargo", "build", "--release"], cwd=FUZZER_DIR, check=True)
    nautilus_grammar = work_dir / "nautilus_grammar.py"
    run(
        ["uv", "run", "babel-cli", "translate", "-i"]
        + [str(f) for f in grammar_files]
        + ["-o", str(nautilus_grammar), "-s", start_rule]
    )
    result = run(
        [
            str(FUZZER_BIN),
            "--histogram",
            str(histogram),
            "--discovery",
            str(discovery),
            str(nautilus_grammar),
            str(repetitions),
            *(str(f) for f in grammar_files),
        ]
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


def run_grammarinator(
    grammar_files: list[Path],
    start_rule: str,
    repetitions: int,
    depth: int,
    jobs: int,
    histogram: Path,
    discovery: Path,
    rules: list[str],
    work_dir: Path,
) -> int:
    gen_dir = work_dir / "grammarinator"
    tests_dir = gen_dir / "tests"
    tests_dir.mkdir(parents=True)
    run(
        ["uv", "run", "grammarinator-process"]
        + [str(f) for f in grammar_files]
        + ["-o", str(gen_dir)]
    )
    generators = sorted(gen_dir.glob("*Generator.py"))
    if len(generators) != 1:
        raise RuntimeError(f"expected one generator in {gen_dir}, got {generators}")
    generator = f"{generators[0].stem}.{generators[0].stem}"
    run(
        [
            "uv",
            "run",
            "grammarinator-generate",
            generator,
            "-r",
            start_rule,
            "-d",
            str(depth),
            "-o",
            str(tests_dir / "test_%d"),
            "-n",
            str(repetitions),
            "--sys-path",
            str(gen_dir),
        ]
    )

    vocabulary = token_vocabulary(grammar_files)
    tests = sorted(tests_dir.glob("test_*"), key=lambda t: int(t.name.split("_")[1]))
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        traces = pool.map(
            lambda t: trace_visited_rules(
                grammar_files,
                start_rule,
                t.read_text(errors="replace"),
                vocabulary,
            ),
            tests,
        )
        counts: Counter[str] = Counter()
        first_seen: dict[str, int] = {}
        for step, visited in enumerate(
            tqdm(traces, total=len(tests), desc="grammarinator: tracing"), start=1
        ):
            counts.update(visited)
            for rule in visited:
                first_seen.setdefault(rule, step)
    write_histogram(histogram, rules, counts, len(tests))
    write_discovery(discovery, first_seen)
    return len(tests)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "grammar",
        type=Path,
        nargs="?",
        help="directory with the .g4 file(s) and a `startsymbol` file (like test/test-grammars/http)",
    )
    parser.add_argument(
        "-n",
        "--repetitions",
        type=int,
        default=200,
        help="inputs to generate per tool (fuzzer executions / grammarinator generations)",
    )
    parser.add_argument(
        "-o", "--output", type=Path, default=Path("benchmark-out"), help="output directory"
    )
    parser.add_argument(
        "-d",
        "--depth",
        type=int,
        default=20,
        help="grammarinator maximum tree depth; output size grows exponentially with it "
        "(on modelica 20 takes ~1s for 20 inputs, 30 takes minutes)",
    )
    parser.add_argument(
        "-j", "--jobs", type=int, default=8, help="parallel antlr4-parse runs"
    )
    parser.add_argument(
        "--plot",
        action="store_true",
        help="after the run, plot the histograms (comparison and one per tool) as PNGs in the output directory",
    )
    parser.add_argument(
        "--plot-only",
        action="store_true",
        help="skip the run and only plot the CSVs already in the output directory",
    )
    args = parser.parse_args()

    if args.plot_only:
        for path in plot_all(args.output.resolve()):
            print(f"wrote {path}")
        return
    if args.grammar is None:
        parser.error("the grammar directory is required unless --plot-only is given")

    grammar_dir = args.grammar.resolve()
    grammar_files = sorted(grammar_dir.glob("*.g4"))
    if not grammar_files:
        parser.error(f"no .g4 files in {grammar_dir}")
    start_rule = (grammar_dir / "startsymbol").read_text().strip()
    rules = grammar_rules(grammar_files)

    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    nautilus_csv = out / "nautilus.csv"
    grammarinator_csv = out / "grammarinator.csv"
    nautilus_discovery = out / "nautilus_discovery.csv"
    grammarinator_discovery = out / "grammarinator_discovery.csv"

    with tempfile.TemporaryDirectory(prefix="babel-bench-") as tmp:
        work_dir = Path(tmp)
        print("running nautilus fuzzer ...")
        report = run_nautilus(
            grammar_dir, grammar_files, start_rule, args.repetitions,
            nautilus_csv, nautilus_discovery, work_dir
        )
        print("running grammarinator ...")
        generated = run_grammarinator(
            grammar_files,
            start_rule,
            args.repetitions,
            args.depth,
            args.jobs,
            grammarinator_csv,
            grammarinator_discovery,
            rules,
            work_dir,
        )

    write_comparison(out / "comparison.csv", nautilus_csv, grammarinator_csv)
    write_discovery_steps(
        out / "discovery.csv",
        nautilus_discovery,
        grammarinator_discovery,
        max(report["repetitions"], generated),
    )

    naut, gram = read_histogram(nautilus_csv), read_histogram(grammarinator_csv)
    total = len(naut)
    print(f"\nrules: {total}")
    print(
        f"nautilus:      {sum(c > 0 for c, _ in naut.values())}/{total} rules covered "
        f"({report['repetitions']} inputs)"
    )
    print(
        f"grammarinator: {sum(c > 0 for c, _ in gram.values())}/{total} rules covered "
        f"({generated} inputs)"
    )
    print(f"histograms written to {out}")
    if args.plot:
        for path in plot_all(out):
            print(f"wrote {path}")
