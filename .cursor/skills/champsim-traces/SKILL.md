---
name: champsim-traces
description: >-
  Documents ChampSim trace directory layout: Google production traces
  (traces/google_traces/) and SPEC CPU 2017 traces (traces/spec17/). Covers
  naming conventions, compression formats, zip archives, discovery/extraction
  patterns, and script variables. Use when writing or updating batch run
  scripts, plotting pipelines, trace lists, or any workflow that references
  traces/, benchmark suites, Google traces, or SPEC17.
---

# ChampSim trace organization

## Layout

```
traces/
├── google_traces/     # Google production workloads (43 traces)
└── spec17/            # SPEC CPU 2017 (20 traces in 5 zip archives)
```

**Root:** `${CHAMPSIM_ROOT}/traces` where `CHAMPSIM_ROOT` is the repo root.

Traces live in **suite subdirectories**, not flat under `traces/`. Older scripts
that set `TRACE_DIR="${CHAMPSIM_ROOT}/traces"` need updating to pick a suite
(or accept a `TRACE_SUITE` variable).

## Suite comparison

| | Google | SPEC17 |
|---|--------|--------|
| **Path** | `traces/google_traces/` | `traces/spec17/` |
| **Source** | Google Traces v2 (production) | DPC-3 SPEC CPU 2017 |
| **Count** | 43 | 20 |
| **Extension** | `.champsim[.-NNN].gz` | `.champsimtrace.xz` |
| **Compression** | gzip | xz |
| **On disk** | Mostly extracted `.gz` | Only `.zip` archives (extract first) |
| **Grouping** | 9 codename workloads | 10 SPEC benchmarks (some with multiple simpoints) |

## Google traces (`traces/google_traces/`)

### Naming

```
{workload}_{index}.champsim[.-{suffix}].gz
```

Examples:

- `tango_0000.champsim-005.gz`
- `charlie_0001.champsim.gz` (no numeric suffix before `.gz`)

The optional `-NNN` suffix is part of the filename, not a separate extension.

### Workloads (9 codenames, 43 traces total)

| Workload | Traces | Indices |
|----------|--------|---------|
| `arizona` | 3 | 0000–0002 |
| `charlie` | 5 | 0000–0004 |
| `merced` | 5 | 0000–0004 |
| `sierra.a.3` | 5 | 0000–0004 |
| `sierra.a.4` | 5 | 0000–0004 |
| `sierra.a.6` | 5 | 0000–0004 |
| `tahoe` | 5 | 0000–0004 |
| `tango` | 5 | 0000–0004 |
| `yankee` | 5 | 0000–0004 |

### Zip archives

Three leftover download zips may still be present (traces already extracted):

- `Google Traces v2-20260611T132354Z-3-003.zip` → `arizona_0000.champsim.gz`
- `Google Traces v2-20260611T132354Z-3-023.zip` → `charlie_0004.champsim.gz`
- `Google Traces v2-20260611T132354Z-3-025.zip` → `charlie_0001.champsim.gz`

Zip members use paths like `Google Traces v2/charlie/charlie_0001.champsim.gz`.
Extract with `unzip -j` (flatten) into `google_traces/`.

### Uncompressed sibling rule

`sierra.a.6_0004.champsim-041` (~83 GB) may exist alongside
`sierra.a.6_0004.champsim-041.gz`. **Always prefer the compressed file** when both
exist.

## SPEC17 traces (`traces/spec17/`)

### Naming (DPC-3 convention)

```
{specnum}.{benchmark}_s-{simpoint}B.champsimtrace.xz
```

Examples:

- `605.mcf_s-484B.champsimtrace.xz`
- `602.gcc_s-1850B.champsimtrace.xz`

The `{simpoint}` field is a byte-size hint from the trace packager, not a ChampSim
instruction count.

### Benchmarks (10 workloads, 20 simpoints)

| Benchmark | Simpoints |
|-----------|-----------|
| `602.gcc_s` | 734B, 1850B |
| `603.bwaves_s` | 891B, 1740B |
| `605.mcf_s` | 472B, 484B, 1536B, 1554B, 1644B |
| `607.cactuBSSN_s` | 2421B |
| `619.lbm_s` | 2676B, 2677B |
| `620.omnetpp_s` | 874B |
| `621.wrf_s` | 6673B |
| `623.xalancbmk_s` | 10B |
| `649.fotonik3d_s` | 1176B, 7084B |
| `654.roms_s` | 293B, 294B, 523B |

### Zip archives

Five download zips, 4 traces each:

```
drive-download-20260613T114942Z-3-001.zip
drive-download-20260613T114942Z-3-002.zip
drive-download-20260613T114942Z-3-003.zip
drive-download-20260613T114942Z-3-004.zip
drive-download-20260613T114942Z-3-005.zip
```

Members are flat `.champsimtrace.xz` names (no subdirectory). Extract into
`spec17/` with `unzip -j`.

Full per-file listing: [reference.md](reference.md).

## Script conventions

### Environment variables

Use these in new batch/plot scripts:

```bash
CHAMPSIM_ROOT=$(cd "${SCRIPT_DIR}/../../../../" && pwd)   # from runs/scripts/micro26/<exp>/
TRACE_SUITE="${TRACE_SUITE:-google_traces}"                # or spec17
TRACE_DIR="${CHAMPSIM_ROOT}/traces/${TRACE_SUITE}"
```

To run one suite explicitly:

```bash
TRACE_SUITE=google_traces ./run_all.sh
TRACE_SUITE=spec17       ./run_all.sh
```

### Discover traces

```bash
discover_traces() {
  shopt -s nullglob
  local -a traces=() f
  for f in "${TRACE_DIR}"/*; do
    [[ -f "${f}" ]] || continue
    case "${f}" in
      *.zip|*.sha256*|*.part*) continue ;;
      *.gz|*.xz|*.bz2) traces+=("${f}") ;;
      *.champsim|*.champsim-*|*.champsimtrace|*.champsimtrace.*)
        [[ -f "${f}.gz" || -f "${f}.xz" || -f "${f}.bz2" ]] && continue
        traces+=("${f}")
        ;;
    esac
  done
  ((${#traces[@]})) || { echo "no traces in ${TRACE_DIR}" >&2; return 1; }
  printf '%s\n' "${traces[@]}" | sort -u
}
```

### Extract zip archives in a suite directory

```bash
extract_zip_traces() {
  shopt -s nullglob
  local zip member base dest
  for zip in "${TRACE_DIR}"/*.zip; do
    while IFS= read -r member; do
      [[ -n "${member}" ]] || continue
      base=$(basename "${member}")
      dest="${TRACE_DIR}/${base}"
      [[ -f "${dest}" ]] && { echo "[extract] skip ${base}"; continue; }
      echo "[extract] ${base} from $(basename "${zip}")"
      unzip -j -o "${zip}" "${member}" -d "${TRACE_DIR}" >/dev/null
    done < <(unzip -Z1 "${zip}" | grep -E '\.(gz|xz|bz2)$' || true)
  done
}
```

Call `extract_zip_traces` before `discover_traces`. SPEC17 **requires** extraction;
Google mostly works without it.

### Parse workload names from paths

**Google** — strip index and extensions:

```bash
# tango_0000.champsim-005.gz → tango
basename="${trace##*/}"
workload="${basename%%_*}"
```

**SPEC17** — extract benchmark id:

```bash
# 605.mcf_s-484B.champsimtrace.xz → 605.mcf_s
basename="${trace##*/}"
benchmark="${basename%.champsimtrace.*}"
benchmark="${benchmark%-*}"    # drop simpoint suffix
```

### Run a single trace

```bash
bin/champsim --warmup-instructions 0 --simulation-instructions 100000000 \
  --hide-heartbeat traces/google_traces/tango_0000.champsim-005.gz

bin/champsim --warmup-instructions 200000000 --simulation-instructions 500000000 \
  --hide-heartbeat traces/spec17/605.mcf_s-484B.champsimtrace.xz
```

Pass `--warmup-instructions 0` explicitly when no warmup is desired (ChampSim
defaults warmup to 20% of sim if omitted).

### Log/output naming

Use the trace **basename** (includes compression suffix) for log filenames:

```
runs/output/micro26/<experiment>/cs_logs/tango_0000.champsim-005.gz.log
runs/output/micro26/<experiment>/cs_logs/605.mcf_s-484B.champsimtrace.xz.log
```

## Choosing a suite in new experiments

| Goal | Suite |
|------|-------|
| Production/datacenter-style workloads | `google_traces` |
| Standard SPEC CPU 2017 comparison / DPC-3 baselines | `spec17` |
| Both | Loop over suites or accept `TRACE_SUITE` / `--suite` flag |

When plotting across a suite, group by **workload** (Google codename or SPEC
benchmark id), not by individual simpoint index.

## Related skills

- **champsim-silverblue-build** — build/run inside toolbox when host lacks `g++`
- **champsim-register-read-histogram** — example experiment using Google traces
  (note: its `run_all.sh` still points at flat `traces/`; update to use this skill)

## Agent checklist

When writing trace batch scripts:

- [ ] Set `TRACE_DIR` to `traces/google_traces/` or `traces/spec17/`, not flat `traces/`
- [ ] Support `TRACE_SUITE` override for reuse across suites
- [ ] Call zip extraction before discovery (required for SPEC17)
- [ ] Skip uncompressed trace when compressed sibling exists
- [ ] Skip `*.zip`, `*.sha256*`, and incomplete `*.part*` downloads
- [ ] Use trace basename for log/output filenames
- [ ] Pass explicit `--warmup-instructions` on the CLI
