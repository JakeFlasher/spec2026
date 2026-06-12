# RRR-Forge — Research Goal, Gap, Challenges, and Contributions

**Status:** authoritative as of 2026-06-12; reflects the top-tier pivot (2026-06-09) *as
amended by* the descope (2026-06-10). If anything here conflicts with
`.claude/memory/descope_2026-06-10.md`, the descope wins.
**Venue target:** MICRO 2027 (primary), HPCA 2027 (secondary); ISPASS/CAL fallback for a
metric-only slice. **Hardware matrix:** exactly 1 Intel (i9-12900, P-cores) + 1 AMD
(Ryzen 9 9955HX), both x86_64, identical `-march=x86-64-v3` pinned binaries (DEC-7).

---

## 1. Ultimate goal — one sentence

> **Establish a principled, vendor-invariant scoring methodology for SPEC CPU2026's
> Rolling Round-Robin (RRR) mode — by formalizing, exposing, mechanistically explaining,
> and then correcting the vendor-dependence of *realized co-run work* under RRR's
> deterministic rotation — thereby answering SPEC's own open call for an RRR metric.**

The deliverable the community adopts is the corrected aggregate; the intellectual
contribution a top-tier PC rewards is the phenomenon + mechanism underneath it. A metric
alone is a letters-venue paper; a surprising, mechanism-explained measurement pathology
with a fix is an architecture-conference paper. We are building the second.

---

## 2. Background — what RRR is and the property everything rests on

SPEC CPU2026 ships RRR as an *exhibition* (non-reportable) mode: N copies each execute the
full benchmark roster in a fixed order, staggered by starting offset; SPEC publishes raw
standardized execution data and **deliberately ships no score** — the committee states the
scoring methodology "is not well-established" and issues an open call over the candidate
space {cumulative IPC, average throughput, harmonic mean, fairness indices}
(Madhav et al., ISCA 2026, arXiv 2605.01575).

```
   RRR full rotation — roster ⟨A,B,C,D⟩, 4 copies, rrrrate_inc = 1
   ──────────────────────────────────────────────────────────────────
   copy 0:   A → B → C → D
   copy 1:   B → C → D → A        copy i starts at roster index (i mod 4),
   copy 2:   C → D → A → B        no synchronization between copies
   copy 3:   D → A → B → C
   ──────────────────────────────────────────────────────────────────
   Every copy retires every benchmark exactly once.
   With identical pinned binaries on a same-ISA vendor pair, the retired
   instruction count per benchmark is EQUAL across copies AND across
   vendors  ⇒  icount is a legitimate, vendor-neutral reference-work unit.
```

The load-bearing refinement (committee-paper-confirmed): the equal-work guarantee holds
**only for the full rotation**. In the *proxy regime* — k < N subsets, copies ≠ N,
`rrrrate_inc ≠ 1`, i.e. exactly the regime that makes RRR useful as a multiprogrammed
proxy generator (cf. Li et al.'s hand-built `709.cactus_r + 749.fotonik3d_r ≈
DCPerf-django`, 13.7% IPC gap) — the equality of *realized co-run overlap* breaks.
That breakdown is not a bug to engineer around; **it is the object of study.**

---

## 3. The research gap

Four bodies of prior work each supply one piece and miss the same seam:

```
  ┌──────────────────────────────┬───────────────────────────┬──────────────────────────────┐
  │ Prior art                    │ Provides                  │ Missing                      │
  ├──────────────────────────────┼───────────────────────────┼──────────────────────────────┤
  │ SPEC committee, ISCA 2026    │ RRR mode itself; raw      │ the metric — an explicitly   │
  │ (arXiv 2605.01575)           │ standardized run data     │ EMPTY slot + open call       │
  ├──────────────────────────────┼───────────────────────────┼──────────────────────────────┤
  │ Li et al. 2026               │ first CPU2026 character-  │ metric model; cross-vendor   │
  │ (arXiv 2605.03713)           │ ization; one hand-built   │ aggregate analysis; any      │
  │                              │ RRR proxy; black-box perf │ mechanism attribution        │
  ├──────────────────────────────┼───────────────────────────┼──────────────────────────────┤
  │ STP / ANTT                   │ the principled multi-     │ schedule model: assumes      │
  │ (Eyerman–Eeckhout, 2008)     │ program throughput +      │ generic co-run, no           │
  │                              │ fairness metric pair      │ deterministic rotation       │
  ├──────────────────────────────┼───────────────────────────┼──────────────────────────────┤
  │ TPEX (Eyerman–Michaud–       │ "a metric IS its          │ instantiated ONLY for a      │
  │ Rogiest, TACO 2014)          │ assumptions" theory of    │ RANDOM scheduler — never     │
  │                              │ throughput experiments    │ for a fixed rotation         │
  └──────────────────────────────┴───────────────────────────┴──────────────────────────────┘
```

The seam all four miss: **RRR's schedule is fixed and deterministic, so the realized
overlap pattern per rotation offset is analytically known — and nobody has asked what
happens to that pattern, and to every aggregate built on top of it, when the same schedule
runs on two different microarchitectures.** TPEX's own theorem (different assumptions ⇒
different metrics ⇒ rankings can flip) predicts trouble; no one has instantiated the
deterministic-rotation case, measured the trouble, explained it, or fixed it.

This gap is *SPEC-sanctioned* (the open call), *timely* (CPU2026 released 2026-05), and
*defensible* (it needs a granted SPEC license, a controlled two-vendor matrix, and
metric-theory depth that the black-box characterization groups have not shown).

---

## 4. The hero claim and its causal chain

> On a same-ISA, identical-binary two-vendor matrix, RRR's full rotation IS equal-work in
> instructions on both vendors — but in the proxy regime the deterministic rotation's
> **realized co-run overlap pattern is vendor-dependent**, so any time-based aggregate
> implicitly weights constituent benchmarks differently per vendor, co-runner rankings
> **invert across vendors**, and an **equal-reference-work (icount-anchored) +
> ANTT-fairness** aggregate restores vendor-invariant rankings.

Why overlap diverges even though instructions don't — the heart of the paper:

```
  Mixture {F = front-end-bound, M = memory-bound}, 2 copies, staggered start.
  Retired instructions per benchmark are IDENTICAL on both vendors.

  VENDOR X   (μarch runs F relatively fast)
  time ──────────────────────────────────────────────►
  copy 0 │ F ███████      │ M ███████████████████ │
  copy 1 │ M ███████████████████ │ F ███████      │
               └─────────┘
           F's entire lifetime co-runs against M        exposure(F vs M): HIGH

  VENDOR Y   (μarch narrows the F:M speed gap)
  time ──────────────────────────────────────────────►
  copy 0 │ F ██████████████ │ M ████████████████ │
  copy 1 │ M ████████████████ │ F ██████████████ │
                            └────┘
           F outlives M's window; its tail co-runs      exposure(F vs M): LOWER
           against the other copy's F                   exposure(F vs F): APPEARS

  Same schedule. Same instructions. Different WHO-RAN-AGAINST-WHOM matrices.
  Every time-weighted aggregate inherits its vendor's overlap matrix as a set
  of hidden, vendor-specific per-benchmark weights.
```

The full causal chain, with the contribution that owns each link:

```
   identical pinned binaries + same RRR schedule on vendors X and Y
                              │
                              ▼
   relative per-benchmark speeds differ        (μarch only: Golden-Cove-class
                              │                 front-end vs Zen-class memory
                              ▼                 subsystem — ISA confound REMOVED)
   realized co-run overlap pattern diverges ──────────────►  C1 formalizes
                              │                              C2 measures
                              ▼
   time-based aggregates weight constituents
   differently per vendor (hidden weights)
                              │
                              ▼
   co-runner rankings INVERT across vendors ──────────────►  C2 evidences
   under {cumulative IPC, throughput, h-mean}                (bootstrap-gated,
                              │                               class-systematic)
                              ├───────────────────────────►  C3 explains
                              ▼                              (PEBS / IBS)
   equal-reference-work (icount) + ANTT aggregate,
   with closed-form staggered-tail-bias correction ───────►  C4 corrects
   restores vendor-invariant rankings                        (answers the
                                                              SPEC open call)
```

---

## 5. Challenges — and how each is met

1. **"A metric is a letter, not a paper."** The STP/ANTT/Michaud lineage lives at
   CAL/IEEE-Micro. *Met by:* the metric is the lens; the headline is the phenomenon
   (vendor-dependent realized work) plus its PEBS/IBS mechanism. Venue-fit recipe shapes
   1 + 2 simultaneously.
2. **The 12-year unresolved metric dispute** (Michaud vs Eyerman–Eeckhout on weighted-IPC
   metrics). *Met by:* never claiming a uniqueness or non-gameability theorem; the two
   positions are used as endpoints of a sensitivity/invariance analysis, and we show what
   RRR's deterministic schedule does to each.
3. **Generalizing from two nodes.** A 2-machine result can be an anecdote. *Met by:*
   cross-vendor claims reported as hypothesis tests with calibrated/conformal uncertainty
   (DEC-9); inversions must be systematic and model-predicted across a benchmark *class*,
   not one mix on one machine; a clean mechanism-explained negative is itself publishable.
4. **Measurement rigor on consumer-class hardware.** The matrix is a mobile Zen 5 part +
   a hybrid Alder Lake part. *Met by:* P-core-only binding, equal copies per vendor, SMT
   siblings idle, frequency-residency manifests, CV gating with run-count escalation,
   bootstrap CIs on every claimed flip. Same cores as the server parts (Golden Cove,
   Zen 5) — the uncore difference is stated as a threat to validity, never hidden.
5. **Mechanism needs facilities clouds don't rent.** Precise sampling (IBS/PEBS) and
   uncore counters exist only on bare metal — see
   `spec2026/notes/rented_node_pmu_qualification.md`. *Met by:* local bare-metal pair as
   the spine; rented VMs at most contribute profile-grade supplementary data.
6. **Scoop risk.** An open call invites everyone. *Met by:* the license + two-vendor +
   metric-theory barrier to entry; the parked co-run CV-model card is retained purely as
   a scooped-vs-novel guard; the standing action item is a periodic scoop-check on
   arXiv 2605.01575 responders.
7. **Resources.** The 2026-06-10 descope is binding: no energy/carbon, no ARM/cross-ISA,
   no agentic-AI targets, no standalone interference table, no predictive CV model.
   One direction, executed deeply, beats five executed thinly.

---

## 6. Contributions

```
        ┌────────────────────────────────────────────────────────────┐
        │  C4   CORRECTION — equal-reference-work (icount-anchored)  │
        │       + ANTT-fairness aggregate, closed-form staggered-    │
        │       tail-bias term; validated predicted-vs-measured on   │
        │       held-out mixes; rank-stability restored              │
        │       ⇒ the artifact the community adopts; answers the     │
        │         SPEC open call as a corollary                      │
        ├────────────────────────────────────────────────────────────┤
        │  C3   MECHANISM — PEBS/IBS attribution of the inversion    │
        │       cases (front-end vs memory-subsystem sensitivity),   │
        │       underwritten by an Intel↔AMD PMU equivalence-class   │
        │       methodology (bias direction, never correction        │
        │       factors)                                             │
        │       ⇒ what lifts the paper above characterization        │
        ├────────────────────────────────────────────────────────────┤
        │  C2   PHENOMENON — measured vendor-divergence of realized  │
        │       co-run exposure on real RRR runs (k = 2..6,          │
        │       cluster-stratified mixes); bootstrap-CI-gated        │
        │       ranking inversions, systematic across a benchmark    │
        │       class and predicted by the overlap model             │
        │       ⇒ the surprising insight                             │
        ├────────────────────────────────────────────────────────────┤
        │  C1   FORMALIZATION — RRR's deterministic rotation as an   │
        │       equal-work generator: equal-icount holds for the     │
        │       full rotation on a same-ISA pair; the proxy regime   │
        │       provably breaks realized-overlap equality; the       │
        │       per-offset overlap pattern is analytically derived   │
        │       ⇒ the lens (and the TPEX regime never instantiated)  │
        └────────────────────────────────────────────────────────────┘
          supporting substrate (not a headline): the C(52,k) cluster-
          stratified mixture sampler + time-weighted PCA scorer, demoted
          to the validation-workload generator that produces diverse,
          controlled staggered mixes for C2/C4.
```

Positioning against the adjacent lineages (likely reviewers own these):

```
   Eyerman–Eeckhout 2008          Eyerman–Michaud–Rogiest 2014
   STP / ANTT metric pair         TPEX: metric = its assumptions
        │   adopted as the              │   random scheduler only
        │   governing pair              │
        └───────────────┬──────────────┘
                        ▼
        THIS WORK — deterministic-rotation regime:
        per-offset overlap analytically known; its
        vendor-dependence exposed (C1–C2), explained
        (C3), and corrected (C4)
                        ▲
        ┌───────────────┴──────────────┐
        │   black-box, one raw IPC,    │   metric-less by design,
        │   no metric model            │   literal open call
   Li et al. 2026                 SPEC committee, ISCA 2026
   (characterization + 1 proxy)   (arXiv 2605.01575)
```

---

## 7. Explicit non-claims (framing rules — violating these costs the paper)

- RRR outputs are **research-mode workload synthesis**, never SPECrate/SPECspeed ratios
  (run rules; RRR is non-reportable).
- No "axiomatically correct / uniqueness / non-gameability" language — *sensitivity and
  invariance analysis* only.
- The geomean-speedup critique (Eeckhout CAL 2024 / ISPASS 2025) is motivation-only: it is
  single-system *speedup*, the wrong lineage for multiprogram *throughput*.
- Cross-ISA icount sensitivity (Li et al.'s 0.72×–1.51× range; the
  `750.sealcrypto_r`/`707.ntest_r` AArch64 extremes) is motivation and future work — never
  an experimental lever (descope).
- Compiler sensitivity (gcc-15 vs gcc-13 ≈ 17.7% icount; `706.stockfish_r` up to ~3×) is a
  held-fixed control (DEC-7), never a lever — do not conflate the compiler axis with the
  vendor axis.
- No coverage claims over the ≈23.25M-combination mixture space; the sampler is a
  stratified generator, not an exhaustive search.

---

## 8. Experiment spine (pointer)

Formalize (C1) → solo PMU vectors + real `--rrrrate`/`--rrrrate_inc` mixes on the
two-vendor matrix → quantify per-mix realized co-run exposure divergence (C2) → identify
bootstrap-gated ranking inversions, front-end-bound × memory-bound pairs (e.g.
`721.gcc_r`/`723.llvm_r` × `749.fotonik3d_r`) → PEBS/IBS mechanism cases (C3) → corrective
aggregate + held-out validation (C4) → DCPerf-django as the sole external validation
anchor (reproduces Li et al.'s proxy). Full spine with controls:
`.claude/knowledge/rrr/rrr-cross-vendor-equal-work.md`.

---

## 9. References

Project knowledge base (authoritative):
- `.claude/memory/descope_2026-06-10.md` — binding scope record
- `.claude/memory/top_tier_pivot.md` — venue pivot rationale
- `.claude/memory/rrr_scoring_open_problem.md` — the SPEC open call, RRR mechanics refinement
- `.claude/knowledge/rrr/rrr-cross-vendor-equal-work.md` — hero claim + experiment spine
- `.claude/knowledge/rrr/multiprogram-throughput-metrics-stp-antt-tpex.md` — governing metric lineage
- `.claude/knowledge/workload-characterization/top-tier-venue-fit-recipe.md` — the bar this note is written against
- `spec2026/notes/rented_node_pmu_qualification.md` — measurement-substrate qualification

External:
- Madhav et al., "SPEC CPU: The Next Generation," ISCA 2026 — https://arxiv.org/abs/2605.01575
- Li et al., "SPEC CPU2026: Characterization…," arXiv 2026 — https://arxiv.org/abs/2605.03713
- Eyerman & Eeckhout, "System-Level Performance Metrics for Multiprogram Workloads," IEEE Micro 2008 — https://ieeexplore.ieee.org/document/4550859
- Eyerman, Michaud, Rogiest, "Revisiting Symbiotic Job Scheduling… (TPEX)," TACO 2014 — https://hal.science/hal-01087743
- Michaud, "Demystifying Multicore Throughput Metrics," CAL 2013 — https://dl.acm.org/doi/10.1109/L-CA.2013.9
- Gohil & Delimitrou (generalizability/OOD bar for cross-system claims), HPCA 2025 — https://people.csail.mit.edu/delimitrou/papers/2024.cal.generalizability.pdf
