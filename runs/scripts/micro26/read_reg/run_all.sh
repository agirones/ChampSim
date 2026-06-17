#!/usr/bin/env bash
#
# Run ChampSim on traces under traces/{google_traces,spec17,graph,ai,cvp-1,cvp-1-fix}
# with 0 warmup and 50M simulation instructions by default. Traces packed in
# *.zip or *.tar archives are extracted first. Individual runs are launched in parallel.
#
# Usage:
#   ./run_all.sh                              # google_traces + spec17 (default)
#   TRACE_SUITES=cvp-1 ./run_all.sh
#   TRACE_SUITES=cvp-1-fix ./run_all.sh
#   TRACE_SUITES=ai ./run_all.sh
#   TRACE_SUITES=graph ./run_all.sh
#   TRACE_SUITES=google_traces ./run_all.sh
#   TRACE_SUITES=spec17 ./run_all.sh
#   TRACE_SUITES=google_traces,spec17,graph,ai,cvp-1,cvp-1-fix JOBS=8 ./run_all.sh
#   CHAMPSIM_TOOLBOX=champsim-dev ./run_all.sh
#
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CHAMPSIM_ROOT=$(cd "${SCRIPT_DIR}/../../../../" && pwd)
TRACES_ROOT="${CHAMPSIM_ROOT}/traces"
RESULTS_DIR="${CHAMPSIM_ROOT}/runs/output/micro26/read_reg/cs_logs"
CHAMPSIM_BIN="${CHAMPSIM_BIN:-${CHAMPSIM_ROOT}/bin/champsim}"

WARMUP="${WARMUP:-0}"
SIM="${SIM:-50000000}"
JOBS="${JOBS:-$(nproc)}"
TRACE_SUITES="${TRACE_SUITES:-google_traces,spec17}"

# Use toolbox when the host has no C++ toolchain but champsim-dev is available.
if [[ -z "${CHAMPSIM_TOOLBOX:-}" ]] && ! command -v g++ >/dev/null 2>&1; then
  if command -v toolbox >/dev/null 2>&1 && toolbox list 2>/dev/null | grep -q 'champsim-dev'; then
    CHAMPSIM_TOOLBOX=champsim-dev
  fi
fi

usage() {
  cat <<EOF
Usage: $(basename "$0")

Environment variables:
  TRACE_SUITES   Comma-separated trace suites to run (default: google_traces,spec17)
                 Allowed values: google_traces, spec17, graph, ai, cvp-1, cvp-1-fix
  WARMUP         Warmup instructions (default: 0)
  SIM            Simulation instructions (default: 100000000)
  JOBS           Parallel jobs (default: nproc)
  CHAMPSIM_BIN   Path to simulator binary (default: bin/champsim)
  FORCE          Re-run even if a complete GPR log exists (default: 0)

Logs are written to:
  ${RESULTS_DIR}/<suite>/<trace-basename>.log
EOF
}

parse_trace_suites() {
  local -a selected=()
  local suite

  IFS=',' read -r -a requested <<<"${TRACE_SUITES}"
  for suite in "${requested[@]}"; do
    suite="${suite// /}"
    [[ -n "${suite}" ]] || continue
    case "${suite}" in
      google_traces|spec17|graph|ai|cvp-1|cvp-1-fix) selected+=("${suite}") ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        echo "error: unknown trace suite '${suite}' (allowed: google_traces, spec17, graph, ai, cvp-1, cvp-1-fix)" >&2
        exit 1
        ;;
    esac
  done

  if ((${#selected[@]} == 0)); then
    echo "error: TRACE_SUITES is empty" >&2
    exit 1
  fi

  printf '%s\n' "${selected[@]}" | sort -u
}

trace_dir_for_suite() {
  echo "${TRACES_ROOT}/$1"
}

extract_zip_traces() {
  local trace_dir=$1
  shopt -s nullglob
  local zip member base dest
  [[ -d "${trace_dir}" ]] || return 0

  for zip in "${trace_dir}"/*.zip; do
    while IFS= read -r member; do
      [[ -n "${member}" ]] || continue
      base=$(basename "${member}")
      dest="${trace_dir}/${base}"
      if [[ -f "${dest}" ]]; then
        echo "[extract:${trace_dir##*/}] skip ${base} (already present)"
        continue
      fi
      echo "[extract:${trace_dir##*/}] ${base} from $(basename "${zip}")"
      unzip -j -o "${zip}" "${member}" -d "${trace_dir}" >/dev/null
    done < <(unzip -Z1 "${zip}" | grep -E '\.(gz|xz|bz2)$' || true)
  done
}

extract_tar_traces() {
  local trace_dir=$1
  shopt -s nullglob
  local archive member base dest
  [[ -d "${trace_dir}" ]] || return 0

  for archive in "${trace_dir}"/*.tar "${trace_dir}"/*.tar.gz "${trace_dir}"/*.tgz; do
    [[ -f "${archive}" ]] || continue
    [[ -s "${archive}" ]] || continue
    while IFS= read -r member; do
      [[ -n "${member}" ]] || continue
      base=$(basename "${member}")
      dest="${trace_dir}/${base}"
      if [[ -f "${dest}" ]]; then
        echo "[extract:${trace_dir##*/}] skip ${base} (already present)"
        continue
      fi
      echo "[extract:${trace_dir##*/}] ${base} from $(basename "${archive}")"
      tar -xf "${archive}" -C "${trace_dir}" --strip-components=1 --no-same-owner "${member}"
    done < <(tar -tf "${archive}" | grep -E '\.(gz|xz|bz2)$' || true)
  done
}

discover_traces() {
  local trace_dir=$1
  shopt -s nullglob
  local -a traces=()
  local f

  [[ -d "${trace_dir}" ]] || return 0

  for f in "${trace_dir}"/*; do
    [[ -f "${f}" ]] || continue
    case "${f}" in
      *.zip|*.sha256*|*.tar|*.tar.gz|*.tgz) continue ;;
      *.gz|*.xz|*.bz2) traces+=("${f}") ;;
      *.champsim|*.champsim-*|*.champsimtrace|*.champsimtrace.*)
        if [[ -f "${f}.gz" || -f "${f}.xz" || -f "${f}.bz2" ]]; then
          continue
        fi
        traces+=("${f}")
        ;;
    esac
  done

  printf '%s\n' "${traces[@]}" | sort -u
}

run_champsim() {
  local suite=$1
  local trace=$2
  local name log suite_log_dir
  name=$(basename "${trace}")
  suite_log_dir="${RESULTS_DIR}/${suite}"
  log="${suite_log_dir}/${name}.log"

  mkdir -p "${suite_log_dir}"

  if [[ -f "${log}" ]] && grep -q 'ChampSim completed all CPUs' "${log}" && grep -q 'GPR lifetimes only' "${log}" && [[ "${FORCE:-0}" != "1" ]]; then
    echo "[skip:${suite}] ${name} (already complete)"
    return 0
  fi

  echo "[run:${suite}]  ${name} -> ${log}"
  if [[ -n "${CHAMPSIM_TOOLBOX:-}" ]]; then
    toolbox run -c "${CHAMPSIM_TOOLBOX}" bash -lc \
      "cd '${CHAMPSIM_ROOT}' && '${CHAMPSIM_BIN}' --warmup-instructions ${WARMUP} --simulation-instructions ${SIM} --hide-heartbeat '${trace}'" \
      >"${log}" 2>&1
  else
    "${CHAMPSIM_BIN}" --warmup-instructions "${WARMUP}" --simulation-instructions "${SIM}" --hide-heartbeat "${trace}" \
      >"${log}" 2>&1
  fi
}

export -f run_champsim extract_zip_traces extract_tar_traces discover_traces
export CHAMPSIM_ROOT CHAMPSIM_BIN CHAMPSIM_TOOLBOX RESULTS_DIR WARMUP SIM TRACES_ROOT

main() {
  if [[ ! -x "${CHAMPSIM_BIN}" && -z "${CHAMPSIM_TOOLBOX:-}" ]]; then
    echo "error: ${CHAMPSIM_BIN} not found or not executable (set CHAMPSIM_TOOLBOX to run inside toolbox)" >&2
    exit 1
  fi

  mapfile -t suites < <(parse_trace_suites)

  echo "ChampSim root:  ${CHAMPSIM_ROOT}"
  echo "Traces root:    ${TRACES_ROOT}"
  echo "Trace suites:   ${suites[*]}"
  echo "Results dir:    ${RESULTS_DIR}"
  echo "Warmup:         ${WARMUP}"
  echo "Simulation:     ${SIM}"
  echo "Parallel jobs:  ${JOBS}"
  [[ -n "${CHAMPSIM_TOOLBOX:-}" ]] && echo "Toolbox:        ${CHAMPSIM_TOOLBOX}"
  echo

  local -a traces=()
  local -a trace_suites=()
  local suite trace_dir

  for suite in "${suites[@]}"; do
    trace_dir=$(trace_dir_for_suite "${suite}")
    if [[ ! -d "${trace_dir}" ]]; then
      echo "warning: trace directory not found: ${trace_dir}" >&2
      continue
    fi

    extract_zip_traces "${trace_dir}"
    extract_tar_traces "${trace_dir}"

    while IFS= read -r trace; do
      [[ -n "${trace}" ]] || continue
      traces+=("${trace}")
      trace_suites+=("${suite}")
    done < <(discover_traces "${trace_dir}")
  done

  echo

  if ((${#traces[@]} == 0)); then
    echo "error: no traces found for suites: ${suites[*]}" >&2
    exit 1
  fi

  echo "Found ${#traces[@]} traces"
  for suite in "${suites[@]}"; do
    count=0
    for s in "${trace_suites[@]}"; do
      [[ "${s}" == "${suite}" ]] && ((count++)) || true
    done
    echo "  ${suite}: ${count}"
  done
  echo

  if command -v parallel >/dev/null 2>&1; then
    parallel --jobs "${JOBS}" --halt soon,fail=1 run_champsim {1} {2} ::: "${trace_suites[@]}" :::+ "${traces[@]}"
  else
    local i
    for i in "${!traces[@]}"; do
      run_champsim "${trace_suites[$i]}" "${traces[$i]}" &
      while (($(jobs -rp | wc -l) >= JOBS)); do
        wait -n
      done
    done
    wait
  fi

  echo
  echo "All runs finished. Logs are in ${RESULTS_DIR}/<suite>/"
  echo "Histogram lines:"
  grep -h 'Register reads before overwrite histogram' "${RESULTS_DIR}"/*/*.log 2>/dev/null || true
}

main "$@"
