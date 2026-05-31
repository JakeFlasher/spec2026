#!/usr/bin/env python3
"""SPEC CPU 2026 build and run tool.

Usage:
  ./spec2026.py build intrate [options]         # build benchmarks
  ./spec2026.py run intrate [options]           # run benchmarks
  ./spec2026.py clean intrate                   # clean build artifacts for a suite
  ./spec2026.py clean                           # clean all suites
  ./spec2026.py list                            # list benchmarks
  ./spec2026.py list-sets                       # list benchmark sets
  ./spec2026.py list-configs                    # list build configs
"""

import argparse
import glob as globmod
import json
import lzma
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

ROOT = os.environ.get("SPEC", os.path.dirname(os.path.abspath(__file__)))
CPU = os.path.join(ROOT, "benchspec", "CPU")
BUILD_BASE = os.path.join(ROOT, "build")
GEN_PL = os.path.join(ROOT, "generate-makefiles.pl")

BSETS = {
    "intrate": {"file": "intrate.bset", "desc": "Integer rate"},
    "fprate": {"file": "fprate.bset", "desc": "Floating-point rate"},
    "intspeed": {"file": "intspeed.bset", "desc": "Integer speed"},
    "fpspeed": {"file": "fpspeed.bset", "desc": "Floating-point speed"},
}

SUITE_CHOICES = list(BSETS.keys())


@dataclass
class Validation:
    type: str  # "FILE", "BIN-FILE", "CMD"
    output: str  # filename to compare against reference
    cmd: Optional[list] = None  # full command for CMD type
    abstol: Optional[float] = None
    reltol: Optional[float] = None


@dataclass
class Workload:
    args: list  # command-line arguments (exe name prepended at runtime)
    stdout: Optional[str] = None  # where to redirect stdout, or None
    stdin: Optional[str] = None  # stdin redirect from this file, or None
    validations: list = field(default_factory=list)


def parse_bset(name):
    with open(os.path.join(CPU, BSETS[name]["file"])) as f:
        return json.load(f)["benchmarks"]


def find_bench_dir(bench_id):
    for entry in os.listdir(CPU):
        if entry.startswith(bench_id + ".") or entry == bench_id:
            return os.path.join(CPU, entry)
    return None


def suite_for_bench(bench_id):
    for sname in SUITE_CHOICES:
        for b in parse_bset(sname):
            if b == bench_id or bench_id.startswith(b.split(".")[0]):
                return sname
    return None


def resolve_benches(args):
    benches = []
    if args.bench:
        benches = args.bench
    elif args.suite:
        benches = parse_bset(args.suite)
    else:
        print(
            "Error: specify a suite (e.g. intrate) or --bench <name>", file=sys.stderr
        )
        return None, None
    bench_dirs = []
    for b in benches:
        d = find_bench_dir(b)
        if d:
            bench_dirs.append(d)
        else:
            print(f"Error: benchmark '{b}' not found", file=sys.stderr)
            return None, None
    bench_ids = [os.path.basename(d) for d in bench_dirs]
    return bench_dirs, bench_ids


def make_config_tag(args):
    tag = os.path.basename(args.cc)
    if args.opt:
        f = args.opt.replace(" ", "")
        tag += f
    tag = re.sub(r"[^a-zA-Z0-9_.-=]", "-", tag)
    return tag


def build_root(suite, config_tag):
    if suite:
        return os.path.join(BUILD_BASE, suite, config_tag)
    return os.path.join(BUILD_BASE, config_tag)


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


def add_build_args(p):
    p.add_argument("suite", nargs="?", choices=SUITE_CHOICES, help="Benchmark suite")
    p.add_argument(
        "--bench", "-b", action="append", dest="bench", help="Specific benchmark(s)"
    )
    p.add_argument("--config", default=None, help="Config name (default: auto)")
    p.add_argument("--cc", default="gcc", help="C compiler (default: gcc)")
    p.add_argument("--cxx", default="g++", help="C++ compiler (default: g++)")
    p.add_argument(
        "--fc", default="gfortran", help="Fortran compiler (default: gfortran)"
    )
    p.add_argument("--opt", default="-O3", help="Optimization flags (default: -O3)")
    p.add_argument("--quiet", "-q", action="store_true", help="Less output")
    p.add_argument(
        "--dry-run", "-n", action="store_true", help="Show what would be done"
    )
    p.add_argument(
        "--jobs",
        "-j",
        type=int,
        default=os.cpu_count(),
        help=f"Parallel jobs (default: {os.cpu_count()})",
    )


def do_build(bench_ids, suite, config_tag, args):
    root = build_root(suite, config_tag)
    os.makedirs(root, exist_ok=True)

    env = os.environ.copy()
    env["SPEC"] = ROOT
    env["OUTPUT_DIR"] = root
    env["CC"] = args.cc
    env["CXX"] = args.cxx
    env["FC"] = args.fc
    env["COPT"] = args.opt
    env["CXXOPT"] = args.opt
    env["FOPT"] = args.opt
    env["XLIBS"] = " ".join(filter(lambda s: s.startswith("-l"), args.opt.split()))

    gen = subprocess.run(
        ["perl", GEN_PL] + bench_ids, env=env, capture_output=True, text=True
    )
    for line in gen.stdout.strip().split("\n"):
        if line.strip():
            print(f"  {line.strip()}")
    if gen.returncode != 0:
        print(gen.stderr, file=sys.stderr)
        return False

    all_ok = True
    for bid in bench_ids:
        build_dir = os.path.join(root, bid)

        # Find all subdirectories with Makefile.spec (one per executable)
        exe_dirs = []
        if os.path.isdir(build_dir):
            for entry in sorted(os.listdir(build_dir)):
                subdir = os.path.join(build_dir, entry)
                if os.path.isdir(subdir) and os.path.exists(
                    os.path.join(subdir, "Makefile.spec")
                ):
                    exe_dirs.append(entry)

        if not exe_dirs:
            print(
                f"  Error: no build subdirectories found in {build_dir}",
                file=sys.stderr,
            )
            all_ok = False
            continue

        for exe in exe_dirs:
            subdir = os.path.join(build_dir, exe)
            exe_path = os.path.join(subdir, exe)
            if os.path.exists(exe_path):
                size = os.path.getsize(exe_path)
                print(f"  OK: {exe_path} ({size / 1024 / 1024:.1f} MB)")
                continue

            print(f"  Building {exe}...", flush=True)
            env["SPEC"] = ROOT
            r = subprocess.run(
                ["make", "-C", subdir, "-j", str(args.jobs)],
                env=env,
                capture_output=True,
                text=True,
            )
            if r.returncode != 0:
                print(f"    FAILED ({exe}):")
                for l in (r.stdout + r.stderr).strip().split("\n")[-60:]:
                    print(f"      {l}")
                all_ok = False
            elif os.path.exists(exe_path):
                size = os.path.getsize(exe_path)
                print(f"  OK: {exe_path} ({size / 1024 / 1024:.1f} MB)")
            else:
                print(f"  OK (executable assumed in {subdir}/)")

    if all_ok:
        print()
        print("All benchmarks built successfully!")
    elif not all_ok:
        print()
        print("Some benchmarks failed.")
    return all_ok


def cmd_build(args):
    bench_dirs, bench_ids = resolve_benches(args)
    if bench_dirs is None:
        return 1
    config_tag = args.config or make_config_tag(args)
    suite = args.suite
    if suite is None and bench_ids:
        suite = suite_for_bench(bench_ids[0])
    root = build_root(suite, config_tag)

    if not args.quiet and not args.dry_run:
        print("=" * 72)
        print("SPEC CPU 2026 Build")
        print(f"  Suite:     {suite}")
        print(f"  Config:    {config_tag}")
        print(f"  Output:    {os.path.join(root, '<bench>/')}")
        print(f"  Compilers: CC={args.cc}, CXX={args.cxx}, FC={args.fc}")
        print(f"  Opt flags: {args.opt}")
        print(f"  Jobs:      {args.jobs}")
        print("=" * 72)

    if args.dry_run:
        for bid in bench_ids:
            print(f"  {bid}")
        return 0

    return 0 if do_build(bench_ids, suite, config_tag, args) else 1


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


def add_run_args(p):
    p.add_argument("suite", nargs="?", choices=SUITE_CHOICES, help="Benchmark suite")
    p.add_argument(
        "--bench", "-b", action="append", dest="bench", help="Specific benchmark(s)"
    )
    p.add_argument("--config", default=None, help="Config name (default: auto)")
    p.add_argument(
        "--copies", type=int, default=1, help="Number of rate copies (default: 1)"
    )
    p.add_argument(
        "--input-size",
        default="refrate",
        choices=["refrate", "refspeed", "test", "train"],
        help="Input data size (default: refrate)",
    )
    p.add_argument(
        "--taskset-core",
        type=int,
        default=None,
        help="Pin first copy to this CPU via taskset",
    )
    p.add_argument("--cc", default="gcc", help="C compiler (used for config tag)")
    p.add_argument("--opt", default="-O3", help="Opt flags (used for config tag)")
    p.add_argument(
        "--perf-record",
        nargs="?",
        const="",
        default=None,
        metavar="events",
        help="Wrap with perf record (optionally with -e events)",
    )
    p.add_argument(
        "--perf-stat",
        nargs="?",
        const="",
        default=None,
        metavar="events",
        help="Wrap with perf stat (optionally with -e events)",
    )
    p.add_argument(
        "--perf-stat-metrics",
        default=None,
        metavar="metrics",
        help="Pass -M <metrics> to perf stat (e.g. TopdownL1); can be combined with --perf-stat",
    )


# Per-benchmark workload definitions
# Each entry: (command_args, output_filename, validate_type)
# validate_type: "STDOUT" = compare captured stdout, "FILE" = compare generated file
BENCH_WORKLOADS = {
    "706.stockfish_r": [
        Workload(
            args=[
                "bench",
                "1600",
                "1",
                "26",
                "spec_ref_pos_1to6.fen",
                "depth",
                "classical",
            ],
            stdout="stockfish_spec_ref_pos_1to6_classical.out",
            validations=[
                Validation(
                    type="FILE", output="stockfish_spec_ref_pos_1to6_classical.out"
                )
            ],
        ),
        Workload(
            args=["bench", "1600", "1", "26", "spec_ref_pos_1to6.fen", "depth", "nnue"],
            stdout="stockfish_spec_ref_pos_1to6_nnue.out",
            validations=[
                Validation(type="FILE", output="stockfish_spec_ref_pos_1to6_nnue.out")
            ],
        ),
        Workload(
            args=[
                "bench",
                "1600",
                "1",
                "26",
                "spec_ref_pos_7to11.fen",
                "depth",
                "nnue",
            ],
            stdout="stockfish_spec_ref_pos_7to11_nnue.out",
            validations=[
                Validation(type="FILE", output="stockfish_spec_ref_pos_7to11_nnue.out")
            ],
        ),
    ],
    "707.ntest_r": [
        Workload(
            args=["Othello.154.ggf", "20", "16"],
            stdout="ntest.Othello.154.20.16.out",
            validations=[Validation(type="FILE", output="ntest.Othello.154.20.16.out")],
        )
    ],
    "708.sqlite_r": [
        Workload(
            args=["--memdb", "--size", "2000", "--testset", "main", "--verify"],
            stdout="sqlite_r.main.out",
            validations=[Validation(type="FILE", output="sqlite_r.main.out")],
        ),
        Workload(
            args=["--memdb", "--size", "2000", "--testset", "cte", "--verify"],
            stdout="sqlite_r.cte.out",
            validations=[Validation(type="FILE", output="sqlite_r.cte.out")],
        ),
        Workload(
            args=["--memdb", "--size", "1000", "--testset", "fp", "--verify"],
            stdout="sqlite_r.fp.out",
            validations=[Validation(type="FILE", output="sqlite_r.fp.out")],
        ),
    ],
    "710.omnetpp_r": [
        Workload(
            args=["-f", "randomMesh.ini", "-c", "General"],
            validations=[
                Validation(type="FILE", output="randomMesh-General-0.sca"),
                Validation(type="FILE", output="randomMesh-General-1.sca"),
                Validation(type="FILE", output="randomMesh-General-2.sca"),
            ],
        ),
        Workload(
            args=["-f", "queuenet.ini", "-c", "OneFifo"],
            validations=[Validation(type="FILE", output="queuenet-OneFifo-0.sca")],
        ),
        Workload(
            args=["-f", "queuenet.ini", "-c", "TandemFifos"],
            validations=[Validation(type="FILE", output="queuenet-TandemFifos-0.sca")],
        ),
        Workload(
            args=["-f", "queuenet.ini", "-c", "SmallCQN"],
            validations=[Validation(type="FILE", output="queuenet-SmallCQN-0.sca")],
        ),
        Workload(
            args=["-f", "queuenet.ini", "-c", "Ring"],
            validations=[Validation(type="FILE", output="queuenet-Ring-0.sca")],
        ),
        Workload(
            args=["-f", "queuenet.ini", "-c", "Terminal"],
            validations=[Validation(type="FILE", output="queuenet-Terminal-0.sca")],
        ),
        Workload(
            args=["-f", "queuenet.ini", "-c", "CallCenter"],
            validations=[Validation(type="FILE", output="queuenet-CallCenter-0.sca")],
        ),
        Workload(
            args=["-f", "queuenet.ini", "-c", "ForkJoin"],
            validations=[Validation(type="FILE", output="queuenet-ForkJoin-0.sca")],
        ),
        Workload(
            args=["-f", "queuenet.ini", "-c", "ResourceAllocation"],
            validations=[
                Validation(type="FILE", output="queuenet-ResourceAllocation-0.sca")
            ],
        ),
        Workload(
            args=["-f", "queuenet.ini", "-c", "AllocDealloc"],
            validations=[Validation(type="FILE", output="queuenet-AllocDealloc-0.sca")],
        ),
    ],
    "714.cpython_r": [
        Workload(
            args=[
                "-I",
                "-B",
                "coreml_pb.py",
                "-i",
                "2",
                "-a",
                "-m",
                "Resnet50Headless.mlmodel",
                "-d",
                "10",
            ],
            stdout="cpython_r_0.out",
            validations=[Validation(type="FILE", output="cpython_r_0.out")],
        ),
        Workload(
            args=[
                "-I",
                "-B",
                "coreml_pb.py",
                "-i",
                "5",
                "-a",
                "-c",
                "-m",
                "MobileNetV2.mlmodel",
                "-d",
                "20",
            ],
            stdout="cpython_r_1.out",
            validations=[Validation(type="FILE", output="cpython_r_1.out")],
        ),
        Workload(
            args=["-I", "-B", "dna_bench.py", "600000"],
            stdout="cpython_r_2.out",
            validations=[Validation(type="FILE", output="cpython_r_2.out")],
        ),
    ],
    "721.gcc_r": [
        Workload(
            args=["gcc-pp.c", "-O2", "-fpic", "-o", "gcc-pp.c.opts-O2_-fpic.s"],
            validations=[Validation(type="FILE", output="gcc-pp.c.opts-O2_-fpic.s")],
        ),
        Workload(
            args=[
                "gcc-smaller.c",
                "-O3",
                "-fipa-pta",
                "-o",
                "gcc-smaller.c.opts-O3_-fipa-pta.s",
            ],
            validations=[
                Validation(type="FILE", output="gcc-smaller.c.opts-O3_-fipa-pta.s")
            ],
        ),
        Workload(
            args=[
                "ref32.c",
                "-O3",
                "-finline-limit=12000",
                "-fno-tree-vrp",
                "-o",
                "ref32.c.opts-O3_-finline-limit_12000_-fno-tree-vrp.s",
            ],
            validations=[
                Validation(
                    type="FILE",
                    output="ref32.c.opts-O3_-finline-limit_12000_-fno-tree-vrp.s",
                )
            ],
        ),
    ],
    "723.llvm_r": [
        Workload(
            args=[
                "transformsplus.bc",
                "-S",
                "-O3",
                "-mcpu=pwr9",
                "--sha512",
                "-o",
                "transformsplus.bc.opts-S_-O3_-mcpu_pwr9.ll",
            ],
            stdout="transformsplus.bc.opts-S_-O3_-mcpu_pwr9.out",
            validations=[
                Validation(
                    type="FILE", output="transformsplus.bc.opts-S_-O3_-mcpu_pwr9.out"
                )
            ],
        ),
        Workload(
            args=[
                "codegen.bc",
                "-S",
                "-O3",
                "-mcpu=pwr9",
                "--sha512",
                "-o",
                "codegen.bc.opts-S_-O3_-mcpu_pwr9.ll",
            ],
            stdout="codegen.bc.opts-S_-O3_-mcpu_pwr9.out",
            validations=[
                Validation(type="FILE", output="codegen.bc.opts-S_-O3_-mcpu_pwr9.out")
            ],
        ),
    ],
    "727.cppcheck_r": [
        Workload(
            args=[
                "--force",
                "738-diamond-record.cpp",
                "--checkers-report=738_report.txt",
                "--enable=all",
                "--output-file=738_bogey.txt",
                "--platform=unix64",
            ],
            stdout="cppcheck_r.738_bogey.out",
            validations=[
                Validation(type="FILE", output="cppcheck_r.738_bogey.out"),
                Validation(type="FILE", output="738_bogey.txt"),
                Validation(type="FILE", output="738_report.txt"),
            ],
        ),
        Workload(
            args=[
                "--force",
                "747-dealii-data_out_base.cc",
                "--checkers-report=747_report.txt",
                "--enable=all",
                "--output-file=747_bogey.txt",
                "--platform=unix64",
            ],
            stdout="cppcheck_r.747_bogey.out",
            validations=[
                Validation(type="FILE", output="cppcheck_r.747_bogey.out"),
                Validation(type="FILE", output="747_bogey.txt"),
                Validation(type="FILE", output="747_report.txt"),
            ],
        ),
        Workload(
            args=[
                "--force",
                "770-7z-SystemPage.cpp",
                "--checkers-report=770_report.txt",
                "--output-file=770_bogey.txt",
                "--platform=unix64",
            ],
            stdout="cppcheck_r.770_bogey.out",
            validations=[
                Validation(type="FILE", output="cppcheck_r.770_bogey.out"),
                Validation(type="FILE", output="770_bogey.txt"),
                Validation(type="FILE", output="770_report.txt"),
            ],
        ),
    ],
    "729.abc_r": [
        Workload(
            args=["-F", "twoexact.in"],
            stdout="twoexact.out",
            validations=[Validation(type="FILE", output="twoexact.out")],
        ),
        Workload(
            args=["-F", "beem6-fraig.in"],
            validations=[Validation(type="BIN-FILE", output="beem6.out.aig")],
        ),
        Workload(
            args=["-F", "mem_ctrl.in"],
            validations=[Validation(type="BIN-FILE", output="mem_ctrl.out.aig")],
        ),
        Workload(
            args=["-F", "vga_lcd_miter.in"],
            validations=[Validation(type="BIN-FILE", output="vga_lcd_miter.out.aig")],
        ),
        Workload(
            args=["-F", "mcml.in"],
            stdout="mcml.out",
            validations=[Validation(type="FILE", output="mcml.out")],
        ),
        Workload(
            args=["-F", "des_system90.in"],
            stdout="des_system90.out",
            validations=[Validation(type="FILE", output="des_system90.out")],
        ),
    ],
    "734.vpr_r": [
        Workload(
            args=[
                "stratixiv_arch.timing.xml",
                "JPEG_stratixiv_arch_timing.blif",
                "--RL_agent_placement",
                "off",
                "--place_algorithm",
                "bounding_box",
                "--max_criticality",
                "0.0",
                "--init_t",
                "512",
                "--alpha_t",
                "0.75",
                "--exit_t",
                "1",
                "--router_initial_timing",
                "all_critical",
                "--routing_failure_predictor",
                "off",
                "--route_chan_width",
                "300",
                "--max_router_iterations",
                "20",
                "--router_lookahead",
                "classic",
                "--initial_pres_fac",
                "1.0",
                "--pres_fac_mult",
                "2.0",
                "--astar_fac",
                "1.5",
                "--router_profiler_astar_fac",
                "1.5",
                "--seed",
                "3",
                "--sdc_file",
                "JPEG_stratixiv_arch_timing.sdc",
                "--pack_verbosity",
                "0",
                "--netlist_verbosity",
                "0",
                "--base_cost_type",
                "demand_only",
                "--inner_num",
                "4",
                "--read_initial_place_file",
                "ref_JPEG_stratixiv_arch_timing.init.place",
                "--place",
            ],
            stdout="JPEG_stratixiv_arch_timing.blif.place.log",
            validations=[
                Validation(
                    type="CMD",
                    output="compare_JPEG_stratixiv_arch_timing.blif.place.log.swap_call.out",
                    cmd=[
                        "./vpr_out_compare",
                        "swap_call",
                        "compare/JPEG_stratixiv_arch_timing.blif.place.log",
                        "JPEG_stratixiv_arch_timing.blif.place.log",
                    ],
                ),
                Validation(
                    type="CMD",
                    output="compare_JPEG_stratixiv_arch_timing.blif.place.log.swap_accepted.out",
                    cmd=[
                        "./vpr_out_compare",
                        "swap_accepted",
                        "compare/JPEG_stratixiv_arch_timing.blif.place.log",
                        "JPEG_stratixiv_arch_timing.blif.place.log",
                    ],
                ),
                Validation(
                    type="CMD",
                    output="compare_JPEG_stratixiv_arch_timing.blif.place.log.swap_rejected.out",
                    cmd=[
                        "./vpr_out_compare",
                        "swap_rejected",
                        "compare/JPEG_stratixiv_arch_timing.blif.place.log",
                        "JPEG_stratixiv_arch_timing.blif.place.log",
                    ],
                ),
            ],
        ),
        Workload(
            args=[
                "stratixiv_arch.timing.xml",
                "JPEG_stratixiv_arch_timing.blif",
                "--place_algorithm",
                "bounding_box",
                "--place_static_notiming_move_prob",
                "50",
                "25",
                "25",
                "--max_criticality",
                "0.0",
                "--router_initial_timing",
                "all_critical",
                "--routing_failure_predictor",
                "off",
                "--route_chan_width",
                "300",
                "--max_router_iterations",
                "20",
                "--router_lookahead",
                "classic",
                "--initial_pres_fac",
                "1.0",
                "--pres_fac_mult",
                "2.0",
                "--astar_fac",
                "1.5",
                "--router_profiler_astar_fac",
                "1.5",
                "--seed",
                "3",
                "--sdc_file",
                "JPEG_stratixiv_arch_timing.sdc",
                "--pack_verbosity",
                "0",
                "--netlist_verbosity",
                "0",
                "--base_cost_type",
                "demand_only",
                "--place_file",
                "ref_JPEG_stratixiv_arch_timing.place",
                "--analysis",
                "--route",
            ],
            stdout="JPEG_stratixiv_arch_timing.blif.route.log",
            validations=[
                Validation(
                    type="CMD",
                    output="compare_JPEG_stratixiv_arch_timing.blif.route.log.num_rr_nodes.out",
                    cmd=[
                        "./vpr_out_compare",
                        "num_rr_nodes",
                        "compare/JPEG_stratixiv_arch_timing.blif.route.log",
                        "JPEG_stratixiv_arch_timing.blif.route.log",
                    ],
                ),
                Validation(
                    type="CMD",
                    output="compare_JPEG_stratixiv_arch_timing.blif.route.log.num_rr_edges.out",
                    cmd=[
                        "./vpr_out_compare",
                        "num_rr_edges",
                        "compare/JPEG_stratixiv_arch_timing.blif.route.log",
                        "JPEG_stratixiv_arch_timing.blif.route.log",
                    ],
                ),
                Validation(
                    type="CMD",
                    output="compare_JPEG_stratixiv_arch_timing.blif.route.log.heap_pushes.out",
                    cmd=[
                        "./vpr_out_compare",
                        "heap_pushes",
                        "compare/JPEG_stratixiv_arch_timing.blif.route.log",
                        "JPEG_stratixiv_arch_timing.blif.route.log",
                    ],
                ),
                Validation(
                    type="CMD",
                    output="compare_JPEG_stratixiv_arch_timing.blif.route.log.heap_pops.out",
                    cmd=[
                        "./vpr_out_compare",
                        "heap_pops",
                        "compare/JPEG_stratixiv_arch_timing.blif.route.log",
                        "JPEG_stratixiv_arch_timing.blif.route.log",
                    ],
                ),
                Validation(
                    type="CMD",
                    output="compare_JPEG_stratixiv_arch_timing.blif.route.log.critical_path_delay.out",
                    cmd=[
                        "./vpr_out_compare",
                        "critical_path_delay",
                        "compare/JPEG_stratixiv_arch_timing.blif.route.log",
                        "JPEG_stratixiv_arch_timing.blif.route.log",
                    ],
                ),
                Validation(
                    type="CMD",
                    output="compare_JPEG_stratixiv_arch_timing.blif.route.log.routed_wire_length.out",
                    cmd=[
                        "./vpr_out_compare",
                        "routed_wire_length",
                        "compare/JPEG_stratixiv_arch_timing.blif.route.log",
                        "JPEG_stratixiv_arch_timing.blif.route.log",
                    ],
                ),
            ],
        ),
        Workload(
            args=[
                "stratixiv_arch.timing.xml",
                "smithwaterman_stratixiv_arch_timing.blif",
                "--RL_agent_placement",
                "off",
                "--place_algorithm",
                "bounding_box",
                "--max_criticality",
                "0.0",
                "--init_t",
                "512",
                "--alpha_t",
                "0.75",
                "--exit_t",
                "1",
                "--router_initial_timing",
                "all_critical",
                "--routing_failure_predictor",
                "off",
                "--route_chan_width",
                "300",
                "--max_router_iterations",
                "20",
                "--router_lookahead",
                "classic",
                "--initial_pres_fac",
                "1.0",
                "--pres_fac_mult",
                "2.0",
                "--astar_fac",
                "1.5",
                "--router_profiler_astar_fac",
                "1.5",
                "--seed",
                "3",
                "--sdc_file",
                "smithwaterman_stratixiv_arch_timing.sdc",
                "--pack_verbosity",
                "0",
                "--netlist_verbosity",
                "0",
                "--base_cost_type",
                "demand_only",
                "--inner_num",
                "1.8",
                "--read_initial_place_file",
                "ref_smithwaterman_stratixiv_arch_timing.init.place",
                "--place",
            ],
            stdout="smithwaterman_stratixiv_arch_timing.blif.place.log",
            validations=[
                Validation(
                    type="CMD",
                    output="compare_smithwaterman_stratixiv_arch_timing.blif.place.log.swap_call.out",
                    cmd=[
                        "./vpr_out_compare",
                        "swap_call",
                        "compare/smithwaterman_stratixiv_arch_timing.blif.place.log",
                        "smithwaterman_stratixiv_arch_timing.blif.place.log",
                    ],
                ),
                Validation(
                    type="CMD",
                    output="compare_smithwaterman_stratixiv_arch_timing.blif.place.log.swap_accepted.out",
                    cmd=[
                        "./vpr_out_compare",
                        "swap_accepted",
                        "compare/smithwaterman_stratixiv_arch_timing.blif.place.log",
                        "smithwaterman_stratixiv_arch_timing.blif.place.log",
                    ],
                ),
                Validation(
                    type="CMD",
                    output="compare_smithwaterman_stratixiv_arch_timing.blif.place.log.swap_rejected.out",
                    cmd=[
                        "./vpr_out_compare",
                        "swap_rejected",
                        "compare/smithwaterman_stratixiv_arch_timing.blif.place.log",
                        "smithwaterman_stratixiv_arch_timing.blif.place.log",
                    ],
                ),
            ],
        ),
        Workload(
            args=[
                "stratixiv_arch.timing.xml",
                "smithwaterman_stratixiv_arch_timing.blif",
                "--place_algorithm",
                "bounding_box",
                "--place_static_notiming_move_prob",
                "50",
                "25",
                "25",
                "--max_criticality",
                "0.0",
                "--router_initial_timing",
                "all_critical",
                "--routing_failure_predictor",
                "off",
                "--route_chan_width",
                "300",
                "--max_router_iterations",
                "20",
                "--router_lookahead",
                "classic",
                "--initial_pres_fac",
                "1.0",
                "--pres_fac_mult",
                "2.0",
                "--astar_fac",
                "1.5",
                "--router_profiler_astar_fac",
                "1.5",
                "--seed",
                "3",
                "--sdc_file",
                "smithwaterman_stratixiv_arch_timing.sdc",
                "--pack_verbosity",
                "0",
                "--netlist_verbosity",
                "0",
                "--base_cost_type",
                "demand_only",
                "--place_file",
                "ref_smithwaterman_stratixiv_arch_timing.place",
                "--analysis",
                "--route",
            ],
            stdout="smithwaterman_stratixiv_arch_timing.blif.route.log",
            validations=[
                Validation(
                    type="CMD",
                    output="compare_smithwaterman_stratixiv_arch_timing.blif.route.log.num_rr_nodes.out",
                    cmd=[
                        "./vpr_out_compare",
                        "num_rr_nodes",
                        "compare/smithwaterman_stratixiv_arch_timing.blif.route.log",
                        "smithwaterman_stratixiv_arch_timing.blif.route.log",
                    ],
                ),
                Validation(
                    type="CMD",
                    output="compare_smithwaterman_stratixiv_arch_timing.blif.route.log.num_rr_edges.out",
                    cmd=[
                        "./vpr_out_compare",
                        "num_rr_edges",
                        "compare/smithwaterman_stratixiv_arch_timing.blif.route.log",
                        "smithwaterman_stratixiv_arch_timing.blif.route.log",
                    ],
                ),
                Validation(
                    type="CMD",
                    output="compare_smithwaterman_stratixiv_arch_timing.blif.route.log.heap_pushes.out",
                    cmd=[
                        "./vpr_out_compare",
                        "heap_pushes",
                        "compare/smithwaterman_stratixiv_arch_timing.blif.route.log",
                        "smithwaterman_stratixiv_arch_timing.blif.route.log",
                    ],
                ),
                Validation(
                    type="CMD",
                    output="compare_smithwaterman_stratixiv_arch_timing.blif.route.log.heap_pops.out",
                    cmd=[
                        "./vpr_out_compare",
                        "heap_pops",
                        "compare/smithwaterman_stratixiv_arch_timing.blif.route.log",
                        "smithwaterman_stratixiv_arch_timing.blif.route.log",
                    ],
                ),
                Validation(
                    type="CMD",
                    output="compare_smithwaterman_stratixiv_arch_timing.blif.route.log.critical_path_delay.out",
                    cmd=[
                        "./vpr_out_compare",
                        "critical_path_delay",
                        "compare/smithwaterman_stratixiv_arch_timing.blif.route.log",
                        "smithwaterman_stratixiv_arch_timing.blif.route.log",
                    ],
                ),
                Validation(
                    type="CMD",
                    output="compare_smithwaterman_stratixiv_arch_timing.blif.route.log.routed_wire_length.out",
                    cmd=[
                        "./vpr_out_compare",
                        "routed_wire_length",
                        "compare/smithwaterman_stratixiv_arch_timing.blif.route.log",
                        "smithwaterman_stratixiv_arch_timing.blif.route.log",
                    ],
                ),
            ],
        ),
    ],
    "735.gem5_r": [
        Workload(
            args=[
                "--stats-file=run_riscv_boot.py_o3_10_--max-ticks_10_000_000_000_stats.stats.txt",
                "run_riscv_boot.py",
                "o3",
                "10",
                "--max-ticks",
                "10_000_000_000",
            ],
            validations=[
                Validation(
                    type="CMD",
                    output="run_riscv_boot.py_o3_10_--max-ticks_10_000_000_000_stats.out",
                    cmd=[
                        "./gem5stats",
                        "control.stat",
                        "m5out/run_riscv_boot.py_o3_10_--max-ticks_10_000_000_000_stats.stats.txt",
                    ],
                )
            ],
        ),
        Workload(
            args=[
                "--stats-file=run_riscv_boot.py_timing_4_--max-ticks_20_000_000_000.stats.txt",
                "run_riscv_boot.py",
                "timing",
                "4",
                "--max-ticks",
                "20_000_000_000",
            ],
            validations=[
                Validation(
                    type="CMD",
                    output="run_riscv_boot.py_timing_4_--max-ticks_20_000_000_000_stats.out",
                    cmd=[
                        "./gem5stats",
                        "control.stat",
                        "m5out/run_riscv_boot.py_timing_4_--max-ticks_20_000_000_000.stats.txt",
                    ],
                )
            ],
        ),
        Workload(
            args=[
                "--stats-file=synthetic_traffic.py_LinearGenerator_21.stats.txt",
                "synthetic_traffic.py",
                "LinearGenerator",
                "21",
            ],
            validations=[
                Validation(
                    type="CMD",
                    output="synthetic_traffic.py_LinearGenerator_21_stats.out",
                    cmd=[
                        "./gem5stats",
                        "control.stat",
                        "m5out/synthetic_traffic.py_LinearGenerator_21.stats.txt",
                    ],
                )
            ],
        ),
        Workload(
            args=[
                "--stats-file=synthetic_traffic.py_LinearGenerator_74_--ruby.stats.txt",
                "synthetic_traffic.py",
                "LinearGenerator",
                "74",
                "--ruby",
            ],
            validations=[
                Validation(
                    type="CMD",
                    output="synthetic_traffic.py_LinearGenerator_74_--ruby_stats.out",
                    cmd=[
                        "./gem5stats",
                        "control.stat",
                        "m5out/synthetic_traffic.py_LinearGenerator_74_--ruby.stats.txt",
                    ],
                )
            ],
        ),
    ],
    "750.sealcrypto_r": [
        Workload(
            args=["refrate", "ecuador_province_capitals_refrate.csv", "Galapagos"],
            stdout="homoencrypt.refrate_ecuador_province_capitals_refrate.csv_Galapagos.out",
            validations=[
                Validation(
                    type="FILE",
                    output="homoencrypt.refrate_ecuador_province_capitals_refrate.csv_Galapagos.out",
                )
            ],
        )
    ],
    "753.ns3_r": [
        Workload(
            args=["mobile-scenario", "--simTimeMinutes=3", "--RngSeed=1", "--RngRun=1"],
            validations=[Validation(type="FILE", output="mobile-scenario.xml")],
        ),
        Workload(
            args=[
                "tcp-pacing",
                "--simulationEndTime=500",
                "--useEcn=false",
                "--RngSeed=1",
                "--RngRun=1",
            ],
            stdout="tcp-pacing_1.out",
            validations=[
                Validation(type="FILE", output="tcp-pacing_1.out"),
                Validation(type="FILE", output="tcp-dynamic-pacing-cwnd.dat"),
                Validation(type="FILE", output="tcp-dynamic-pacing-ssthresh.dat"),
            ],
        ),
        Workload(
            args=[
                "lena-radio-link-failure",
                "--numberOfEnbs=2",
                "--interSiteDistance=800",
                "--simTime=200",
                "--RngSeed=1",
                "--RngRun=1",
            ],
            stdout="lena-radio-link-failure_2.out",
            validations=[
                Validation(type="FILE", output="lena-radio-link-failure_2.out"),
                Validation(type="FILE", output="rlf_dl_thrput_2_eNB_ideal_rrc"),
            ],
        ),
        Workload(
            args=[
                "dctcp-example",
                "--enableSwitchEcn=true",
                "--flowStartupWindow=0.4",
                "--convergenceTime=0.4",
                "--measurementWindow=0.4",
                "--RngSeed=1",
                "--RngRun=1",
            ],
            stdout="dctcp-example_3.out",
            validations=[
                Validation(type="FILE", output="dctcp-example_3.out"),
                Validation(type="FILE", output="dctcp-example-faireness.dat"),
                Validation(type="FILE", output="dctcp-example-s1-r1-throughput.dat"),
                Validation(type="FILE", output="dctcp-example-s2-r2-throughput.dat"),
                Validation(type="FILE", output="dctcp-example-s3-r1-throughput.dat"),
                Validation(type="FILE", output="dctcp-example-t1-length.dat"),
                Validation(type="FILE", output="dctcp-example-t2-length.dat"),
            ],
        ),
        Workload(
            args=[
                "wifi-mixed-network",
                "--isUdp=0",
                "--payloadSize=3072",
                "--simulationTime=25",
                "--RngSeed=1",
                "--RngRun=1",
            ],
            stdout="wifi-mixed-network_4.out",
            validations=[Validation(type="FILE", output="wifi-mixed-network_4.out")],
        ),
        Workload(
            args=[
                "wifi-eht-network",
                "--simulationTime=0.2",
                "--frequency=5",
                "--useRts=1",
                "--minExpectedThroughput=6",
                "--maxExpectedThroughput=547",
                "--RngSeed=1",
                "--RngRun=1",
            ],
            stdout="wifi-eht-network_5.out",
            validations=[Validation(type="FILE", output="wifi-eht-network_5.out")],
        ),
    ],
    "777.zstd_r": [
        Workload(
            args=["-b3", "-e3", "--verbose", "-i40", "cld.tar"],
            stdout="zstd.b3_e3_verbose_i40_cld.tar.out",
            validations=[
                Validation(type="FILE", output="zstd.b3_e3_verbose_i40_cld.tar.out")
            ],
        ),
        Workload(
            args=["-b5", "-e5", "--verbose", "-i25", "cld.tar"],
            stdout="zstd.b5_e5_verbose_i25_cld.tar.out",
            validations=[
                Validation(type="FILE", output="zstd.b5_e5_verbose_i25_cld.tar.out")
            ],
        ),
        Workload(
            args=["-b7", "-e7", "--verbose", "-i12", "cld.tar"],
            stdout="zstd.b7_e7_verbose_i12_cld.tar.out",
            validations=[
                Validation(type="FILE", output="zstd.b7_e7_verbose_i12_cld.tar.out")
            ],
        ),
        Workload(
            args=["-b10", "-e10", "--verbose", "-i6", "cld.tar"],
            stdout="zstd.b10_e10_verbose_i6_cld.tar.out",
            validations=[
                Validation(type="FILE", output="zstd.b10_e10_verbose_i6_cld.tar.out")
            ],
        ),
        Workload(
            args=["-b14", "-e14", "--verbose", "-i4", "cld.tar"],
            stdout="zstd.b14_e14_verbose_i4_cld.tar.out",
            validations=[
                Validation(type="FILE", output="zstd.b14_e14_verbose_i4_cld.tar.out")
            ],
        ),
        Workload(
            args=["-b16", "-e16", "--verbose", "-i1", "cld.tar"],
            stdout="zstd.b16_e16_verbose_i1_cld.tar.out",
            validations=[
                Validation(type="FILE", output="zstd.b16_e16_verbose_i1_cld.tar.out")
            ],
        ),
        Workload(
            args=["-b18", "-e18", "--verbose", "-i1", "cld.tar"],
            stdout="zstd.b18_e18_verbose_i1_cld.tar.out",
            validations=[
                Validation(type="FILE", output="zstd.b18_e18_verbose_i1_cld.tar.out")
            ],
        ),
        Workload(
            args=["-b19", "-e19", "--verbose", "-i1", "cld.tar"],
            stdout="zstd.b19_e19_verbose_i1_cld.tar.out",
            validations=[
                Validation(type="FILE", output="zstd.b19_e19_verbose_i1_cld.tar.out")
            ],
        ),
    ],
    "709.cactus_r": [
        Workload(
            args=["ShiftedGaugeWave.par"],
            stdout="cactus.out",
            validations=[
                Validation(
                    type="FILE", output="cactus.out", abstol=1e-14, reltol=0.0001
                ),
                Validation(type="FILE", output="gxx.dl", abstol=1e-14, reltol=0.0001),
                Validation(type="FILE", output="gxx.xl", abstol=1e-14, reltol=0.0001),
                Validation(type="FILE", output="gxx.yl", abstol=1e-14, reltol=0.0001),
                Validation(type="FILE", output="gxx.zl", abstol=1e-14, reltol=0.0001),
                Validation(type="FILE", output="gxy.dl", abstol=1e-14, reltol=0.0001),
                Validation(type="FILE", output="gxy.xl", abstol=1e-14, reltol=0.0001),
                Validation(type="FILE", output="gxy.yl", abstol=1e-14, reltol=0.0001),
                Validation(type="FILE", output="gxy.zl", abstol=1e-14, reltol=0.0001),
            ],
        ),
    ],
    "722.palm_r": [
        Workload(
            args=[],
            stdin="runfile_atmos",
            validations=[Validation(type="FILE", output="RUN_CONTROL")],
        ),
    ],
    "731.astcenc_r": [
        Workload(
            args=["ref-inputs-linear.txt"],
            stdout="astcenc_r.0.out",
            validations=[
                Validation(type="FILE", output="astcenc_r.0.out", reltol=0.01)
            ],
        ),
        Workload(
            args=["ref-inputs-hdr.txt"],
            stdout="astcenc_r.1.out",
            validations=[
                Validation(type="FILE", output="astcenc_r.1.out", reltol=0.01)
            ],
        ),
        Workload(
            args=["ref-inputs-precision.txt"],
            stdout="astcenc_r.2.out",
            validations=[
                Validation(type="FILE", output="astcenc_r.2.out", reltol=0.01)
            ],
        ),
    ],
    "736.ocio_r": [
        Workload(
            args=[
                "--spec-validation-offset",
                "101",
                "--spec-validation-stride",
                "17",
                "--spec-validation-pixels",
                "131",
                "--bitdepths",
                "ui16",
                "ui16",
                "--iter",
                "100",
                "--test",
                "-1",
                "--transform",
                "ctf/lut1d_halfdom.ctf",
            ],
            stdout="perf_lut1d_halfdom.ctf.out",
            validations=[
                Validation(type="FILE", output="perf_lut1d_halfdom.ctf.out", abstol=2)
            ],
        ),
        Workload(
            args=[
                "--spec-validation-offset",
                "202",
                "--spec-validation-stride",
                "19",
                "--spec-validation-pixels",
                "132",
                "--bitdepths",
                "ui16",
                "f32",
                "--iter",
                "200",
                "--8kres",
                "--test",
                "0",
                "--transform",
                "ctf/mntr_srgb_identity.ctf",
            ],
            stdout="perf_mntr_srgb_identity.ctf.out",
            validations=[
                Validation(
                    type="FILE",
                    output="perf_mntr_srgb_identity.ctf.out",
                    abstol=1.6e-05,
                )
            ],
        ),
        Workload(
            args=[
                "--spec-validation-offset",
                "303",
                "--spec-validation-stride",
                "23",
                "--spec-validation-pixels",
                "133",
                "--bitdepths",
                "f32",
                "f32",
                "--iter",
                "20",
                "--8kres",
                "--test",
                "-1",
                "--transform",
                "clf/aces_to_video_with_look.clf",
            ],
            stdout="perf_aces_to_video_with_look.clf.out",
            validations=[
                Validation(
                    type="FILE",
                    output="perf_aces_to_video_with_look.clf.out",
                    abstol=3e-06,
                )
            ],
        ),
        Workload(
            args=[
                "--spec-validation-offset",
                "404",
                "--spec-validation-stride",
                "29",
                "--spec-validation-pixels",
                "134",
                "--bitdepths",
                "f32",
                "f32",
                "--iter",
                "25",
                "--test",
                "-1",
                "--transform",
                "clf/heavy_transform.clf",
            ],
            stdout="perf_heavy_transform.clf.out",
            validations=[
                Validation(
                    type="FILE", output="perf_heavy_transform.clf.out", abstol=2e-06
                )
            ],
        ),
    ],
    "737.gmsh_r": [
        Workload(
            args=["-option", "gmsh.opts", "-nt", "0", "choi.geo"],
            validations=[Validation(type="FILE", output="choi.val")],
        ),
        Workload(
            args=["-option", "gmsh.opts", "-nt", "0", "mediterranean.geo"],
            validations=[Validation(type="FILE", output="mediterranean.val")],
        ),
        Workload(
            args=["-option", "gmsh.opts", "-nt", "0", "projection.geo"],
            validations=[Validation(type="FILE", output="projection.val")],
        ),
        Workload(
            args=["-option", "gmsh.opts", "-nt", "0", "gasdis.geo"],
            validations=[Validation(type="FILE", output="gasdis.val")],
        ),
        Workload(
            args=["-option", "gmsh.opts", "-nt", "0", "Torus.geo"],
            validations=[Validation(type="FILE", output="Torus.val")],
        ),
        Workload(
            args=[
                "-option",
                "gmsh.opts",
                "-nt",
                "0",
                "spec.geo",
                "-clscale",
                "0.175",
                "-algo",
                "del2d",
                "-algo",
                "hxt",
            ],
            validations=[Validation(type="FILE", output="spec.val")],
        ),
        Workload(
            args=["-option", "gmsh.opts", "-nt", "0", "p19.geo"],
            validations=[Validation(type="FILE", output="p19.val")],
        ),
    ],
    "748.flightdm_r": [
        Workload(
            args=["--nohighlight", "scripts/weather-balloon2.xml"],
            stdout="weather-balloon2.xml.out",
            validations=[Validation(type="FILE", output="weather-balloon2.xml.out")],
        ),
        Workload(
            args=["--nohighlight", "scripts/B747_script1.xml"],
            stdout="B747_script1.xml.out",
            validations=[Validation(type="FILE", output="B747_script1.xml.out")],
        ),
        Workload(
            args=["--nohighlight", "scripts/x153.xml"],
            stdout="x153.xml.out",
            validations=[Validation(type="FILE", output="x153.xml.out")],
        ),
        Workload(
            args=["--nohighlight", "scripts/c3104.xml"],
            stdout="c3104.xml.out",
            validations=[Validation(type="FILE", output="c3104.xml.out")],
        ),
        Workload(
            args=["--nohighlight", "scripts/ah1s_flight_test.xml"],
            stdout="ah1s_flight_test.xml.out",
            validations=[Validation(type="FILE", output="ah1s_flight_test.xml.out")],
        ),
        Workload(
            args=["--nohighlight", "scripts/ball_orbit_g_torque.xml"],
            stdout="ball_orbit_g_torque.xml.out",
            validations=[Validation(type="FILE", output="ball_orbit_g_torque.xml.out")],
        ),
        Workload(
            args=["--nohighlight", "scripts/ball_orbit_g_torque2.xml"],
            stdout="ball_orbit_g_torque2.xml.out",
            validations=[
                Validation(type="FILE", output="ball_orbit_g_torque2.xml.out")
            ],
        ),
        Workload(
            args=["--nohighlight", "scripts/ball_orbit.xml"],
            stdout="ball_orbit.xml.out",
            validations=[Validation(type="FILE", output="ball_orbit.xml.out")],
        ),
    ],
    "749.fotonik3d_r": [
        Workload(
            args=[],
            validations=[
                Validation(type="FILE", output="pscyee.out", abstol=1e-26, reltol=1e-07)
            ],
        ),
    ],
    "765.roms_r": [
        Workload(
            args=[],
            stdin="roms_benchmark2.in.x",
            stdout="roms_benchmark2.log",
            validations=[Validation(type="FILE", output="roms_benchmark2.log")],
        ),
    ],
    "766.femflow_r": [
        Workload(
            args=["refrate.prm"],
            stdout="femflow.out",
            validations=[Validation(type="FILE", output="femflow.out")],
        ),
    ],
    "767.nest_r": [
        Workload(
            args=["cuba_stdp.sli"],
            stdout="cuba_stdp.sli.out",
            validations=[
                Validation(type="FILE", output="cuba_stdp.sli.out"),
                Validation(type="FILE", output="cuba_stdp-11253-0.dat"),
                Validation(type="FILE", output="cuba_stdp-11254-0.dat"),
            ],
        ),
        Workload(
            args=["structural_plasticity_benchmark.sli"],
            stdout="structural_plasticity_benchmark.sli.out",
            validations=[
                Validation(
                    type="FILE", output="structural_plasticity_benchmark.sli.out"
                ),
                Validation(type="FILE", output="spb_log_00.dat"),
                Validation(type="FILE", output="spike_recorder-6002-0.dat"),
            ],
        ),
        Workload(
            args=["ArtificialSynchrony.sli"],
            stdout="ArtificialSynchrony.sli.out",
            validations=[
                Validation(type="FILE", output="ArtificialSynchrony.sli.out"),
                Validation(type="FILE", output="voltmeter-Grid-0-129-0.dat"),
                Validation(type="FILE", output="voltmeter-Grid-1-129-0.dat"),
                Validation(type="FILE", output="voltmeter-Grid-2-129-0.dat"),
                Validation(type="FILE", output="voltmeter-Grid-3-129-0.dat"),
                Validation(type="FILE", output="voltmeter-Grid-4-129-0.dat"),
                Validation(type="FILE", output="voltmeter-Grid-5-129-0.dat"),
                Validation(type="FILE", output="voltmeter-Precise-0-129-0.dat"),
                Validation(type="FILE", output="voltmeter-Precise-1-129-0.dat"),
                Validation(type="FILE", output="voltmeter-Precise-2-129-0.dat"),
                Validation(type="FILE", output="voltmeter-Precise-3-129-0.dat"),
                Validation(type="FILE", output="voltmeter-Precise-4-129-0.dat"),
                Validation(type="FILE", output="voltmeter-Precise-5-129-0.dat"),
            ],
        ),
    ],
    "772.marian_r": [
        Workload(
            args=[
                "--cpu-threads",
                "1",
                "-m",
                "model.alphas.npz",
                "-v",
                "vocab.spm",
                "vocab.spm",
                "--beam-size",
                "1",
                "--mini-batch",
                "32",
                "--maxi-batch",
                "100",
                "--maxi-batch-sort",
                "src",
                "-w",
                "512",
                "--skip-cost",
                "--gemm-type",
                "intgemm8",
                "--intgemm-options",
                "precomputed-alpha",
                "standard-only",
                "--quiet",
                "--quiet-translation",
                "-i",
                "TildeMODEL-spec.en",
                "--log",
                "TildeMODEL-spec.log",
                "--log-level",
                "off",
                "-o",
                "TildeMODEL-spec.out",
            ],
            validations=[
                Validation(
                    type="CMD",
                    output="compare_TildeMODEL-spec.out.out",
                    cmd=[
                        "./text_compare",
                        "TildeMODEL-spec.out",
                        "compare/TildeMODEL-spec.out",
                    ],
                ),
            ],
        ),
        Workload(
            args=[
                "--cpu-threads",
                "1",
                "-m",
                "model.alphas.npz",
                "-v",
                "vocab.spm",
                "vocab.spm",
                "--beam-size",
                "1",
                "--mini-batch",
                "32",
                "--maxi-batch",
                "100",
                "--maxi-batch-sort",
                "src",
                "-w",
                "512",
                "--skip-cost",
                "--gemm-type",
                "intgemm8",
                "--intgemm-options",
                "precomputed-alpha",
                "standard-only",
                "--quiet",
                "--quiet-translation",
                "-i",
                "EuroPat-spec.en",
                "--log",
                "EuroPat-spec.log",
                "--log-level",
                "off",
                "-o",
                "EuroPat-spec.out",
            ],
            stdout="run_EuroPat-spec.out.out",
            validations=[
                Validation(
                    type="CMD",
                    output="compare_EuroPat-spec.out.out",
                    cmd=[
                        "./text_compare",
                        "EuroPat-spec.out",
                        "compare/EuroPat-spec.out",
                    ],
                ),
            ],
        ),
    ],
    "782.lbm_r": [
        Workload(
            args=["900", "reference.dat", "0", "0", "200_200_130_ldc.of"],
            stdout="lbm.out",
            validations=[Validation(type="FILE", output="lbm.out")],
        ),
    ],
}

# Benchmarks whose input files must be copied (not symlinked) into the run directory.
COPY_INPUTS = {"735.gem5_r", "777.zstd_r"}

# Benchmarks whose .xz files must be decompressed before running.
DECOMPRESS_XZ = {"734.vpr_r", "735.gem5_r", "749.fotonik3d_r"}


def link_inputs(src_dir, dst_dir, copy=False, decompress_xz=False):
    if not os.path.isdir(src_dir):
        return
    for name in os.listdir(src_dir):
        src = os.path.join(src_dir, name)
        dst = os.path.join(dst_dir, name)
        if name.endswith(".xz") and decompress_xz:
            dst = os.path.join(dst_dir, name[:-3])
            if os.path.exists(dst) or os.path.islink(dst):
                os.unlink(dst)
            with lzma.open(src) as f_in, open(dst, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
        elif copy and os.path.isdir(src):
            if os.path.exists(dst) or os.path.islink(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst, symlinks=True)
        elif copy and os.path.isfile(src) and not os.path.islink(src):
            shutil.copy2(src, dst)
        else:
            if os.path.exists(dst) or os.path.islink(dst):
                os.unlink(dst)
            os.symlink(src, dst)


def setup_run_dir(
    build_dir, bench_dir, config_tag, size, copy_inputs=False, decompress_xz=False
):
    run_tag = f"run_{size}_{config_tag}"
    run_dir = os.path.join(build_dir, "run", run_tag)
    os.makedirs(run_dir, exist_ok=True)

    link_inputs(
        os.path.join(bench_dir, "data", "all", "input"),
        run_dir,
        copy=copy_inputs,
        decompress_xz=decompress_xz,
    )
    link_inputs(
        os.path.join(bench_dir, "data", size, "input"),
        run_dir,
        copy=copy_inputs,
        decompress_xz=decompress_xz,
    )

    for size_dir in (
        os.path.join(bench_dir, "data", size),
        os.path.join(bench_dir, "data", "all"),
    ):
        compare_src = os.path.join(size_dir, "compare")
        if os.path.isdir(compare_src):
            compare_dst = os.path.join(run_dir, "compare")
            if not os.path.exists(compare_dst):
                os.symlink(compare_src, compare_dst)

    return run_dir


def compare_output(run_dir, ref_dir, fname, binary=False, abstol=None, reltol=None):
    ref_file = os.path.join(ref_dir, fname)
    if not os.path.exists(ref_file):
        return "no reference"

    out_file = os.path.join(run_dir, fname)
    if not os.path.exists(out_file):
        print(f"  DEBUG compare: {out_file} not found, run_dir={run_dir}", flush=True)
        return "missing output"

    if binary:
        import filecmp

        if filecmp.cmp(out_file, ref_file, shallow=False):
            return "pass"
        return "binary mismatch"

    with open(out_file) as f:
        out_lines = f.readlines()
    with open(ref_file) as f:
        ref_lines = f.readlines()

    if len(out_lines) != len(ref_lines):
        return f"line count mismatch ({len(out_lines)} vs {len(ref_lines)})"

    float_re = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")

    def extract_floats(s):
        return [float(m.group()) for m in float_re.finditer(s)]

    diffs = 0
    use_tol = abstol is not None or reltol is not None
    for i, (a, b) in enumerate(zip(out_lines, ref_lines)):
        a_s, b_s = a.strip(), b.strip()
        if use_tol:
            fa, fb = extract_floats(a_s), extract_floats(b_s)
            if fa and fb and len(fa) == len(fb):
                # compare non-numeric text parts
                text_a = float_re.sub("<>", a_s)
                text_b = float_re.sub("<>", b_s)
                if text_a != text_b:
                    diffs += 1
                    continue
                for va, vb in zip(fa, fb):
                    abs_diff = abs(va - vb)
                    if abs_diff <= (abstol if abstol is not None else 0):
                        continue
                    if reltol is not None:
                        denom = max(abs(va), abs(vb), 1e-300)
                        if abs_diff / denom <= reltol:
                            continue
                    diffs += 1
                    break
                continue
        if a_s != b_s:
            diffs += 1

    if diffs == 0:
        return "pass"
    return f"FAIL ({diffs} differing lines)"


def cmd_run(args):
    bench_dirs, bench_ids = resolve_benches(args)
    if bench_dirs is None:
        return 1
    if args.perf_record is not None and (
        args.perf_stat is not None or args.perf_stat_metrics is not None
    ):
        print(
            "Error: --perf-record is mutually exclusive with --perf-stat and --perf-stat-metrics",
            file=sys.stderr,
        )
        return 1
    config_tag = args.config or make_config_tag(args)
    copies = max(args.copies, 1)
    size = args.input_size
    exclusive = args.taskset_core is not None
    suite = args.suite
    if suite is None and bench_ids:
        suite = suite_for_bench(bench_ids[0])
    root = build_root(suite, config_tag)

    can_run = []
    no_data = []
    for d, bid in zip(bench_dirs, bench_ids):
        build_dir = os.path.join(root, bid)
        # Find the primary executable from subdirectories
        exe_path = None
        if os.path.isdir(build_dir):
            for entry in sorted(os.listdir(build_dir)):
                subdir = os.path.join(build_dir, entry)
                spec_path = os.path.join(subdir, "Makefile.spec")
                if not os.path.isdir(subdir) or not os.path.exists(spec_path):
                    continue
                cand = os.path.join(subdir, entry)
                if os.path.exists(cand):
                    exe_path = cand
                    break
                cand_exe = cand + ".exe"
                if os.path.exists(cand_exe):
                    exe_path = cand_exe
                    break
        if not exe_path:
            no_data.append((bid, "not built"))
            continue
        can_run.append((d, bid, exe_path, build_dir))

    print("=" * 72, flush=True)
    print(
        f"SPEC CPU 2026 Run (suite: {suite}, config: {config_tag}, size: {size})",
        flush=True,
    )
    print(f"  Copies: {copies}", flush=True)
    if exclusive:
        print(f"  Per-copy taskset: CPU {args.taskset_core}", flush=True)
    print("=" * 72, flush=True)
    print(flush=True)

    if no_data:
        print("Skipped:", flush=True)
        for bid, reason in no_data:
            print(f"  {bid}: {reason}", flush=True)
        print(flush=True)

    if not can_run:
        print("Nothing to run.", flush=True)
        print(
            "Place input data in:  benchspec/CPU/<benchmark>/data/<size>/input/",
            flush=True,
        )
        print(
            "Place reference in:   benchspec/CPU/<benchmark>/data/<size>/output/",
            flush=True,
        )
        print("Then run again with:  spec2026.py run <suite>", flush=True)
        return 0

    for d, bid, exe_path, build_dir in can_run:
        ref_dir = os.path.join(d, "data", size, "output")
        workloads = BENCH_WORKLOADS.get(bid, [])
        if not workloads:
            print(f"Skipping {bid}: no hardcoded workload definitions", flush=True)
            continue

        copy_inputs = bid in COPY_INPUTS
        decompress_xz = bid in DECOMPRESS_XZ
        run_dir = setup_run_dir(
            build_dir,
            d,
            config_tag,
            size,
            copy_inputs=copy_inputs,
            decompress_xz=decompress_xz,
        )
        print(
            f"--- {bid} ({len(workloads)} workloads, {copies} cop{'y' if copies == 1 else 'ies'}) ---",
            flush=True,
        )
        print(f"      run dir: {run_dir}", flush=True)

        log_path = os.path.join(run_dir, "run.log")
        log_file = open(log_path, "w")
        log_file.write(f"Benchmark: {bid}\n")
        log_file.write(f"Config:    {config_tag}\n")
        log_file.write(f"Input:     {size}\n")
        log_file.write(f"Copies:    {copies}\n")
        log_file.write(f"Run dir:   {run_dir}\n")
        log_file.write(f"Exe:       {exe_path}\n")
        log_file.write("\n")
        log_file.flush()

        per_copy_times = []
        all_ok = True
        validation = []
        for copy_idx in range(copies):
            copy_times = []
            prefix = []
            if exclusive:
                core = args.taskset_core + copy_idx
                prefix = ["taskset", "-c", str(core)]

            # Copy extra executables from subdirectories
            for entry in sorted(os.listdir(build_dir)):
                subdir = os.path.join(build_dir, entry)
                if not os.path.isdir(subdir):
                    continue
                spec_path = os.path.join(subdir, "Makefile.spec")
                if not os.path.exists(spec_path):
                    continue
                exe_path_in_sub = os.path.join(subdir, entry)
                if os.path.isfile(exe_path_in_sub):
                    exe_dst = os.path.join(run_dir, entry)
                    if not os.path.exists(exe_dst):
                        shutil.copy2(exe_path_in_sub, exe_dst)

            for wl_idx, wl in enumerate(workloads):
                exe_name = os.path.basename(exe_path)
                print(
                    f"  wl={wl_idx}: starting {exe_name} {' '.join(wl.args[:3])}...",
                    flush=True,
                )
                exe_dst = os.path.join(run_dir, exe_name)
                if not os.path.exists(exe_dst):
                    shutil.copy2(exe_path, exe_dst)
                cmd = [f"./{exe_name}"] + wl.args
                perf_name = f"perf-{bid}-wl{wl_idx}"
                if args.perf_record is not None:
                    perf_cmd = ["perf", "record", "-o", f"{perf_name}.data"]
                    if args.perf_record:
                        perf_cmd += ["-e", args.perf_record]
                    cmd = perf_cmd + cmd
                if args.perf_stat is not None or args.perf_stat_metrics is not None:
                    perf_cmd = ["perf", "stat", "-o", f"{perf_name}.stat"]
                    if args.perf_stat:
                        perf_cmd += ["-e", args.perf_stat]
                    if args.perf_stat_metrics:
                        perf_cmd += ["-M", args.perf_stat_metrics]
                    cmd = perf_cmd + cmd
                cmd = prefix + cmd
                start = time.monotonic()
                stdin_file = None
                stdin_handle = None
                if wl.stdin:
                    stdin_handle = open(os.path.join(run_dir, wl.stdin), "rb")
                    stdin_file = stdin_handle
                result = subprocess.run(
                    cmd, cwd=run_dir, capture_output=True, stdin=stdin_file
                )
                if stdin_handle:
                    stdin_handle.close()
                elapsed = time.monotonic() - start
                copy_times.append(elapsed)

                out_log = ""
                if wl.stdout:
                    out_path = os.path.join(run_dir, wl.stdout)
                    with open(out_path, "wb") as of:
                        of.write(result.stdout)
                    out_log = f" -> {wl.stdout}"

                wl_ok = result.returncode == 0
                okstr = "OK" if wl_ok else "FAIL"
                print(f"  wl={wl_idx}: {okstr} ({elapsed:.2f}s)", flush=True)
                if args.perf_record is not None:
                    print(
                        f"    perf-record: {os.path.join(run_dir, perf_name)}.data",
                        flush=True,
                    )
                if args.perf_stat is not None:
                    print(
                        f"    perf-stat: {os.path.join(run_dir, perf_name)}.stat",
                        flush=True,
                    )
                if not wl_ok:
                    all_ok = False
                    print(
                        f"  FAIL copy={copy_idx} wl={wl_idx}: exit={result.returncode} ({elapsed:.2f}s)",
                        flush=True,
                    )

                log_file.write(
                    f"  copy={copy_idx} wl={wl_idx}: {subprocess.list2cmdline(cmd)}\n"
                )
                log_file.write(f"    cwd={run_dir}{out_log}\n")
                log_file.write(f"    exit={result.returncode} elapsed={elapsed:.2f}s\n")
                log_file.flush()

                if wl_ok:
                    # Run CMD validations and validate all outputs
                    for v_idx, val in enumerate(wl.validations):
                        if val.type == "CMD":
                            print(
                                f"  wl={wl_idx}.{v_idx}: starting {' '.join(val.cmd[:4])}...",
                                flush=True,
                            )
                            sub_start = time.monotonic()
                            sub_result = subprocess.run(
                                val.cmd, cwd=run_dir, capture_output=True
                            )
                            sub_elapsed = time.monotonic() - sub_start
                            wl_sub_idx = f"{wl_idx}.{v_idx}"
                            out_path = os.path.join(run_dir, val.output)
                            with open(out_path, "wb") as of:
                                of.write(sub_result.stdout)
                            status = "OK" if sub_result.returncode == 0 else "FAIL"
                            print(
                                f"  wl={wl_sub_idx}: {status} ({sub_elapsed:.2f}s)",
                                flush=True,
                            )
                            if sub_result.returncode != 0:
                                all_ok = False
                                print(
                                    f"  FAIL copy={copy_idx} wl={wl_sub_idx}: exit={sub_result.returncode} ({sub_elapsed:.2f}s)",
                                    flush=True,
                                )
                            log_file.write(
                                f"  copy={copy_idx} wl={wl_sub_idx}: {subprocess.list2cmdline(val.cmd)}\n"
                            )
                            log_file.write(f"    cwd={run_dir}{out_log}\n")
                            log_file.write(
                                f"    exit={sub_result.returncode} elapsed={sub_elapsed:.2f}s {status}\n"
                            )
                            log_file.flush()

                    for val in wl.validations:
                        r = compare_output(
                            run_dir,
                            ref_dir,
                            val.output,
                            binary=(val.type == "BIN-FILE"),
                            abstol=val.abstol,
                            reltol=val.reltol,
                        )
                        if r == "pass":
                            print(f"  VALIDATE {val.output}: pass", flush=True)
                        elif r == "no reference":
                            print(f"  VALIDATE {val.output}: no reference", flush=True)
                        else:
                            all_ok = False
                            print(f"  VALIDATE {val.output}: {r}", flush=True)
                        validation.append((val.output, r))
                elif wl.validations:
                    for val in wl.validations:
                        validation.append((val.output, "no reference"))

            total = sum(copy_times)
            per_copy_times.append(total)
            wl_detail = ", ".join(
                f"wl{wl_idx}={t:.2f}s" for wl_idx, t in enumerate(copy_times)
            )
            status = "OK" if all_ok else "FAIL"
            log_file.write(
                f"  Copy {copy_idx}: {total:.2f}s total [{wl_detail}] {status}\n"
            )
            log_file.flush()
            print(
                f"  Copy {copy_idx}: {total:.2f}s total [{wl_detail}] {status}",
                flush=True,
            )

        if copies > 1 and per_copy_times:
            mx = max(per_copy_times)
            mn = min(per_copy_times)
            spread = ((mx / mn) - 1) * 100 if mn > 0 else 0
            log_file.write(
                f"  Rate: max_copy={mx:.2f}s min_copy={mn:.2f}s spread={spread:.1f}%\n"
            )
            log_file.flush()
            print(f"  Rate: max_copy={mx:.2f}s min_copy={mn:.2f}s spread={spread:.1f}%")
        if validation:
            passed = sum(1 for _, r in validation if r == "pass")
            no_ref = sum(1 for _, r in validation if r == "no reference")
            log_file.write(f"Validation: {passed} passed, {no_ref} no reference\n")
            log_file.flush()

        log_file.close()
        print()

    summary = []
    summary.append(f"Suite:     {suite}")
    summary.append(f"Config:    {config_tag}")
    summary.append(f"Input:     {size}")
    summary.append(f"Started:   {time.strftime('%Y-%m-%d %H:%M:%S')}")
    summary.append("")
    for d, bid, exe_path, build_dir in can_run:
        run_dir = os.path.join(build_dir, "run", f"run_{size}_{config_tag}")
        log_path = os.path.join(run_dir, "run.log")
        if os.path.exists(log_path):
            with open(log_path) as lf:
                for line in lf:
                    if line.startswith("Validation") or line.startswith("  Copy 0:"):
                        summary.append(f"  {bid}: {line.strip()}")
    summary.append("")
    summary.append(f"End:       {time.strftime('%Y-%m-%d %H:%M:%S')}")
    summary_path = os.path.join(root, f"run_{size}_{config_tag}.log")
    with open(summary_path, "a") as sf:
        sf.write("\n".join(summary) + "\n")

    print("All benchmarks completed.")
    return 0


# ---------------------------------------------------------------------------
# Clean
# ---------------------------------------------------------------------------


def add_clean_args(p):
    p.add_argument(
        "suite",
        nargs="?",
        choices=SUITE_CHOICES,
        help="Benchmark suite (optional; cleans all suites if omitted)",
    )
    p.add_argument("--config", default=None, help="Config to clean (default: auto)")
    p.add_argument("--cc", default="gcc", help="C compiler (for auto config name)")
    p.add_argument("--opt", default="-O3", help="Opt flags (for auto config name)")


def cmd_clean(args):
    config_tag = args.config or make_config_tag(args)
    if args.suite:
        dirs = [build_root(args.suite, config_tag)]
    else:
        dirs = []
        for suite in os.listdir(BUILD_BASE):
            d = os.path.join(BUILD_BASE, suite, config_tag)
            if os.path.isdir(d):
                dirs.append(d)

    if not dirs:
        print(f"  Nothing to clean (no {config_tag} builds found)")
        return 0

    for d in dirs:
        shutil.rmtree(d)
        print(f"  Removed {d}/")
    return 0


# ---------------------------------------------------------------------------
# List commands
# ---------------------------------------------------------------------------


def cmd_list(args):
    for entry in sorted(os.listdir(CPU)):
        if re.match(r"^\d+\.[a-zA-Z]", entry):
            print(entry)
    return 0


def cmd_list_sets(args):
    for name, info in BSETS.items():
        bset_path = os.path.join(CPU, info["file"])
        if os.path.exists(bset_path):
            print(f"{name} ({info['desc']}):")
            for b in parse_bset(name):
                print(f"  {b}")
    return 0


def cmd_list_configs(args):
    if not os.path.isdir(BUILD_BASE):
        print("No build configs found.")
        return 0
    for suite in sorted(os.listdir(BUILD_BASE)):
        suite_dir = os.path.join(BUILD_BASE, suite)
        if not os.path.isdir(suite_dir) or suite.startswith("."):
            continue
        for cfg in sorted(os.listdir(suite_dir)):
            cfg_dir = os.path.join(suite_dir, cfg)
            if os.path.isdir(cfg_dir):
                benches = sorted(os.listdir(cfg_dir))
                print(f"{suite}/{cfg}/  ({len(benches)} benchmarks)")
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    p = argparse.ArgumentParser(description="SPEC CPU 2026 build and run tool")
    sub = p.add_subparsers(dest="command", required=True)

    bp = sub.add_parser("build", help="Build benchmarks")
    add_build_args(bp)

    rp = sub.add_parser("run", help="Run benchmarks")
    add_run_args(rp)

    cp = sub.add_parser("clean", help="Clean build artifacts")
    add_clean_args(cp)

    lp = sub.add_parser("list", help="List all benchmarks")
    lp.set_defaults(func=cmd_list)

    lsp = sub.add_parser("list-sets", help="List benchmark sets")
    lsp.set_defaults(func=cmd_list_sets)

    lcp = sub.add_parser("list-configs", help="List existing build configs")
    lcp.set_defaults(func=cmd_list_configs)

    args = p.parse_args()

    if args.command == "build":
        return cmd_build(args)
    elif args.command == "run":
        return cmd_run(args)
    elif args.command == "clean":
        return cmd_clean(args)
    elif hasattr(args, "func"):
        return args.func(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
