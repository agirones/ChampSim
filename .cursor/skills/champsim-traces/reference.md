# ChampSim trace inventory (reference)

## Google traces — full file list (43)

```
arizona_0000.champsim.gz
arizona_0001.champsim-037.gz
arizona_0002.champsim-034.gz
charlie_0000.champsim-026.gz
charlie_0001.champsim.gz
charlie_0002.champsim-042.gz
charlie_0003.champsim-024.gz
charlie_0004.champsim.gz
merced_0000.champsim-033.gz
merced_0001.champsim-010.gz
merced_0002.champsim-008.gz
merced_0003.champsim-036.gz
merced_0004.champsim-004.gz
sierra.a.3_0000.champsim-039.gz
sierra.a.3_0001.champsim-022.gz
sierra.a.3_0002.champsim-021.gz
sierra.a.3_0003.champsim-020.gz
sierra.a.3_0004.champsim-040.gz
sierra.a.4_0000.champsim-038.gz
sierra.a.4_0001.champsim-019.gz
sierra.a.4_0002.champsim-017.gz
sierra.a.4_0003.champsim-016.gz
sierra.a.4_0004.champsim-032.gz
sierra.a.6_0000.champsim-031.gz
sierra.a.6_0001.champsim-043.gz
sierra.a.6_0002.champsim-028.gz
sierra.a.6_0003.champsim-027.gz
sierra.a.6_0004.champsim-041.gz
tahoe_0000.champsim-006.gz
tahoe_0001.champsim-001.gz
tahoe_0002.champsim-011.gz
tahoe_0003.champsim-030.gz
tahoe_0004.champsim-009.gz
tango_0000.champsim-005.gz
tango_0001.champsim-029.gz
tango_0002.champsim-002.gz
tango_0003.champsim-007.gz
tango_0004.champsim-012.gz
yankee_0000.champsim-015.gz
yankee_0001.champsim-018.gz
yankee_0002.champsim-014.gz
yankee_0003.champsim-035.gz
yankee_0004.champsim-013.gz
```

## SPEC17 traces — full file list (20)

Sorted by SPEC number:

```
602.gcc_s-734B.champsimtrace.xz
602.gcc_s-1850B.champsimtrace.xz
603.bwaves_s-891B.champsimtrace.xz
603.bwaves_s-1740B.champsimtrace.xz
605.mcf_s-472B.champsimtrace.xz
605.mcf_s-484B.champsimtrace.xz
605.mcf_s-1536B.champsimtrace.xz
605.mcf_s-1554B.champsimtrace.xz
605.mcf_s-1644B.champsimtrace.xz
607.cactuBSSN_s-2421B.champsimtrace.xz
619.lbm_s-2676B.champsimtrace.xz
619.lbm_s-2677B.champsimtrace.xz
620.omnetpp_s-874B.champsimtrace.xz
621.wrf_s-6673B.champsimtrace.xz
623.xalancbmk_s-10B.champsimtrace.xz
649.fotonik3d_s-1176B.champsimtrace.xz
649.fotonik3d_s-7084B.champsimtrace.xz
654.roms_s-293B.champsimtrace.xz
654.roms_s-294B.champsimtrace.xz
654.roms_s-523B.champsimtrace.xz
```

## SPEC17 zip → trace mapping

| Zip | Traces inside |
|-----|---------------|
| `drive-download-...-001.zip` | 603.bwaves_s-891B, 605.mcf_s-484B, 619.lbm_s-2677B, 649.fotonik3d_s-7084B |
| `drive-download-...-002.zip` | 602.gcc_s-734B, 605.mcf_s-472B, 605.mcf_s-1536B, 654.roms_s-294B |
| `drive-download-...-003.zip` | 602.gcc_s-1850B, 605.mcf_s-1554B, 620.omnetpp_s-874B, 654.roms_s-523B |
| `drive-download-...-004.zip` | 603.bwaves_s-1740B, 607.cactuBSSN_s-2421B, 619.lbm_s-2676B, 649.fotonik3d_s-1176B |
| `drive-download-...-005.zip` | 605.mcf_s-1644B, 621.wrf_s-6673B, 623.xalancbmk_s-10B, 654.roms_s-293B |

## Quick discovery commands

List Google traces:

```bash
ls traces/google_traces/*.gz | sort
```

List SPEC17 traces (after extraction):

```bash
ls traces/spec17/*.xz | sort
```

Count traces in a suite:

```bash
find traces/google_traces -maxdepth 1 -type f \( -name '*.gz' -o -name '*.xz' \) | wc -l
find traces/spec17         -maxdepth 1 -type f \( -name '*.gz' -o -name '*.xz' \) | wc -l
```

Extract all SPEC17 zips:

```bash
for z in traces/spec17/*.zip; do
  unzip -j -o "$z" '*.xz' -d traces/spec17/
done
```
