# Register-read counting — reference

Detailed semantics and examples for the register-read-before-overwrite histogram.

## Lifetime timeline

```
Schedule (write)     rename_dest_register(arch)  →  read_counts[P_new] = 0
Schedule (read)      rename_src_register(arch)   →  ++read_counts[P_old]  (if mapped)
Retire (newer write) retire_dest_register(P_new)  →  bucket read_counts[P_old], free P_old
```

`P_old` is whatever `frontend_RAT[arch]` pointed to before the overwriting write was scheduled.
`P_new` is the physical register allocated for the overwriting write.

## Worked example: three-instruction chain

```
mov rax, 1    → allocates P0, read_counts[P0]=0
add rbx, rax  → rename_src(rax): read_counts[P0]=1
mov rax, 2    → rename_dest(rax): allocates P1, read_counts[P1]=0
... mov rax, 2 retires → retire_dest: bucket P0 as "1 read", free P0
```

## Worked example: self-read-write (`add rax, rax`)

Scheduling order in `do_scheduling()`: **all sources, then all destinations**.

```
rename_src(rax)  → ++read_counts[P_old]   (reads previous rax value)
rename_dest(rax) → allocates P_new, read_counts[P_new]=0
```

After rename: `source = P_old`, `destination = P_new` — different physical registers.
The instruction never reads the register it is producing.

Unit test: `test/cpp/src/201-register-rename.cc`, scenario "A long chain of RAW dependencies"
(instruction `i` reads phys reg `i`, writes phys reg `i+1`).

## Duplicate source operands (`X0 = X1 op X1`)

Each `rename_src_register()` call increments independently. Two source slots for the
same arch reg → **two** increments on that physical register's lifetime counter.

Unit test: `test/cpp/src/201-register-rename.cc`, scenario "An instruction of the form
X0 = X1 operation X1".

## Wrong path

ChampSim is trace-driven: `input_queue` is filled sequentially from the trace. Branch
mispredictions:

- Set `branch_mispredicted` and pause fetch (`fetch_resume_time`, `stop_fetch`)
- Do **not** inject alternate-path instructions
- Do **not** squash ROB entries

All traced instructions are architecturally correct. Register counting sees only that
stream. Mispredicted branches still rename and retire; mispredict affects timing only.

Future wrong-path support is noted in `RegisterAllocator::reset_frontend_RAT()`:
"once wrong path is implemented: find registers allocated by wrong-path instructions
and free them".

## GPR-only filtering

`record_lifetime_reads()` returns early unless `meta.producer_kind == reg_write_kind::gpr`.

Excluded from histogram:

| `reg_write_kind` | Typical source |
|----------------|----------------|
| `stack_pointer` | writes to SP arch reg |
| `flags` | writes to flags |
| `instruction_pointer` | writes to IP |
| `store` | instruction has `destination_memory` |
| `branch` | `instr.is_branch` |
| `trace_entry` | cold-start `rename_src` on unmapped arch reg |

`classify_producer()` in `register_allocator.cc` assigns the kind at dest rename.

## Zero-read producer breakdown

When `reads == 0` at lifetime end, `record_lifetime_reads()` also increments
`zero_read_by_category` (by producer kind). Printed as:

```
ZERO_READ_PROD category=gpr count=...
```

`plot_zero_read_producers.py` parses these lines. With GPR-only histogram filtering,
only the `gpr` category is populated in current builds.

Optional per-event log: set `CHAMPSIM_ZERO_READ_LOG=/path/to/file`.

## Plot script data flow

```
bin/champsim  →  stdout  →  runs/output/micro26/read_reg/cs_logs/<suite>/*.log
                                    ↓
              plot_read_reg.py  →  graphs/read_reg.tex
              plot_zero_read_producers.py  →  graphs/zero_read_producers.tex
```

`plot_read_reg.py` regex-parses histogram lines; requires `GPR lifetimes only` in log.
Converts raw counts to per-trace percentages; Mean bar is count-weighted across traces.

## OoO reordering vs wrong path

Reads are counted at **schedule** time in **OoO order** among in-flight traced
instructions. That is normal register renaming reordering, not wrong-path speculation.
