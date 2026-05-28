# SPEC CPU 2026 Build & Run Tool

Prerequisites: obtain your own copy of SPEC CPU 2026, then copy the `benchspec/` and `bin/` folder into this directory.

## Usage

```
./spec2026.py build intrate       # build integer rate benchmarks
./spec2026.py build fprate        # build floating-point rate benchmarks
./spec2026.py build intspeed      # build integer speed benchmarks
./spec2026.py build fpspeed       # build floating-point speed benchmarks

./spec2026.py run intrate         # run integer rate benchmarks
./spec2026.py run fprate          # run floating-point rate benchmarks
./spec2026.py run intspeed        # run integer speed benchmarks
./spec2026.py run fpspeed         # run floating-point speed benchmarks

./spec2026.py clean               # clean all build artifacts
./spec2026.py list                # list all available benchmarks
./spec2026.py list-sets           # list benchmark sets
./spec2026.py list-configs        # list build configs
```

### Build options

```
--cc <compiler>      C compiler (default: gcc)
--cxx <compiler>     C++ compiler (default: g++)
--fc <compiler>      Fortran compiler (default: gfortran)
--opt <flags>        Optimization flags (default: -O3)
-j <n>               Parallel jobs (default: all cores)
--config <name>      Config name (auto-generated if omitted)
-b <bench_id>        Build/run specific benchmark(s)
```

### Run options

```
--copies <n>         Number of rate copies (default: 1)
--input-size <size>  Input data: refrate, refspeed, test, train (default: refrate)
--taskset-core <n>   Pin first copy to this CPU via taskset
--perf-record        Wrap with perf record
```
