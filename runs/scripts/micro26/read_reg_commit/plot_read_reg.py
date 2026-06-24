#!/usr/bin/env python3
"""
Generates a standalone PGF/TikZ (pgfplots) stacked bar chart showing, per trace,
the distribution (in %) of register lifetimes by reads before overwrite: 0, 1, 2,
or 3-or-more.

Uses logs from the commit-time register-read counter (read_reg_commit branch):
reads are counted when consuming instructions commit, not at rename.

Data source
-----------
ChampSim stdout captured in run logs, e.g.:

  CPU 0 Register reads before overwrite histogram (GPR lifetimes only, total: N)
    0 reads: ...
    1 read:  ...
    2 reads: ...
    3+ reads: ...

Read from: runs/output/micro26/read_reg_commit/cs_logs/*.log

The rightmost bar is the count-weighted mean across all traces.

Output: runs/output/micro26/read_reg_commit/graphs/read_reg.tex
"""

import argparse
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]  # .../ChampSim/
LOG_DIR = ROOT / "runs/output/micro26/read_reg_commit/cs_logs"
OUTPUT_TEX = ROOT / "runs/output/micro26/read_reg_commit/graphs/read_reg.tex"

CATEGORY_KEYS = ["0", "1", "2", "3_or_more"]
CATEGORY_LABELS = ["0", "1", "2", r"3 or more"]

LINE_PATTERNS = {
    "0": re.compile(r"^\s*0 reads:\s*(\d+)\s*$"),
    "1": re.compile(r"^\s*1 read:\s*(\d+)\s*$"),
    "2": re.compile(r"^\s*2 reads:\s*(\d+)\s*$"),
    "3_or_more": re.compile(r"^\s*3\+ reads:\s*(\d+)\s*$"),
}

HEADER = "Register reads before overwrite histogram"


def benchmark_from_log(path: Path, log_root: Path | None = None) -> str:
    name = path.name.removesuffix(".log")
    for ext in (".gz", ".xz", ".bz2"):
        if name.endswith(ext):
            name = name[: -len(ext)]
            break
    if ".champsim" in name:
        name = name.split(".champsim", 1)[0]
    if log_root is not None and path.parent != log_root:
        name = f"{path.parent.name}/{name}"
    return name


def iter_log_files(log_dir: Path) -> list[Path]:
    logs = sorted(log_dir.glob("**/*.log"))
    if logs:
        return logs
    return sorted(log_dir.glob("*.log"))


def parse_log(log_file: Path) -> dict[str, float] | None:
    if not log_file.is_file():
        return None

    text = log_file.read_text(errors="replace")
    if "ChampSim completed all CPUs" not in text:
        return None
    if "GPR lifetimes only" not in text:
        return None

    lines = text.splitlines()
    header_idx = next((i for i, line in enumerate(lines) if HEADER in line), None)
    if header_idx is None:
        return None

    counts: dict[str, float] = {}
    for key, pattern in LINE_PATTERNS.items():
        for line in lines[header_idx + 1 : header_idx + 8]:
            match = pattern.match(line)
            if match:
                counts[key] = float(match.group(1))
                break

    if len(counts) != len(CATEGORY_KEYS):
        return None
    return counts


def collect_data(log_dir: Path, debug_bm: str = "") -> dict[str, dict[str, float]]:
    if not log_dir.exists():
        print(f"ERROR: log directory not found: {log_dir}")
        return {}

    log_files = iter_log_files(log_dir)
    if not log_files:
        print(f"WARNING: no .log files found under {log_dir}")
        return {}

    data: dict[str, dict[str, float]] = {}
    for log_file in log_files:
        benchmark = benchmark_from_log(log_file, log_dir)
        counts = parse_log(log_file)
        if counts is None:
            print(f"  WARNING: no histogram in {log_file.name}")
            continue

        if debug_bm and benchmark == debug_bm:
            total = sum(counts.values())
            print(f"  log      : {log_file.name}")
            print(f"  raw counts : " + "  ".join(f"{k}={counts[k]:.0f}" for k in CATEGORY_KEYS))
            print(f"  raw total  : {total:.0f}")
            if total > 0:
                print("  raw pct    : " + "  ".join(f"{k}={100 * counts[k] / total:.2f}%" for k in CATEGORY_KEYS))
            print()

        data[benchmark] = counts

    return data


def to_percentages(vals: dict[str, float]) -> list[float]:
    counts = [vals.get(k, 0.0) for k in CATEGORY_KEYS]
    total = sum(counts)
    if total <= 0:
        return [0.0] * len(CATEGORY_KEYS)
    return [100.0 * c / total for c in counts]


def compute_mean_percentages(plot_data: dict[str, dict[str, float]], benchmarks: list[str] | None = None) -> list[float]:
    if benchmarks is None:
        benchmarks = sorted(plot_data.keys())
    if not benchmarks:
        return [0.0] * len(CATEGORY_KEYS)

    bm_totals = [sum(plot_data[bm].get(k, 0.0) for k in CATEGORY_KEYS) for bm in benchmarks]
    grand_total = sum(bm_totals)
    bm_weights = [t / grand_total for t in bm_totals] if grand_total > 0 else [1.0 / len(benchmarks)] * len(benchmarks)
    weighted_cat = [
        sum(bm_weights[j] * plot_data[benchmarks[j]].get(CATEGORY_KEYS[i], 0.0) for j in range(len(benchmarks)))
        for i in range(len(CATEGORY_KEYS))
    ]
    total_wc = sum(weighted_cat)
    return [100.0 * c / total_wc for c in weighted_cat] if total_wc > 0 else [0.0] * len(CATEGORY_KEYS)


def suite_benchmarks(plot_data: dict[str, dict[str, float]], suite: str) -> list[str]:
    prefix = f"{suite}/"
    return sorted(bm for bm in plot_data if bm.startswith(prefix))


def print_mean_row(label: str, means: list[float], header_width: int) -> None:
    print(f"{label:<{header_width}}" + "".join(f"{v:>11.2f}%" for v in means))


def tex_escape(name: str) -> str:
    return name.replace("_", r"\_")


def generate_tikz(data: dict[str, dict[str, float]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    benchmarks = sorted(data.keys())

    pct_data = {bm: to_percentages(data[bm]) for bm in benchmarks}

    mean_pct = compute_mean_percentages(data, benchmarks)

    x_labels = benchmarks + ["Mean"]
    display_labels = [tex_escape(bm) for bm in benchmarks] + [r"\textbf{Mean}"]
    sym_coords = ", ".join(x_labels)
    xticklabels = ", ".join(display_labels)

    colors = [
        ("clrDep0", "352A86"),
        ("clrDep1", "2C92A1"),
        ("clrDep2", "8DCB6E"),
        ("clrDep3", "F6C96B"),
    ]
    patterns = [
        None,
        "dots",
        "north east lines",
        "crosshatch",
    ]
    pattern_colors = [
        None,
        "black!40",
        "black!40",
        "white!30",
    ]

    define_colors = ""
    for cname, hex_val in colors:
        r = int(hex_val[0:2], 16)
        g = int(hex_val[2:4], 16)
        b = int(hex_val[4:6], 16)
        define_colors += f"\\definecolor{{{cname}}}{{RGB}}{{{r},{g},{b}}}\n"

    addplot_lines = []
    for i, cat_label in enumerate(CATEGORY_LABELS):
        cname = colors[i][0]
        pat = patterns[i]
        patcol = pattern_colors[i]

        coords = []
        for bm in benchmarks:
            coords.append(f"({bm}, {pct_data[bm][i]:.4f})")
        coords.append(f"(Mean, {mean_pct[i]:.4f})")
        coord_body = "\n        ".join(coords)

        postaction = ""
        if pat:
            postaction = f",\n        postaction={{pattern={pat}, pattern color={patcol}}}"

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

    addplot_str = "\n\n".join(addplot_lines)

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
        r"\pgfplotsset{" "\n"
        r"    legend image code/.code={" "\n"
        r"        \draw[#1, draw=black!60, line width=0.3pt]" "\n"
        r"            (0pt,-1pt) rectangle (5pt,4pt);" "\n"
        r"    }," "\n"
        r"}" "\n"
        "\n"
        r"\begin{document}" "\n"
        r"\begin{tikzpicture}" "\n"
        r"\begin{axis}[" "\n"
        r"    ybar stacked," "\n"
        r"    bar width       = 3pt," "\n"
        r"    width           = 0.75\linewidth, height = 3cm, scale only axis," "\n"
        r"    enlarge x limits= 0.15," "\n"
        r"    clip            = false," "\n"
        f"    symbolic x coords = {{{sym_coords}}},\n"
        r"    xtick           = data," "\n"
        f"    xticklabels     = {{{xticklabels}}},\n"
        r"    tick align      = outside," "\n"
        r"    minor tick length = 3pt," "\n"
        r"    x tick label style = {rotate=90, anchor=east, font=\scriptsize}," "\n"
        r"    ymin            = 0," "\n"
        r"    ymax            = 100," "\n"
        r"    ytick           = {0, 20, 40, 60, 80, 100}," "\n"
        r"    yticklabel      = {\pgfmathprintnumber{\tick}\%}," "\n"
        r"    ylabel          = {Register reads between overwrites (commit)}," "\n"
        r"    ylabel style    = {font=\scriptsize}," "\n"
        r"    ymajorgrids     = true," "\n"
        r"    grid style      = {dashed, gray!30}," "\n"
        r"    axis line style = {gray!60}," "\n"
        r"    tick style      = {gray!60}," "\n"
        r"    legend style    = {" "\n"
        r"        at={(0.5,1.05)}, anchor=south," "\n"
        r"        font=\scriptsize," "\n"
        r"        cells={anchor=west}," "\n"
        r"        draw=none," "\n"
        r"        /tikz/every even column/.append style={column sep=6pt}," "\n"
        r"    }," "\n"
        r"    legend columns  = -1," "\n"
        r"    tick label style= {font=\scriptsize}," "\n"
        r"    after end axis/.code={" "\n"
        r"        \begin{pgfonlayer}{background}" "\n"
        r"            \fill[gray!60] ([xshift=-3pt]{axis cs:Mean,\pgfkeysvalueof{/pgfplots/ymin}}) rectangle (rel axis cs:1,1);" "\n"
        r"        \end{pgfonlayer}" "\n"
        r"    }," "\n"
        r"]" "\n"
        "\n"
        + addplot_str
        + "\n"
        "\n"
        r"\end{axis}" "\n"
        r"\end{tikzpicture}" "\n"
        r"\end{document}" "\n"
    )

    output_path.write_text(tex)
    print(f"Saved {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot commit-time register reads before overwrite distribution.")
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=LOG_DIR,
        help="Directory containing ChampSim *.log files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_TEX,
        help="Output .tex file path",
    )
    parser.add_argument(
        "--debug",
        metavar="TRACE",
        default="",
        help="Print parsed counts for this trace (e.g. tango_0000)",
    )
    args = parser.parse_args()

    log_dir = args.log_dir.resolve()
    output_tex = args.output.resolve()

    print(f"Collecting commit-time register-read histograms from {log_dir} ...")
    if args.debug:
        print(f"DEBUG mode: showing all numbers for '{args.debug}'\n")
    data = collect_data(log_dir, debug_bm=args.debug)
    if not data:
        print("No data found – nothing to plot.")
        return

    benchmarks = sorted(data.keys())
    print(f"\nFound {len(benchmarks)} traces:")
    header = f"{'Trace':<30}" + "".join(f"{c:>12}" for c in ["0 (%)", "1 (%)", "2 (%)", "3+ (%)"])
    print(header)
    print("-" * len(header))
    for bm in benchmarks:
        pct = to_percentages(data[bm])
        row = f"{bm:<30}" + "".join(f"{v:>11.2f}%" for v in pct)
        print(row)

    google_bms = suite_benchmarks(data, "google_traces")
    spec_bms = suite_benchmarks(data, "spec17")

    means = compute_mean_percentages(data, benchmarks)
    google_means = compute_mean_percentages(data, google_bms)
    spec_means = compute_mean_percentages(data, spec_bms)

    print("-" * len(header))
    print_mean_row("Mean (all)", means, 30)
    if google_bms:
        print_mean_row(f"Mean (google, n={len(google_bms)})", google_means, 30)
    if spec_bms:
        print_mean_row(f"Mean (spec17, n={len(spec_bms)})", spec_means, 30)

    generate_tikz(data, output_tex)


if __name__ == "__main__":
    main()
