---
name: champsim-register-read-histogram
description: >-
  Implements and runs ChampSim register-read-before-overwrite histograms (buckets
  0/1/2/3+). Covers RegisterAllocator counting hooks, O3_CPU phase printing,
  micro26 batch runs, trace discovery, and Silverblue toolbox execution. Use when
  the user asks about register read counts, register lifetime histograms, read_reg
  experiments, or running all Google traces in parallel.
---

# ChampSim register-read-before-overwrite histogram

## What this measures

Count **how many times a physical register is read before its value is superseded**
by the next write to the same architectural register.

- One **lifetime** = one physical register from allocation (write/rename) until the
  old physical register is freed at **retire** when a newer write commits.
- Each **read** = one `rename_src_register()` call during scheduling.
- Histogram buckets: **0, 1, 2, 3+** reads per completed lifetime.

This uses **register renaming semantics** (correct for OoO). Do not count at execute
time — ChampSim has no explicit register-file read at execution.

Registers still live at simulation end are **not** bucketed (only completed lifetimes
on overwrite).

## Where counting lives

| Event | File | Function |
|-------|------|----------|
| Read (+1) | `src/register_allocator.cc` | `rename_src_register()` |
| New lifetime (count=0) | `src/register_allocator.cc` | `rename_dest_register()` |
| Bucket old lifetime | `src/register_allocator.cc` | `retire_dest_register()` → `record_lifetime_reads()` |
| Rename invoked | `src/ooo_cpu.cc` | `do_scheduling()` |
| Retire invoked | `src/ooo_cpu.cc` | `retire_rob()` |

Trace operands are **logical** IDs in `inc/trace_instruction.h` (`source_registers`,
`destination_registers`). Renaming happens in `do_scheduling()`, not at fetch/decode.

## Implementation (already in tree)

### `inc/register_allocator.h`

- `read_counts` — per-physical-register counter (`std::vector<uint32_t>`)
- `read_before_overwrite_histogram` — 4 buckets (`std::array<uint64_t, 4>`)
- `record_lifetime_reads()`, `reset_register_lifetime_histogram()`,
  `print_register_lifetime_histogram()`

### `src/register_allocator.cc`

```cpp
// rename_dest_register: read_counts[phys_reg] = 0
// rename_src_register:   ++read_counts[phys] (existing mapping only)
// retire_dest_register: record_lifetime_reads(read_counts[old_phys_reg]) before free_register()
// record_lifetime_reads: bucket = min(reads, 3) where 3 means "3+"
```

Cold-start path in `rename_src_register()` (arch reg not yet mapped) allocates a
physical reg and sets count to 0 — does not increment (not a true read of a prior value).

### `src/ooo_cpu.cc`

- `begin_phase()`: `reg_allocator.reset_register_lifetime_histogram()` when `!warmup`
- `end_phase()`: print histogram when `!warmup && finished_cpu == this->cpu`

### Output format

```
CPU 0 Register reads before overwrite histogram (total lifetimes: N)
  0 reads: ...
  1 read:  ...
  2 reads: ...
  3+ reads: ...
```

Printed at ROI phase end (stdout and captured in run logs).

## Warmup and CLI caveats

**Warmup clears register operands** in `do_init_instruction()` — no rename during
warmup, so histogram stays empty until simulation phase.

**Always pass `--warmup-instructions 0` explicitly** when no warmup is desired.
If only `--simulation-instructions` is given, ChampSim defaults warmup to 20% of sim.

```bash
bin/champsim --warmup-instructions 0 --simulation-instructions 100000000 --hide-heartbeat traces/foo.champsim-005.gz
```

Other caveats:

- **Stack pointer folding** (`do_stack_pointer_folding()` in `ooo_cpu.cc`) may remove
  SP from destination registers — some SP writes won't start a new lifetime.
- **Special registers** (IP, flags, SP) are handled specially in `inc/instruction.h`.
- Total lifetimes > retired instructions because many instructions write multiple regs.

## Batch run script

**Script:** `runs/scripts/micro26/read_reg/run_all.sh`  
**Logs:** `runs/output/micro26/read_reg/cs_logs/<trace-basename>.log`

Defaults: `WARMUP=0`, `SIM=100000000`, `JOBS=$(nproc)`.

```bash
cd /path/to/ChampSim
./runs/scripts/micro26/read_reg/run_all.sh

# Tune parallelism / instructions
JOBS=8 SIM=50000000 ./runs/scripts/micro26/read_reg/run_all.sh
```

Environment variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `JOBS` | `nproc` | Parallel trace runs |
| `WARMUP` | `0` | Warmup instructions |
| `SIM` | `100000000` | Simulation instructions |
| `CHAMPSIM_BIN` | `bin/champsim` | Simulator binary |
| `CHAMPSIM_TOOLBOX` | auto | Run inside toolbox if host has no `g++` |

Script behavior:

1. Resolves `CHAMPSIM_ROOT` four levels up from script dir
2. Extracts missing traces from `traces/*.zip` (`unzip -j`)
3. Discovers traces: `*.gz`, `*.xz`, `*.bz2`, uncompressed `*.champsim*`
4. Skips uncompressed trace if compressed sibling exists (e.g. skip 83GB
   `sierra.a.6_0004.champsim-041` when `.gz` exists)
5. Skips runs whose log already contains `ChampSim completed all CPUs`
6. Runs in parallel via GNU `parallel` or `xargs -P`
7. Greps histogram summary lines at end

### Trace inventory

Google trace zips in `traces/` may contain traces not yet extracted:

- `arizona_0000.champsim.gz`
- `charlie_0001.champsim.gz`
- `charlie_0004.champsim.gz`

Expect ~43 traces after extraction (~40 `.gz` already present + 3 from zips).

## Build and run on Silverblue

Host may lack `g++`. Use existing skill **champsim-silverblue-build** or:

```bash
toolbox run -c champsim-dev bash -lc 'cd ~/research/ChampSim && make -j$(nproc)'
CHAMPSIM_TOOLBOX=champsim-dev ./runs/scripts/micro26/read_reg/run_all.sh
```

The batch script auto-selects `champsim-dev` toolbox when `g++` is missing.

## Parsing results from logs

Histogram block appears before `Simulation finished CPU`:

```bash
grep -A4 'Register reads before overwrite histogram' runs/output/micro26/read_reg/cs_logs/*.log
```

Single trace quick test (50M, no warmup):

```bash
bin/champsim --warmup-instructions 0 --simulation-instructions 50000000 --hide-heartbeat traces/tango_0000.champsim-005.gz
```

Example result (tango_0000, 50M): ~62% lifetimes with 1 read, ~20% with 0 reads.

## Extending or modifying

### Add histogram to structured stats (optional)

Current design prints directly from `RegisterAllocator`. To integrate with
`cpu_stats` / `plain_printer`, copy `read_before_overwrite_histogram` into
`inc/core_stats.h` in `end_phase()` and format in `src/plain_printer.cc`.

### Architectural-order counting (alternative, not implemented)

For strict in-order **architectural** counts (ignoring rename), maintain per-arch-reg
counters in `do_scheduling()` before rename loops. Simpler but does not reflect OoO
register versioning.

### New experiment scripts

Follow the same layout:

```
runs/scripts/micro26/<experiment>/run_all.sh
runs/output/micro26/<experiment>/cs_logs/
```

Resolve `CHAMPSIM_ROOT` with `../../../../` from `runs/scripts/micro26/<experiment>/`.

## Checklist for agents

When user asks to implement, debug, or run register-read histograms:

- [ ] Counting in `RegisterAllocator`, not trace reader or execute stage
- [ ] Bucket on `retire_dest_register()` / `free_register()`, not `complete_dest_register()`
- [ ] Reset histogram at simulation phase start (`!warmup`)
- [ ] Print at simulation phase end only
- [ ] CLI uses explicit `--warmup-instructions 0` when no warmup wanted
- [ ] Rebuild `bin/champsim` after code changes (toolbox if needed)
- [ ] Batch logs under `runs/output/micro26/read_reg/cs_logs/`
- [ ] Use `JOBS` to limit memory when running many large traces in parallel
