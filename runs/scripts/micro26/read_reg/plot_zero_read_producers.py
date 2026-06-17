#!/usr/bin/env python3
"""
Plot GPR zero-read register lifetimes (count only; all entries are GPR producers).

Parses ChampSim logs containing lines like:

  ZERO_READ_PROD category=gpr count=1234567

Only GPR lifetimes are counted by the simulator (special registers excluded).
Parses ChampSim logs under runs/output/micro26/read_reg/cs_logs/<suite>/.
Suites: google_traces, spec17, graph, ai, cvp-1, cvp-1-fix (default: all six).

Output: runs/output/micro26/read_reg/graphs/zero_read_producers.tex
"""

import argparse
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LOG_DIR = ROOT / "runs/output/micro26/read_reg/cs_logs"
OUTPUT_TEX = ROOT / "runs/output/micro26/read_reg/graphs/zero_read_producers.tex"
DEFAULT_TRACE_SUITES = ("google_traces", "spec17", "graph", "ai", "cvp-1", "cvp-1-fix")
SUITE_LABELS = {
    "google_traces": "google",
    "spec17": "spec17",
    "graph": "graph",
    "ai": "ai",
    "cvp-1": "cvp-1",
    "cvp-1-fix": "cvp-1-fix",
}

ZERO_READ_LINE = re.compile(r"^ZERO_READ_PROD category=(\S+) count=(\d+)\s*$")

# Simulator counts GPR lifetimes only; ignore other categories in older logs.
GPR_ONLY = ["gpr"]


def benchmark_from_log(path: Path, log_root: Path | None = None) -> str:
    name = path.name.removesuffix(".log")
    for ext in (".gz", ".xz", ".bz2"):
        if name.endswith(ext):
            name = name[: -len(ext)]
            break
    if ".champsim" in name:
        name = name.split(".champsim", 1)[0]
    if name.endswith(".trace"):
        name = name[: -len(".trace")]
    if log_root is not None and path.parent != log_root:
        name = f"{path.parent.name}/{name}"
    return name


def parse_trace_suites(suites_arg: str) -> tuple[str, ...]:
    allowed = set(DEFAULT_TRACE_SUITES)
    selected: list[str] = []
    for suite in suites_arg.split(","):
        suite = suite.strip()
        if not suite:
            continue
        if suite not in allowed:
            allowed_list = ", ".join(DEFAULT_TRACE_SUITES)
            raise SystemExit(f"error: unknown trace suite '{suite}' (allowed: {allowed_list})")
        selected.append(suite)
    if not selected:
        raise SystemExit("error: no trace suites selected")
    return tuple(dict.fromkeys(selected))


def iter_log_files(log_dir: Path, suites: tuple[str, ...] = DEFAULT_TRACE_SUITES) -> list[Path]:
    logs: list[Path] = []
    for suite in suites:
        suite_dir = log_dir / suite
        if not suite_dir.is_dir():
            print(f"  WARNING: log suite directory not found: {suite_dir}")
            continue
        logs.extend(sorted(suite_dir.glob("*.log")))
    return sorted(logs)


def parse_log(log_file: Path) -> dict[str, float] | None:
    if not log_file.is_file():
        return None

    text = log_file.read_text(errors="replace")
    if "ChampSim completed all CPUs" not in text:
        return None

    counts: dict[str, float] = defaultdict(float)
    for line in text.splitlines():
        match = ZERO_READ_LINE.match(line)
        if match and match.group(1) in GPR_ONLY:
            counts[match.group(1)] += float(match.group(2))

    return dict(counts) if counts else None


def collect_data(log_dir: Path, suites: tuple[str, ...]) -> dict[str, dict[str, float]]:
    if not log_dir.exists():
        print(f"ERROR: log directory not found: {log_dir}")
        return {}

    data: dict[str, dict[str, float]] = {}
    for log_file in iter_log_files(log_dir, suites):
        counts = parse_log(log_file)
        if counts is None:
            print(f"  WARNING: no ZERO_READ_PROD lines in {log_file} (rebuild and re-run ChampSim)")
            continue
        data[benchmark_from_log(log_file, log_dir)] = counts

    return data


def aggregate(raw: dict[str, float], categories: list[str], mapping: dict[str, list[str]]) -> dict[str, float]:
    out = {cat: 0.0 for cat in categories}
    for plot_cat, src_cats in mapping.items():
        out[plot_cat] = sum(raw.get(src, 0.0) for src in src_cats)
    return out


def to_percentages(vals: dict[str, float], categories: list[str]) -> list[float]:
    counts = [vals.get(cat, 0.0) for cat in categories]
    total = sum(counts)
    if total <= 0:
        return [0.0] * len(categories)
    return [100.0 * c / total for c in counts]


def tex_escape(name: str) -> str:
    return name.replace("_", r"\_")


def compute_mean_percentages(plot_data: dict[str, dict[str, float]], categories: list[str]) -> list[float]:
    benchmarks = sorted(plot_data.keys())
    bm_totals = [sum(plot_data[bm].get(cat, 0.0) for cat in categories) for bm in benchmarks]
    grand_total = sum(bm_totals)
    bm_weights = [t / grand_total for t in bm_totals] if grand_total > 0 else [1.0 / len(benchmarks)] * len(benchmarks)
    weighted_cat = [
        sum(bm_weights[j] * plot_data[benchmarks[j]].get(categories[i], 0.0) for j in range(len(benchmarks)))
        for i in range(len(categories))
    ]
    total_wc = sum(weighted_cat)
    return [100.0 * c / total_wc for c in weighted_cat] if total_wc > 0 else [0.0] * len(categories)


def suite_benchmarks(plot_data: dict[str, dict[str, float]], suite: str) -> list[str]:
    prefix = f"{suite}/"
    return sorted(bm for bm in plot_data if bm.startswith(prefix))


def print_mean_row(label: str, means: list[float], header_width: int) -> None:
    print(f"{label:<{header_width}}" + "".join(f"{v:>9.1f}%" for v in means))


def generate_tikz(data: dict[str, dict[str, float]], categories: list[str], category_labels: list[str], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    benchmarks = sorted(data.keys())
    pct_data = {bm: to_percentages(data[bm], categories) for bm in benchmarks}

    mean_pct = compute_mean_percentages(data, categories)

    x_labels = benchmarks + ["Mean"]
    display_labels = [tex_escape(bm) for bm in benchmarks] + [r"\textbf{Mean}"]
    sym_coords = ", ".join(x_labels)
    xticklabels = ", ".join(display_labels)

    colors = [
        ("clrZ0", "352A86"),
        ("clrZ1", "2C92A1"),
        ("clrZ2", "8DCB6E"),
        ("clrZ3", "F6C96B"),
        ("clrZ4", "E8847C"),
        ("clrZ5", "BBBBBB"),
        ("clrZ6", "777777"),
        ("clrZ7", "444444"),
        ("clrZ8", "AA66CC"),
        ("clrZ9", "66AA99"),
        ("clrZ10", "CC8844"),
        ("clrZ11", "8899CC"),
        ("clrZ12", "CC6677"),
        ("clrZ13", "999999"),
    ]
    patterns = [None, "dots", "north east lines", "crosshatch", "grid", "horizontal lines", None, "dots", "north east lines", "crosshatch", "grid", "horizontal lines", None, "dots"]

    define_colors = ""
    for cname, hex_val in colors[: len(categories)]:
        r = int(hex_val[0:2], 16)
        g = int(hex_val[2:4], 16)
        b = int(hex_val[4:6], 16)
        define_colors += f"\\definecolor{{{cname}}}{{RGB}}{{{r},{g},{b}}}\n"

    addplot_lines = []
    for i, cat_label in enumerate(category_labels):
        cname = colors[i][0]
        pat = patterns[i] if i < len(patterns) else None

        coords = [f"({bm}, {pct_data[bm][i]:.4f})" for bm in benchmarks]
        coords.append(f"(Mean, {mean_pct[i]:.4f})")
        coord_body = "\n        ".join(coords)

        postaction = ""
        if pat:
            postaction = f",\n        postaction={{pattern={pat}, pattern color=black!40}}"

        addplot_lines.append(
            f"    \\addplot[\n"
            f"        fill={cname},\n"
            f"        draw=black!60,\n"
            f"        line width=0.3pt{postaction},\n"
            f"    ] coordinates {{\n"
            f"        {coord_body}\n"
            f"    }};\n"
            f"    \\addlegendentry{{{cat_label}}}"
        )

    tex = (
        r"\documentclass[tikz]{standalone}" "\n"
        r"\usepackage{pgfplots}" "\n"
        r"\pgfplotsset{compat=1.18}" "\n"
        r"\usetikzlibrary{patterns}" "\n"
        "\n"
        r"\pgfdeclarelayer{background}" "\n"
        r"\pgfsetlayers{background,main}" "\n"
        "\n"
        + define_colors
        + "\n"
        r"\begin{document}" "\n"
        r"\begin{tikzpicture}" "\n"
        r"\begin{axis}[" "\n"
        r"    ybar stacked," "\n"
        r"    bar width       = 4.5pt," "\n"
        r"    width           = 0.54\linewidth, height = 3cm, scale only axis," "\n"
        r"    enlarge x limits= 0.03," "\n"
        r"    clip            = false," "\n"
        f"    symbolic x coords = {{{sym_coords}}},\n"
        r"    xtick           = data," "\n"
        f"    xticklabels     = {{{xticklabels}}},\n"
        r"    tick align      = outside," "\n"
        r"    x tick label style = {rotate=90, anchor=east, font=\scriptsize}," "\n"
        r"    ymin            = 0," "\n"
        r"    ymax            = 100," "\n"
        r"    ytick           = {0, 20, 40, 60, 80, 100}," "\n"
        r"    yticklabel      = {\pgfmathprintnumber{\tick}\%}," "\n"
        r"    ylabel          = {Fraction of Zero-Read Lifetimes}," "\n"
        r"    ylabel style    = {font=\scriptsize}," "\n"
        r"    ymajorgrids     = true," "\n"
        r"    grid style      = {dashed, gray!30}," "\n"
        r"    legend style    = {at={(0.5,1.05)}, anchor=south, font=\scriptsize, draw=none, legend columns=-1}," "\n"
        r"    after end axis/.code={" "\n"
        r"        \begin{pgfonlayer}{background}" "\n"
        r"            \fill[gray!60] ([xshift=-4.8pt]{axis cs:Mean,\pgfkeysvalueof{/pgfplots/ymin}}) rectangle (rel axis cs:1,1);" "\n"
        r"        \end{pgfonlayer}" "\n"
        r"    }," "\n"
        r"]" "\n"
        "\n"
        + "\n\n".join(addplot_lines)
        + "\n"
        "\n"
        r"\end{axis}" "\n"
        r"\end{tikzpicture}" "\n"
        r"\end{document}" "\n"
    )

    output_path.write_text(tex)
    print(f"Saved {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot GPR zero-read register lifetimes.")
    parser.add_argument("--log-dir", type=Path, default=LOG_DIR)
    parser.add_argument("--output", type=Path, default=OUTPUT_TEX)
    parser.add_argument(
        "--suites",
        default=",".join(DEFAULT_TRACE_SUITES),
        help="Comma-separated log suites under --log-dir (default: google_traces,spec17,graph,ai,cvp-1,cvp-1-fix)",
    )
    args = parser.parse_args()

    suites = parse_trace_suites(args.suites)
    log_dir = args.log_dir.resolve()

    print(f"Collecting zero-read producer counts from {log_dir} (suites: {', '.join(suites)}) ...")
    raw_data = collect_data(log_dir, suites)
    if not raw_data:
        print("No zero-read producer data found. Rebuild bin/champsim and re-run the batch script.")
        return

    categories = GPR_ONLY
    labels = ["GPR"]
    mapping = {"gpr": ["gpr"]}
    plot_data = {bm: aggregate(counts, categories, mapping) for bm, counts in raw_data.items()}

    benchmarks = sorted(plot_data.keys())
    print(f"Found zero-read data for {len(benchmarks)} traces\n")
    header = f"{'Trace':<30}" + "".join(f"{c:>10}" for c in categories)
    print(header)
    print("-" * len(header))
    for bm in benchmarks:
        pct = to_percentages(plot_data[bm], categories)
        row = f"{bm:<30}" + "".join(f"{v:>9.1f}%" for v in pct)
        print(row)

    means = compute_mean_percentages(plot_data, categories)

    print("-" * len(header))
    print_mean_row("Mean (all)", means, 30)
    for suite in suites:
        bms = suite_benchmarks(plot_data, suite)
        if not bms:
            continue
        label = SUITE_LABELS.get(suite, suite)
        subset = {bm: plot_data[bm] for bm in bms}
        print_mean_row(f"Mean ({label}, n={len(bms)})", compute_mean_percentages(subset, categories), 30)

    generate_tikz(plot_data, categories, labels, args.output.resolve())


if __name__ == "__main__":
    main()
