---
name: champsim-register-read-histogram
description: >-
  Explains and runs ChampSim register-read-before-overwrite histograms (buckets
  0/1/2/3+). Covers physical-register lifetime counting, rename/retire hooks,
  self-read-write semantics, trace-driven (no wrong-path) model, GPR filtering,
  zero-read producers, micro26 batch runs, plot scripts, and Silverblue toolbox
  execution. Use when the user asks how register read counts work, register
  lifetime histograms, read_reg experiments, rename_src_register, or plotting
  read_reg / zero_read_producers results.
---

# ChampSim register-read-before-overwrite histogram

## What this measures

Count **how many times a physical register is read before its value is superseded**
by the next write to the same architectural register.

| Term | Meaning |
|------|---------|
| **Lifetime** | One physical register from dest-rename until the old phys reg is freed at retire when a newer write to the same arch reg commits |
| **Read** | One `rename_src_register()` call during scheduling (not execute) |
| **Overwrite** | A newer write to the same arch reg retires; old phys reg is bucketed and freed |
| **Buckets** | 0, 1, 2, 3+ reads per completed GPR lifetime |

Counting uses **OoO register renaming semantics**. ChampSim has no explicit
register-file read at execution. Lifetimes still live at simulation end are **not**
bucketed.

**Counting is at the physical-register level.** After `do_scheduling()`, operand
vectors hold `PHYSICAL_REGISTER_ID` values (`inc/instruction.h`). `read_counts`
is indexed by physical register, not architectural.

## When counts change

| Event | File | Function | Effect |
|-------|------|----------|--------|
| Read (+1) | `src/register_allocator.cc` | `rename_src_register()` | `++read_counts[phys]` if arch reg already mapped |
| New lifetime | `src/register_allocator.cc` | `rename_dest_register()` | `read_counts[new_phys] = 0` |
| Commit / bucket | `src/register_allocator.cc` | `retire_dest_register()` → `record_lifetime_reads()` | Old phys reg count → histogram bucket |
| Per-reg reset | `src/register_allocator.cc` | `free_register()` | `read_counts[phys] = 0` after bucketing |
| Histogram reset | `src/register_allocator.cc` | `reset_register_lifetime_histogram()` | Clears bucket arrays at sim phase start |
| Rename invoked | `src/ooo_cpu.cc` | `do_scheduling()` | Sources first, then destinations |
| Retire invoked | `src/ooo_cpu.cc` | `retire_rob()` | Calls `retire_dest_register()` per dest |

Trace operands are **architectural** IDs until `do_scheduling()` renames them.

### Cold-start reads

If `rename_src_register()` finds an unmapped arch reg (trace slice mid-program), it
allocates a synthetic phys reg (`reg_write_kind::trace_entry`) with count **0** — not
counted as a read of a prior value.

## Rename order and edge cases

`do_scheduling()` renames **all sources, then all destinations**:

```cpp
for (auto& src_reg : instr.source_registers)
  src_reg = reg_allocator.rename_src_register(src_reg);
for (auto& dreg : instr.destination_registers) {
  const auto arch_reg = dreg;
  dreg = reg_allocator.rename_dest_register(dreg, instr, arch_reg);
}
```

### Same arch reg as source and destination (`add rax, rax`)

1. `rename_src(rax)` → reads `P_old`, increments `read_counts[P_old]`
2. `rename_dest(rax)` → allocates `P_new`, `read_counts[P_new] = 0`

Source and dest become **different** physical registers. The insn reads the **previous**
lifetime, not the value it produces.

### Duplicate source operands (`X = X1 op X1`)

Each source slot calls `rename_src_register()` independently → **two** increments on
the same phys reg if both operands are the same arch reg.

See `test/cpp/src/201-register-rename.cc` for unit tests of these cases.

## Wrong path

ChampSim does **not** model wrong-path execution. It is **trace-driven**: fetch always
pulls the next instruction from `input_queue` (the traced committed stream).

Branch mispredictions only inject **timing penalties** (`fetch_resume_time`,
`branch_mispredicted`). They do not fetch alternate-path instructions or squash ROB
entries. All register counts therefore reflect traced (architecturally correct)
instructions only — not because of explicit right-path filtering, but because wrong
path does not exist in the model.

Wrong-path register recovery is noted as future work in
`RegisterAllocator::reset_frontend_RAT()`.

## GPR filtering and zero-read breakdown

`record_lifetime_reads()` only buckets lifetimes where `producer_kind == gpr`.
Stack pointer, flags, IP, stores, branches, and trace-entry mappings are excluded.

Zero-read GPR lifetimes (`reads == 0`) also update `zero_read_by_category` and print:

```
ZERO_READ_PROD category=gpr count=...
```

Set `CHAMPSIM_ZERO_READ_LOG` for per-event logging of zero-read producers.

## Plotting pipeline

| Script | Input | Output | Parses |
|--------|-------|--------|--------|
| `runs/scripts/micro26/read_reg/plot_read_reg.py` | `cs_logs/<suite>/*.log` | `graphs/read_reg.tex` | Histogram 0/1/2/3+ lines; requires `GPR lifetimes only` |
| `runs/scripts/micro26/read_reg/plot_zero_read_producers.py` | same logs | `graphs/zero_read_producers.tex` | `ZERO_READ_PROD category=gpr count=...` |

Suites: `google_traces`, `spec17`, `graph`, `ai`, `cvp-1-fix`. Each trace bar shows
bucket percentages; Mean is count-weighted across traces.

## Implementation summary

### `inc/register_allocator.h`

- `read_counts` — per-physical-register counter (`std::vector<uint32_t>`)
- `read_before_overwrite_histogram` — 4 buckets (`std::array<uint64_t, 4>`)
- `zero_read_by_category`, `zero_read_lifetime_total`

### Output format (simulation phase end)

```
CPU 0 Register reads before overwrite histogram (GPR lifetimes only, total: N)
  0 reads: ...
  1 read:  ...
  2 reads: ...
  3+ reads: ...
```

Also prints zero-read GPR breakdown and `ZERO_READ_PROD` lines when applicable.

### Phase hooks (`src/ooo_cpu.cc`)

- `begin_phase()`: `reset_register_lifetime_histogram()` when `!warmup`
- `end_phase()`: print histogram when `!warmup && finished_cpu == this->cpu`

## Warmup and CLI

Warmup clears register operands in `do_init_instruction()` — no rename during warmup.

**Always pass `--warmup-instructions 0` explicitly** when no warmup is desired.

```bash
bin/champsim --warmup-instructions 0 --simulation-instructions 100000000 --hide-heartbeat traces/foo.champsim-005.gz
```

Other caveats:

- **Stack pointer folding** may remove SP from destination registers
- **Special registers** handled in `inc/instruction.h`
- Total lifetimes > retired instructions (multi-dest instructions)

## Batch run

**Script:** `runs/scripts/micro26/read_reg/run_all.sh`  
**Logs:** `runs/output/micro26/read_reg/cs_logs/<suite>/*.log`

```bash
./runs/scripts/micro26/read_reg/run_all.sh
JOBS=8 SIM=50000000 ./runs/scripts/micro26/read_reg/run_all.sh
```

| Variable | Default | Purpose |
|----------|---------|---------|
| `JOBS` | `nproc` | Parallel trace runs |
| `WARMUP` | `0` | Warmup instructions |
| `SIM` | `100000000` | Simulation instructions |
| `CHAMPSIM_BIN` | `bin/champsim` | Simulator binary |
| `CHAMPSIM_TOOLBOX` | auto | Toolbox if host lacks `g++` |

On Silverblue, use skill **champsim-silverblue-build** or:

```bash
toolbox run -c champsim-dev bash -lc 'cd ~/research/ChampSim && make -j$(nproc)'
CHAMPSIM_TOOLBOX=champsim-dev ./runs/scripts/micro26/read_reg/run_all.sh
```

Trace layout: skill **champsim-traces**.

## Parse results from logs

```bash
grep -A4 'Register reads before overwrite histogram' runs/output/micro26/read_reg/cs_logs/*/*.log
grep 'ZERO_READ_PROD' runs/output/micro26/read_reg/cs_logs/*/*.log
```

## Additional reference

Worked examples, wrong-path details, and plot data flow:
[reference.md](reference.md)

## Checklist for agents

- [ ] Counting in `RegisterAllocator`, not trace reader or execute stage
- [ ] Reads counted at `rename_src_register()` on **physical** regs after RAT lookup
- [ ] Sources renamed before destinations in `do_scheduling()`
- [ ] Bucket on `retire_dest_register()` / `free_register()`, not `complete_dest_register()`
- [ ] Only GPR lifetimes enter histogram (`record_lifetime_reads` filter)
- [ ] Wrong path not modeled — trace stream only
- [ ] Reset histogram at simulation phase start (`!warmup`)
- [ ] Print at simulation phase end only
- [ ] CLI uses explicit `--warmup-instructions 0` when no warmup wanted
- [ ] Rebuild `bin/champsim` after code changes
- [ ] Plot scripts require `GPR lifetimes only` / `ZERO_READ_PROD` in logs
