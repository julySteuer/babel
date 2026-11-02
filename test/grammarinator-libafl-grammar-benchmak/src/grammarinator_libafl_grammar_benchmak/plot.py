"""Plot the CSVs written by the benchmark (comparison plus one figure per tool)."""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

COLORS = {"nautilus": "#1f77b4", "grammarinator": "#ff7f0e"}


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def _bar_height(rule_count: int) -> float:
    return max(4.0, 0.22 * rule_count + 1.5)


def _plot_single(out: Path, tool: str, histogram: list[dict], discovery: list[dict]) -> Path:
    rows = sorted(histogram, key=lambda r: (-float(r["fraction"]), r["rule"]))
    steps = [int(r["step"]) for r in discovery]
    cumulative = [int(r[f"{tool}_cumulative"]) for r in discovery]

    fig, (ax_hist, ax_disc) = plt.subplots(
        1,
        2,
        figsize=(14, _bar_height(len(rows))),
        gridspec_kw={"width_ratios": [2, 1]},
    )
    ax_hist.barh([r["rule"] for r in rows], [float(r["fraction"]) for r in rows], color=COLORS[tool])
    ax_hist.invert_yaxis()
    ax_hist.set_xlim(0, 1)
    ax_hist.set_xlabel("fraction of inputs visiting the rule")
    ax_hist.set_title(f"{tool}: rule histogram")
    ax_hist.tick_params(axis="y", labelsize=7)

    ax_disc.step(steps, cumulative, where="post", color=COLORS[tool])
    ax_disc.set_xlabel("generation step")
    ax_disc.set_ylabel("rules discovered (cumulative)")
    ax_disc.set_ylim(0, len(rows))
    ax_disc.set_title(f"{tool}: discovery")
    ax_disc.grid(alpha=0.3)

    fig.tight_layout()
    path = out / f"{tool}.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _plot_comparison(out: Path, comparison: list[dict], discovery: list[dict]) -> Path:
    rows = sorted(
        comparison,
        key=lambda r: (
            -(float(r["nautilus_fraction"]) + float(r["grammarinator_fraction"])),
            r["rule"],
        ),
    )
    fig, (ax_hist, ax_disc) = plt.subplots(
        1,
        2,
        figsize=(16, _bar_height(len(rows))),
        gridspec_kw={"width_ratios": [2, 1]},
    )
    ys = range(len(rows))
    h = 0.4
    ax_hist.barh(
        [y - h / 2 for y in ys],
        [float(r["nautilus_fraction"]) for r in rows],
        height=h,
        color=COLORS["nautilus"],
        label="nautilus",
    )
    ax_hist.barh(
        [y + h / 2 for y in ys],
        [float(r["grammarinator_fraction"]) for r in rows],
        height=h,
        color=COLORS["grammarinator"],
        label="grammarinator",
    )
    ax_hist.set_yticks(list(ys), [r["rule"] for r in rows])
    ax_hist.invert_yaxis()
    ax_hist.set_xlim(0, 1)
    ax_hist.set_xlabel("fraction of inputs visiting the rule")
    ax_hist.set_title("rule histogram")
    ax_hist.tick_params(axis="y", labelsize=7)
    ax_hist.legend()

    steps = [int(r["step"]) for r in discovery]
    for tool in COLORS:
        ax_disc.step(
            steps,
            [int(r[f"{tool}_cumulative"]) for r in discovery],
            where="post",
            color=COLORS[tool],
            label=tool,
        )
    ax_disc.set_xlabel("generation step")
    ax_disc.set_ylabel("rules discovered (cumulative)")
    ax_disc.set_ylim(0, len(rows))
    ax_disc.set_title("discovery")
    ax_disc.grid(alpha=0.3)
    ax_disc.legend()

    fig.tight_layout()
    path = out / "comparison.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_all(out: Path) -> list[Path]:
    """Read the benchmark CSVs in `out` and write comparison.png, nautilus.png, grammarinator.png."""
    discovery = _read(out / "discovery.csv")
    paths = [_plot_comparison(out, _read(out / "comparison.csv"), discovery)]
    for tool in COLORS:
        paths.append(_plot_single(out, tool, _read(out / f"{tool}.csv"), discovery))
    return paths
