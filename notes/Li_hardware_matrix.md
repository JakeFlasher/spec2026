# Li et al. Hardware Matrix and RRR Feasibility

## Answer

Li et al. used nine dual-socket server machines (24-80 cores/socket, 64 GB-768 GB DRAM/socket), but DRAM capacity is not what makes RRR research feasible or infeasible on the consumer boxes. Per-copy footprint is, and rate-class RRR fits comfortably in 32 GB at the target copy counts. The genuine consumer-vs-server gap is memory bandwidth and channel count, not capacity.

## Li et al.'s Hardware Matrix

Table 2 of the paper reports the following per-socket configurations. All machines are dual-socket.

| Machine | CPU | Cores/socket | DRAM/socket | GB/core |
| --- | --- | ---: | --- | ---: |
| CPU-A | Intel Skylake Platinum 8160 | 24 | 96 GB DDR4 | 4.0 |
| CPU-B | Intel Icelake Platinum 8380 | 40 | 128 GB DDR4 | 3.2 |
| CPU-C | Intel Sapphire Rapids Platinum 8468 | 48 | 768 GB DDR5 | 16.0 |
| CPU-D | Intel Sapphire Rapids MAX 9480 | 56 | 64 GB HBM2e | 1.14 |
| CPU-E | AMD Milan EPYC 7763 | 64 | 128 GB DDR4 | 2.0 |
| CPU-F | AMD Genoa EPYC 9454 | 48 | 192 GB DDR5 | 4.0 |
| CPU-G | AMD Turin EPYC 9555 | 64 | 512 GB DDR5 | 8.0 |
| CPU-H | Ampere Altra (Neoverse-N1) | 80 | 128 GB DDR4 | 1.6 |
| CPU-I | Nvidia Grace (Neoverse-V2) | 72 | 224 GB LPDDR5 | 3.1 |

Their roster goes down to 1.14-1.6 GB/core for the HBM-capped SPR MAX and the Altra. The 9955HX at 32 GB / 16 cores is 2.0 GB/core, identical to their Milan ratio.

## Footprint Arithmetic for RRR Runs

The paper measures CPU2026 Rate per-copy resident footprint at max ~2.2 GB and median ~1.4 GB, compared with CPU2017's 1.7 GB max and 0.8 GB median. This is consistent with the committee's "~2 GB/copy" rule for SPECrate. Li et al.'s RRR proof-of-concept, using `709.cactus_r` and `749.fotonik3d_r`, used rate benchmarks only. The local AMD box has 30 GiB usable according to `free -h`.

- Hero configuration (8 copies, equal across vendors): worst case 8 x 2.2 GB ~= 17.6 GB, which fits with more than 10 GB headroom. Median-footprint mixes are approximately 11 GB.
- 16-copy worst-case mixes: 35 GB > 30 GiB, which would swap and invalidate the run. Do not run full-16-copy mixes containing the largest-footprint benchmarks on this box. The hero does not need them because equal-copies = 8, matching the 12900's 8 P-cores.
- Speed-class constituents are the real capacity hazard. The 52-benchmark space nominally includes the speed suites, and `fpspeed` runs to ~49 GB RSS with a committee requirement of 64 GB. Replicating a speed benchmark across copies is infeasible on 32 GB, and on most of Li et al.'s servers too. Practical consequence: mixes stay rate-class, as Li's proof of concept did, or the mixture sampler gets an explicit per-node feasibility filter:

  ```text
  copies * max_RSS(subset) + OS_headroom <= usable_RAM
  ```

  Infeasible mixes should be excluded and logged, not silently dropped.

- Run-validity gate: the box has 94 GB swap, and any swap activity mid-run corrupts timing. `vmstat` `si`/`so` must be 0 for a run to count, which slots into the existing CV/statistics gating.

## What the Server Gap Actually Is

Capacity-wise, the consumer boxes are inside Li et al.'s own envelope. What they cannot match is channels: Li et al.'s machines have 8-12 DDR channels per socket, while consumer parts have 2. Their prefetcher study quotes 25.6 GB/s per channel at 3200 MT/s.

That means more bandwidth contention per core on the consumer boxes, which helps produce the ranking inversions the hero needs and is already the documented threat to validity: contention regime stated, server-class uncore as future work. The consumer constraint cuts in favor of finding the phenomenon and is honestly reportable.

## Knowledge Consulted

- `spec2026.pdf` (Li et al., arXiv 2605.03713): Table 2 hardware configurations, RSS footprint findings in the memory analysis section, and RRR proxy section, extracted via `pdftotext`
- `.claude/memory/rrr_scoring_open_problem.md`: committee footprint facts; SPECrate ~2 GB/copy, SPECspeed 16 -> 64 GB
- `~/.claude/.../memory/amd-node-bringup-march-pin.md`: `fpspeed` ~49 GB RSS and equal-copies/8-P-core discipline
- `.claude/skills/cpu-arch-history/SKILL.md`: Li et al. roster cross-check
- Local `free -h` on the AMD node: 30 GiB usable, 94 GB swap
