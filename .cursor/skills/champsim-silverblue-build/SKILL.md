---
name: champsim-silverblue-build
description: >-
  Build ChampSim on Fedora Silverblue using toolbox containers. Diagnose vcpkg
  compiler-detection failures (missing C++ toolchain). Use when the user is on
  Silverblue, Kinoite, or other rpm-ostree systems, mentions toolbox or distrobox,
  hits vcpkg "unable to detect compiler" errors, or needs ChampSim dependencies
  and build setup on immutable Fedora.
---

# ChampSim on Fedora Silverblue

## When to apply

- User is on Fedora Silverblue / Kinoite / other immutable rpm-ostree OS
- `vcpkg/vcpkg install` fails during "Detecting compiler hash for triplet x64-linux"
- User asks where to install `gcc-c++`, build tools, or ChampSim dependencies
- User wants a reproducible dev environment without layering packages on the host

**Do not** run `sudo dnf install` on the Silverblue host for dev toolchains. Use **toolbox** (or distrobox) instead.

## Diagnosing vcpkg compiler errors

The top-level message is often misleading:

```
error: vcpkg was unable to detect the active compiler's information.
```

Read the CMake logs under `vcpkg/buildtrees/detect_compiler/`:

| Log file | What to look for |
|----------|------------------|
| `config-x64-linux-rel-err.log` | Actual CMake error |
| `config-x64-linux-rel-out.log` | Which compilers were found vs unknown |

**Common root cause on Fedora:** C compiler present, C++ compiler missing.

```
-- The C compiler identification is GNU ...
-- The CXX compiler identification is unknown
CMake Error: No CMAKE_CXX_COMPILER could be found.
```

Verify on the system (or inside toolbox):

```bash
command -v g++ c++    # should print paths
g++ --version
rpm -q gcc gcc-c++    # Fedora: gcc-c++ often not installed
```

On Fedora, `gcc` provides `cc`/`gcc`; **`gcc-c++`** provides `g++`/`c++`. Installing only `gcc` is insufficient for ChampSim.

## Silverblue workflow

Home directory (e.g. `~/research/ChampSim`) is bind-mounted into toolbox. Build inside the container; artifacts remain in the project tree on the host.

### 1. Create and enter toolbox

```bash
toolbox create --container champsim-dev   # one-time
toolbox enter champsim-dev                # or: toolbox enter
```

### 2. Install dependencies inside toolbox

```bash
sudo dnf install -y \
  gcc gcc-c++ \
  make git \
  curl zip unzip tar
```

vcpkg bundles its own CMake and Ninja via `bootstrap-vcpkg.sh`; system `cmake`/`ninja-build` are optional.

Verify before proceeding:

```bash
g++ --version
```

### 3. Build ChampSim

From project root inside toolbox:

```bash
cd ~/research/ChampSim

git submodule update --init
vcpkg/bootstrap-vcpkg.sh
vcpkg/vcpkg install

./config.sh champsim_config.json   # or: ./config.sh
make
```

Run simulation:

```bash
bin/champsim --warmup-instructions 200000000 --simulation-instructions 500000000 /path/to/trace.champsimtrace.xz
```

## vcpkg manifest dependencies

ChampSim dependencies (from `vcpkg.json`): `cli11`, `nlohmann-json`, `fmt`, `bzip2`, `liblzma`, `zlib`, `catch2`. vcpkg installs these after compiler detection succeeds.

## Troubleshooting

### Partial failed vcpkg run on host (no g++)

If vcpkg was run on the host before toolbox was set up, retry inside toolbox. If detection still fails:

```bash
rm -rf vcpkg/buildtrees/detect_compiler
vcpkg/vcpkg install
```

### pyenv shim warnings in sandboxed shells

`mktemp: ... .pyenv/shims ... Permission denied` is unrelated to ChampSim/vcpkg. Ignore unless it blocks compiler discovery.

### Host vs toolbox

| Action | Where |
|--------|-------|
| `dnf install` dev packages | toolbox only |
| `rpm-ostree install` | host only, for system-level tools (avoid for routine dev) |
| Edit source, `git`, `make`, `vcpkg install` | toolbox (recommended) |
| Open project in editor | host (terminal/build in toolbox) |

## Quick reference (copy-paste)

```bash
toolbox enter champsim-dev
sudo dnf install -y gcc gcc-c++ make git curl zip unzip tar
cd ~/research/ChampSim
git submodule update --init
vcpkg/bootstrap-vcpkg.sh
vcpkg/vcpkg install
./config.sh
make
```
