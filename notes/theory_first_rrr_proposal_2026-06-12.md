# From Exhibition to Score: An Axiomatic and Algorithmic Theory of RRR Scoring
## Research Proposal — Theory-First Pivot (codified 2026-06-12)

**Status.** ADOPTED as the project's single active direction on 2026-06-12 (user decision).
Supersedes the empirical-first hero of `descope_2026-06-10` / `top_tier_pivot` (the *content*
of that hero survives; its *burden of proof* and venue targeting do not). Authoritative scope
record: `.claude/memory/theory_first_pivot_2026-06-12.md`. **Implementation plan** (refines
§7's workstreams into ACs, milestones, a 27-task table, and DEC gates, incorporating the
2026-06-12 execution research on RRR instrumentation, repo reuse, and Lean/Z3 engineering):
`.humanize/plans/rrr-forge-plan-v2-theory-first.md`.

**Audience.** Workers in other Claude sessions and the human researcher. This note is
self-contained: it states the claim, the theorems, the machinery, the minimal empirical
plan, the venue strategy with verified deadlines, and the risks. Companion notes:
`research_goal_gap_contributions.md` (the pre-pivot framing, now historical),
`rented_node_pmu_qualification.md` (node qualification — mostly moot under this pivot),
`Li_hardware_matrix.md` (why consumer DRAM suffices).

---

## 0. Executive summary

SPEC CPU2026 ships its multiprogrammed Rolling Round-Robin (RRR) mode in *exhibition*
status with **no official metric** — the committee states scoring "is not well-established"
and issues an open call (Madhav et al., ISCA 2026, arXiv 2605.01575). As of 2026-06-12 the
scoring design space is publicly untouched (exhaustive scoop check: exactly two papers
mention SPEC CPU2026; both have zero citations).

We answer the open call with a **theorem-first** paper:

> **Hero claim.** RRR scoring admits a complete information-theoretic resolution. We prove
> that no aggregate computed from wall-clock segment times alone can be machine-invariant
> while satisfying the desiderata existing metrics individually promise (**impossibility**,
> T4); that admitting one extra datum — per-benchmark reference instruction work — restores
> possibility; and that the icount-anchored, tail-bias-corrected ANTT-style aggregate is the
> **unique** such metric up to monotone transform (**characterization**, T5). The supporting
> theory (T1–T3) formalizes RRR as a deterministic cyclic co-schedule with
> contention-endogenous durations, proves steady-state existence via nonlinear
> Perron–Frobenius theory, and proves that distinct machines generically induce distinct
> overlap weights. Two consumer desktops (1 Intel + 1 AMD, identical pinned x86-64-v3
> binaries) serve as **witnesses**, not as the evidence base.

Why this is the right shape for the available resources:

```
        OLD HERO (MICRO/HPCA, empirical-first)      NEW HERO (TACO/SIGMETRICS, theorem-first)
  ┌──────────────────────────────────────────┐  ┌──────────────────────────────────────────┐
  │ CLAIM  rankings invert on real vendors   │  │ CLAIM  theorems T1–T5 (about ALL machines)│
  │ PROOF  measurements; breadth = validity  │  │ PROOF  mathematics; machines = witnesses  │
  │                                          │  │                                          │
  │ 2 consumer boxes = WEAKNESS              │  │ 2 consumer boxes = SUFFICIENT             │
  │ ("does it generalize beyond n = 2?")     │  │ (existence needs n = 1; invariance        │
  │                                          │  │  is proved, not sampled)                  │
  │ needs: server fleet, IBS/PEBS mechanism  │  │ needs: solo runtimes, icount audits,      │
  │ campaign, large mix sweep                │  │ a few dozen theory-selected mixes         │
  └──────────────────────────────────────────┘  └──────────────────────────────────────────┘
```

The pivot inverts the reviewer attack surface: under the old framing, two machines invite
"insufficient evaluation"; under the new framing, the theorems are machine-agnostic and the
empirical section only has to **exhibit** the predicted phenomena (an existence claim, for
which n = 1 suffices) and **instantiate** the corrected metric.

---

## 1. The object of study: RRR as a deterministic cyclic co-schedule

RRR runs N copies on N cores. Each copy walks the same ordered benchmark roster; copy *i*
starts at roster index *i·inc mod |R|* (`--rrrrate_inc`). The schedule is deterministic;
the *durations* are not — each segment's duration depends on which benchmarks co-run with
it, which depends on alignment, which depends on durations. That coupling is the entire
subject.

```
  Roster R = ⟨B0, B1, B2, B3⟩,  copies = 4,  inc = 1   (full rotation)

  copy 0:  │ B0 ███████ │ B1 ███ │ B2 █████████ │ B3 ████ │
  copy 1:  │ B1 ███ │ B2 █████████ │ B3 ████ │ B0 ███████ │
  copy 2:  │ B2 █████████ │ B3 ████ │ B0 ███████ │ B1 ███ │
  copy 3:  │ B3 ████ │ B0 ███████ │ B1 ███ │ B2 █████████ │
            t ────────────────────────────────────────────▶

  Full rotation: every copy runs every benchmark once
                 ⇒ per-benchmark incidence is EQUAL (T1, provable).
  Proxy regime (k < N subsets, copies ≠ N, inc ≠ 1):
                 equal incidence breaks; realized OVERLAP becomes the object.
```

The cross-vendor divergence that motivates everything (same schedule, same pinned binaries,
equal total icount per rotation — different co-run exposure):

```
        VENDOR I (Intel, same binaries)        VENDOR A (AMD, same binaries)
  copy0 │ B0 ████████│ B1 ██│ B2 ██████│       │ B0 █████│ B1 ████│ B2 ███████│
  copy1 │ B1 ██│ B2 ██████│ B3 ███│             │ B1 ████│ B2 ███████│ B3 ██│
         ──────────────────────────▶ t            ──────────────────────────▶ t
         relative per-benchmark speeds differ between microarchitectures
                       ⇓
         realized overlap matrices Φ_I ≠ Φ_A          (generically — T3)
                       ⇓
         time-based aggregates carry hidden,
         vendor-specific constituent weights          (T4's premise)
```

---

## 2. Provability map (refined)

The decomposition of the claim into provable and empirical fragments, with two corrections
relative to the first draft (rows 3 and 9):

| # | Claim fragment | Status | Engine |
|---|---|---|---|
| 1 | RRR schedule is deterministic; full rotation gives equal benchmark incidence | **Theorem** (T1) | combinatorics of the rotation |
| 2 | Same binary + reference input ⇒ equal intended instruction work | **Conditional theorem + PMU audit** | same-ISA pin (DEC-7); rC0/retired-icount audit |
| 3 | Given *realized* durations, the overlap matrix is exactly computable | **Theorem** (T1, descriptive) | piecewise-rational segment algebra |
| 3′ | *Predicting* durations is a coupled fixed point with a steady state | **Theorem with scoped conditions** (T2) | topical maps / nonlinear Perron–Frobenius |
| 4 | Distinct normalized runtime vectors generically induce distinct overlap weights | **Generic theorem** (T3) | semialgebraic measure-zero stack |
| 5 | Time-based aggregates hide vendor-specific weights | **Theorem, once overlap differs** (corollary of T3) | direct computation |
| 6 | Rankings can invert under different weights | **Possibility theorem** (constructive example) | explicit witness mix |
| 7 | Actual Intel/AMD CPU2026 rankings invert | **Empirical (existence; n = 1 suffices)** | the two desktops |
| 8 | Equal-reference-work + ANTT restores ranking stability | **Theorem (T5) + empirical instantiation** | axiomatics + the desktops |
| 9 | A universal machine-invariant metric exists | ~~"not provable; likely impossible"~~ → **provably impossible for time-only aggregates under axioms (T4); provably possible and unique once reference work is admitted (T5)** | the information-regime scoping below |

Row 9 is the paper's spine. The impossibility must be scoped to the **information regime**,
not asserted absolutely:

```
   INFORMATION REGIME             ACHIEVABLE?                        RESULT
   ──────────────────────────────────────────────────────────────────────────
   wall-clock segment times       ✗  IMPOSSIBLE — the axiom set       T4
   {t_ij} only                       {monotonicity, machine-
                                     invariance, overlap-
                                     independence} is unsatisfiable
          │
          ▼  admit ONE extra datum per benchmark: reference work {w_j}
   ──────────────────────────────────────────────────────────────────────────
   {t_ij} ∪ {w_j}                 ✓  POSSIBLE — and the icount-        T5
   (icount-anchored regime)          anchored ANTT-style aggregate
                                     is UNIQUE up to monotone
                                     transform
   ──────────────────────────────────────────────────────────────────────────
   arc:  impossibility  →  minimal information repair  →  uniqueness
```

---

## 3. The theory program (T1–T5)

### T1 — Rotation calculus (descriptive theory)

**Statement sketch.** (a) Under full rotation, per-benchmark incidence is equal across
copies. (b) Given realized segment durations d = (d_ij), the co-run overlap matrix
Φ(d) — for each ordered pair (segment, co-running benchmark), the overlap duration — is an
exactly computable, piecewise-rational function of d. (c) The runtime-vector space
partitions into finitely many *overlap-pattern cells*; Φ is rational on each cell.

**Machinery.** Timed-event-graph / max-plus form (Baccelli–Cohen–Olsder–Quadrat 1992) for
constant durations; the cell decomposition is the load-bearing artifact reused by T2 and T3.
**Risk: low.** This is careful bookkeeping, not deep mathematics.

### T2 — Steady-state existence (predictive theory)

The coupled system:

```
              ┌──────────────────────────────────┐
              │  alignment / overlap pattern  Φ  │
              │  (who co-runs with whom,         │
              │   and for how long)              │
              └─────────┬───────────▲────────────┘
        f: contention   │           │   g: durations
        determines      │           │   determine
        durations       ▼           │   overlap windows
              ┌──────────────────────────────────┐
              │  per-segment durations  d = (d_ij)│
              └──────────────────────────────────┘

        steady state  =  fixed point   d* = f(Φ(d*))
```

**Statement sketch.** If the per-lap update map is monotone and additively homogeneous
(delaying every copy by h delays everything by h), it is a *topical function* — sup-norm
nonexpansive — and a periodic steady state (nonlinear eigenvector / cycle-time vector)
exists under a connectivity condition (Gaubert–Gunawardena, Trans. AMS 2004, nonlinear
Perron–Frobenius). Uniqueness is **not** free for topical maps and must be argued from
RRR-specific structure, cell by cell; where it fails we publish the counterexample.

**Known hard part (scope early).** Monotonicity of the lap map is plausible for contention
(more co-run pressure ⇒ longer segments) but shifting one segment's duration moves overlap
*windows* non-monotonically. Mitigation: prove monotonicity **within** each overlap-pattern
cell of T1's decomposition (the same cells T3 needs anyway); treat cell-boundary crossings
as the explicit non-monotone catalog. Fallback posture: existence-with-conditions plus an
honest counterexample section — still a publishable theorem (and the *first* of its kind:
see §6 gap analysis).

**Machinery.** Gaubert–Gunawardena 2004; Fricker–Jaïbi (Queueing Systems 1994) monotone
embedded-map technique; Hanen–Munier cyclic-scheduling cycle-time as the contention-free
null model.

### T3 — Vendor genericity (the formal version of the old hero claim)

**Statement sketch.** Let v_I, v_A be two machines' solo-runtime vectors over the roster.
The set of (v_I, v_A) pairs for which the induced overlap-weight vectors coincide is
contained in a proper semialgebraic subset — hence Lebesgue-null, meager, and nowhere
dense simultaneously. In words: **overlap weights are machine-specific, except on a
measure-zero coincidence set.**

**Lemma stack** (all citable, nothing bespoke):
1. Finitely many overlap-pattern cells, Φ rational on each — T1(c)
   (cell decomposition: Bochnak–Coste–Roy, *Real Algebraic Geometry*, 1998).
2. Per-cell coincidence = zero set of a polynomial that is not identically zero —
   **the one model-specific obligation**: exhibit a single machine pair where the
   polynomial is nonzero. *This is what the two desktops are for.*
3. Nonzero polynomial ⇒ Lebesgue-null zero set (Mityagin, Math. Notes 107(3), 2020).
4. For semialgebraic sets, null / meager / nowhere-dense genericity coincide
   (Bolte–Daniilidis–Lewis, Math. of OR 36(1), 2011) — one citation upgrades the claim
   to all three senses at once.

**Risk: low**, given T1. No benchmarking paper has ever made a measure-zero-coincidence
claim; the machinery is standard elsewhere.

### T4 — Impossibility (axiomatic core)

**Statement sketch.** No score S({t_ij}) computed from wall-clock segment times alone
satisfies, simultaneously and in the proxy regime: anonymity (A1), progress-monotonicity
(A2), time-unit scale invariance (A3), machine-invariance of implied constituent weights
(A4), and overlap-independence (A5). Proof shape: T3 supplies two machines whose realized
overlaps differ on the same schedule; A4+A5 then force S to equalize weight vectors that
A2+A3 force apart — a finite, checkable contradiction (SMT-verifiable on small instances).

**Axiom design discipline (anti-rigging rule).** Every axiom must be satisfied by at least
one *existing* metric, so the impossibility reads "no metric does all the things current
metrics each individually promise," not "no metric satisfies our invented wishlist":

| Axiom (draft) | Informal content | Satisfied by (examples) |
|---|---|---|
| A1 anonymity | copies/benchmarks treated symmetrically | all candidates |
| A2 progress-monotonicity | speeding up one constituent never lowers the score | STP, cumulative IPC |
| A3 scale invariance | invariant to time units | all candidates |
| A4 machine-invariant weighting | implied constituent weights identical across machines running the same schedule | SPECrate-style equal-weight ideal; full-rotation aggregates |
| A5 overlap-independence | score depends on progress, not on realized alignment | ANTT (per-program normalization) |
| A6 full-rotation consistency | on the full rotation, reduces to a symmetric per-benchmark mean | harmonic-mean candidates |

(The set is a draft; finalization is workstream W2 in §7. The committee's own candidate
space — cumulative IPC, average throughput, harmonic mean, fairness indices — must each
appear in the satisfaction table.)

**Corollary: axiomatizing the 12-year dispute.** Michaud's "consistency" property
(CAL 2013) and Eyerman–Eeckhout's "system-level meaning" (CAL 2013 rebuttal) enter as
formal axioms. The paper does **not** pick a winner (the old framing rule survives); it
characterizes which axiom subsets are co-satisfiable — exactly the move of "Axiomatizing
Congestion Control" (Zarchy–Mittal–Schapira–Shenker, SIGMETRICS/POMACS 2019). This is the
strongest possible treatment of the dispute without taking sides.

### T5 — Characterization / uniqueness (the constructive payoff)

**Statement sketch.** In the icount-anchored regime ({t_ij} ∪ {w_j}), the
equal-reference-work aggregate — per-benchmark normalized progress against reference work
w_j, ANTT-style harmonic composition, with the closed-form staggered-tail-bias correction
(absorbed H3: fast copies retire early; slow copies finish under declining contention) —
satisfies {A1..A6 minus the impossible conjunction} and is the **unique** such score up to
monotone transform.

**Machinery.** Functional-equation uniqueness in the Aczél–Saaty 1983 style (the rigorous
counterpart the Fleming–Wallace 1986 geomean argument never had), structured like
Lan–Kao–Chiang–Sabharwal's axiomatic fairness theory (INFOCOM 2010). The same-ISA pin
(DEC-7) is what makes w_j a legitimate machine-neutral reference-work unit — the cross-ISA
confound was *removed* by the 2026-06-10 descope, not hidden.

**Framing-rule amendment (deliberate, recorded).** The old rule "never claim a
uniqueness theorem" was an anti-absolutism guard for the empirical hero. Under this pivot,
uniqueness **relative to an explicit axiom set** (a conditional theorem) is the
contribution and is defensible in the performance-evaluation tradition (Aczél–Saaty;
Lan et al.; Zarchy et al.). Absolute claims ("the one correct metric") remain forbidden.

---

## 4. Mechanization (the "modern frameworks" component)

| Target | Tool | Feasibility (verified against mathlib4, 2026-06) |
|---|---|---|
| T1(a) equal incidence; axiom lattice of T4/T5 (finite structures) | **Lean 4** | straightforward; finite combinatorics |
| T3 linear case (coincidence loci as rational hyperplanes) | **Lean 4** | essentially off-the-shelf: `MeasureTheory.Measure.addHaar_affineSubspace` (proper affine subspaces are null) |
| T3 full piecewise-rational case | Lean 4 (stretch) | plausible self-contained Fubini induction; do NOT promise — mathlib has no semialgebraic geometry or Sard |
| T4 small-instance unsatisfiability; counterexample search over axiom subsets | **SMT (Z3)** | standard |
| Overlap simulator (T1) | exact rational arithmetic (Python `fractions`) + symbolic tie-breaking (Simulation-of-Simplicity style) | avoids floating-point cell-boundary artifacts |

**Why bother.** Verified rarity (2026-06-12 research): no theorem-prover artifact has ever
appeared at IISWC/ISPASS; no Lean artifact at any architecture venue; the nearest precedent
line (Prosa, ECRTS 2016; Bozhko–Brandenburg's mechanized abstract RTA, ECRTS 2020) proves
empirical-venue reviewers accept mechanization when framed as *readable verification of the
definitions*, not as formal-methods showmanship. Artifact bar: `lake build`, zero `sorry`.
Position the Lean artifact as supplementary rigor; never as a headline contribution at
TACO/ICPE/ISPASS (only PL venues badge proofs per se).

---

## 5. Minimal empirical plan (two consumer desktops, weeks not months)

Hardware (unchanged from DEC-2/DEC-7): AMD Ryzen 9 9955HX (Zen 5, 16C, 30 GiB usable) +
Intel i9-12900 (Alder Lake, 8 P-cores used, E-cores idle), identical x86-64-v3 pinned
binaries, SMT siblings idle, equal copies = 8.

| Stage | What | Size | Purpose |
|---|---|---|---|
| E1 | Solo runtime vectors: rate-class roster (14 INT + 12 FP) × 2 machines, ≥5 reps, CV/bootstrap gating per statistics policy | ~260 runs | inputs to T2/T3; the T3 witness evaluation |
| E2 | Retired-icount audit (rC0 / retired-instr equivalence class) on the same runs | piggybacked | row 2 of the provability map; w_j measurement |
| E3 | Theory-*selected* RRR mixes: k = 2..4, copies = 8, chosen by the T1 simulator to maximize predicted overlap divergence between the two measured runtime vectors | 20–40 mixes × 2 machines × ≥3 reps | exhibit row 6/7 (inversion); validate Φ predicted vs realized; validate T2 steady state |
| E4 | Corrected-metric instantiation: compute the T5 aggregate on E3; show rank stability across vendors; validate the tail-bias correction term | analysis only | row 8 |

Run-validity gates (carried over): zero swap activity (`vmstat` si/so = 0 — the AMD box
has 30 GiB; 8 copies × 2.2 GB worst-case ≈ 17.6 GB fits; never run 16-copy worst-case
mixes), frequency/thermal discipline logged in the environment manifest, memory-feasibility
filter in the mix selector (`copies × max_RSS(subset) + OS ≤ usable RAM`; infeasible mixes
logged, not silently dropped — speed-class constituents are excluded by this filter
automatically).

What this plan **no longer contains**: server rentals (the PMU-qualification note's tier
system is moot for the hero — Tier B counting/sampling on the local boxes is ample),
IBS/PEBS mechanism campaigns (PMU work shrinks to the icount equivalence-class audit),
the cluster-stratified C(52,k) sweep (the sampler survives only as E3's mix picker), and
**DCPerf-django** (dropped by default — the proxy-fidelity story belonged to the
workload-synthesis framing; revival condition: a venue/reviewer demands an application
anchor, in which case the Li et al. reproduction is the cheap fallback).

---

## 6. Novelty: the verified three-way gap

Exhaustive literature research (7 agents, ~280 searches, 2026-06-12) verified:

1. **Metric axiomatics.** No axiomatic or impossibility treatment of multiprogram
   throughput metrics exists. Michaud (CAL 2013) proves one property violation
   (proto-axiomatic); TPEX (Eyerman–Michaud–Rogiest, TACO 2014) is operational
   ("a metric is defined by its experiment's assumptions"), not axiomatic. The genuine
   templates — Aczél–Saaty 1983, Lan et al. 2010, Zarchy et al. 2019, the Arrow-for-ML-
   benchmarks line (Zhang–Hardt ICML 2024; Gordienko et al. 2026) — have **never** been
   imported into architecture. The architecture-side "war of the means"
   (Fleming–Wallace 1986 → Smith 1988 → Mashey 2004 → John 2004 → Eeckhout CAL 2024) is
   entirely informal.
2. **Cyclic-schedule theory.** All of it — polling models (Takagi; Boxma), pinwheel
   (incl. Kawamura's STOC 2024 resolution), cyclic executives, PESP, max-plus — assumes
   **exogenous** durations. Exactly one prior model ever closed the mutual-contention loop
   as a simultaneous system (StatCC, PACT 2010) and it ships **zero**
   existence/uniqueness/convergence theory. The structural twin in architecture
   (co-phase matrix, Van Biesbrouck et al., ISPASS 2004/2006) was a simulation
   accelerator, never an analytical theory.
3. **SPEC CPU2026 itself.** Two papers total (the committee's open call + Li et al.);
   zero citations each; zero scoring proposals anywhere, academic or otherwise
   (deepest non-academic treatment, Igor's Lab 2026-05, explicitly lists the candidate
   metrics and stops).

```
                              formal proofs
                                   ▲
        polling / max-plus /       │      ★ THIS PROPOSAL
        pinwheel theory            │        axiomatic + fixed-point
        (exogenous durations,      │        theory OF RRR scoring,
        no contention coupling)    │        mechanized, witness-validated
                                   │
   ────────────────────────────────┼────────────────────────────────▶
                                   │          SPEC / multiprogram
        Aczél–Saaty 1983;          │          domain specificity
        Lan et al. 2010;           │      TPEX 2014; Michaud CAL'13;
        Zarchy et al. 2019;        │      StatCC 2010; co-phase ISPASS'04;
        Arrow-for-ML (2024–26)     │      Li et al. 2026; SPEC open call
        (right rigor, wrong domain)│      (right domain, no axioms/proofs)
```

The proposal occupies the empty upper-right quadrant on every axis simultaneously.

Scoop horizon: **IISWC 2026 notifications, 2026-07-27** — the only place a rushed
CPU2026/RRR submission could be hiding. Re-run the scoop check that week.

---

## 7. Workstreams and sequencing

(W-numbering is local to this note.)

| W | Content | Output | Window (2026) |
|---|---|---|---|
| W1 | T1 rotation calculus + exact-rational overlap simulator + cell decomposition | proofs + simulator | Jun–Jul |
| W2 | Axiom finalization (satisfaction table over the committee's candidate metrics) + T4 proof + Z3 instance checks | proofs + SMT artifact | Jul–Aug |
| W3 | E1/E2 solo + icount campaign on both boxes | runtime/icount vectors | Jul–Aug (parallel) |
| W4 | T3 genericity proof + witness evaluation on E1 data | proof + witness | Aug |
| W5 | T2 fixed-point theory (cell-wise monotonicity; counterexample catalog) | proofs, scoped | Aug–Sep |
| W6 | T5 characterization + tail-bias correction well-posedness | proof | Sep |
| W7 | E3/E4 mix campaign + corrected-metric instantiation | inversion witness + stability demo | Sep |
| W8 | Lean 4 artifact (T1(a), T3 linear, axiom lattice) | `lake build`, zero `sorry` | Sep–Oct |
| W9 | Paper writing + submission | manuscript | Oct → venue ladder |

Dependency spine: W1 → {W2, W4, W5}; W3 → {W4, W7}; {W2, W5, W6} → W9.
W3 can start immediately (hardware is ready; gcc.cfg/aocc.cfg must be re-pinned to
x86-64-v3 first — still the standing pre-condition from the bring-up memory).

---

## 8. Venue strategy (deadlines verified 2026-06-12)

Honest verdicts from the venue research: **ASPLOS, CGO, PLDI are out** (ASPLOS codifies
SIGPLAN's Empirical Evaluation Guidelines in its CFP and has zero theory-first precedent
2023–2026; CGO/PLDI are desk-mismatches). MICRO/HPCA main tracks set an empirical bar
(Mess, MICRO 2024: hundreds of measurements, six vendors) this paper deliberately does not
chase; their industry tracks are ineligible (industry first-author required).

| Venue | Fit | Key facts | Deadline |
|---|---|---|---|
| **ACM TACO** (primary) | 3.5/5 | TPEX (TACO 2014) is the exact in-venue ancestor; architecture audience; 20 pp (+refs), 25 pp cap; ~47 d first response; ~30% accept; CORE B; HiPEAC journal-first podium (June-1 pattern → HiPEAC 2028) | rolling |
| **SIGMETRICS 2027** (stretch) | 3.5/5 | CORE A*; axiomatic genre native ("Axiomatizing Congestion Control", POMACS 2019); theory ≈ 43% of program; 2027 @ FCRC Atlanta, co-located **with ISCA**; risk: zero SPEC papers in POMACS 2020–26 — sell the general aggregation problem, SPEC as instance; 13–20%/round; 12-month resubmission ban on plain reject | Fall: abs **Oct 2**, paper **Oct 9, 2026**; Winter: Jan 4/11, 2027 |
| ICPE 2027 (fallback 1) | 4/5 | the ACM/**SPEC** conference; answering SPEC's open call lands with its own sponsor; Emerging-Research track as low-risk entry; CORE B, ~33% | est. late Oct/early Nov 2026 (CFP unposted) |
| ISPASS 2027 (fallback 2) | 4/5 | CFP literally lists "Foundations of performance and efficiency analysis: **Metrics**"; Top-Down (Yasin 2014) is an ISPASS paper; 2 desktops normal | est. early Dec 2026 (2026 was Dec 8/15, 2025) |
| IEEE CAL (optional pre-stake) | 3/5 | 4 pp incl. refs; ~30 d decision; **no concurrent submission** (publish-first-then-extend only) | rolling |
| Perf. Evaluation / ToMPECS | 4/5 fit, low payoff | axiomatic form factor native; Q3 prestige; wrong audience | rolling |

```
   2026 ─────────────────────────────────────────────────────────▶ 2027
   Jun    Jul         Aug    Sep    Oct          Nov     Dec      Jan        ...   Jun
    │      │                         │            │       │        │                │
    │   IISWC'26                SIGMETRICS      ICPE    ISPASS   SIGMETRICS    SIGMETRICS'27
    │   notifications           Fall round      2027    2027     Winter        @ FCRC w/ ISCA
    │   Jul 27                  abs Oct 2       (est.)  (est.)   Jan 4 / 11    Atlanta
    │   (scoop horizon)         paper Oct 9
    │
    └── TACO: rolling — submit when T1–T5 are written (~47-day first response) ────▶
```

**Decision rule.** If W1–W6 are drafted by late September: take the SIGMETRICS Fall swing
(Oct 2/9); a plain reject still leaves TACO open immediately (no concurrency conflict
after notification, Dec 9). Otherwise: TACO directly. ICPE/ISPASS 2027 remain as
conference fallbacks if the architecture community's podium matters more than journal
archival. Skip the CAL pre-stake unless the scoop check on Jul 27 turns up a competitor —
it delays the full paper for a 4-page claim.

---

## 9. Risks and mitigations

| # | Risk | Mitigation |
|---|---|---|
| R1 | Axiom-rigging objection ("you chose axioms to force the result") | anti-rigging rule (§3, T4): every axiom satisfied by an existing metric; committee's own candidate space in the satisfaction table |
| R2 | Lap-map monotonicity fails globally | cell-wise treatment; counterexample catalog; fallback = existence-with-conditions (still a first) |
| R3 | SIGMETRICS out-of-community ("what is RRR? who cares?") | lead with the general problem — aggregating deterministic co-schedule performance across machines — with SPEC's open call as the standing official demand; quote Madhav et al. verbatim |
| R4 | TACO reviewer pool is architects, not theorists | lead with the corrected metric + the SPEC open call; demote Lean to artifact; cite TPEX as in-venue lineage in the first paragraph |
| R5 | Uniqueness (T5) harder than sketched | degrade to characterization-within-a-family (Aczél-style); the impossibility (T4) + construction still stand alone |
| R6 | Scooped at IISWC 2026 | re-run scoop check at notifications (Jul 27); differentiation: nobody else has the theory layer; an empirical RRR paper would *cite-fodder* this one, not kill it |
| R7 | Mechanization scope creep | hard scope: T1(a) + T3-linear + axiom lattice only; everything else pen-and-paper |
| R8 | SPEC license compliance | unchanged and non-negotiable: research-mode framing (`--noreportable`, disclosure), no SPEC assets in any artifact, `redistribution_audit.py` as publish gate, no benchmark names in flags, no FDO in base |

---

## 10. What survives / what dies (delta vs. descope_2026-06-10)

| Item | Status under this pivot |
|---|---|
| 2-box matrix (1 Intel + 1 AMD, x86-64-v3 pin, equal copies, P-core binding) | **survives** — now *sufficient*, not minimal |
| icount-as-reference-work anchor; ANTT lineage; STP/ANTT + TPEX as governing lineage | **survives** — now formalized as T5's regime |
| staggered-tail-bias correction (ex-H3) | **survives** — part of T5's well-posedness |
| PMU equivalence classes (ex-H5) | **shrinks** — icount audit only (E2); IBS/PEBS mechanism campaign dead |
| C(52,k) sampler | **shrinks again** — E3's mix picker only |
| DCPerf-django anchor | **dropped by default** (revival condition in §5) |
| MICRO 2027 / HPCA targeting (DEC-VENUE) | **superseded** — TACO primary / SIGMETRICS stretch / ICPE + ISPASS fallback |
| "never claim a uniqueness theorem" framing rule | **amended** — conditional (axiom-relative) uniqueness is the contribution; absolute uniqueness still forbidden |
| Server/cloud rentals; node-qualification tiers for the hero | **moot** — local boxes suffice (see `rented_node_pmu_qualification.md`, standing conclusion confirmed) |
| Energy/carbon, cross-ISA/ARM, agentic-AI, H4 table, H2 CV model | **stay terminated/parked** (unchanged from 2026-06-10) |

---

## 11. Working title and contribution list (for the eventual abstract)

**Working title.** *From Exhibition to Score: An Axiomatic and Algorithmic Theory of
Rolling Round-Robin Benchmark Scoring.*

1. The first formal theory of deterministic cyclic co-scheduling with
   contention-endogenous durations: exact overlap calculus (T1), steady-state
   existence via nonlinear Perron–Frobenius (T2), and machine-genericity of overlap
   weights (T3).
2. The first axiomatic treatment of multiprogram throughput metrics: an impossibility
   theorem for time-only aggregates (T4) and a uniqueness characterization of the
   icount-anchored corrected aggregate (T5) — resolving the information-theoretic shape
   of SPEC's open scoring call.
3. A mechanized core (Lean 4 + SMT) and an exact-rational overlap simulator.
4. Witness validation on a two-vendor consumer matrix: predicted overlap divergence,
   ranking inversion under time-only aggregates, and rank stability under the corrected
   metric.

---

## 12. References (anchors; full list in `references/papers/sources/`)

- Madhav et al., "SPEC CPU: The Next Generation," ISCA 2026, arXiv:2605.01575 (the open call).
- Li et al., "SPEC CPU2026: Characterization...," arXiv:2605.03713 (the baseline characterization).
- Eyerman & Eeckhout, IEEE Micro 28(3), 2008 (STP/ANTT). Michaud, IEEE CAL 12(2), 2013. Eyerman–Michaud–Rogiest, ACM TACO 11(3), 2014 (TPEX), DOI 10.1145/2663346.
- Fleming & Wallace, CACM 29(3), 1986; Smith, CACM 31(10), 1988; Mashey, SIGARCH CAN 32(4), 2004 (the war of the means).
- Aczél & Saaty, J. Math. Psychology 27(1), 1983 (functional-equation uniqueness).
- Lan, Kao, Chiang, Sabharwal, INFOCOM 2010 (axiomatic fairness).
- Zarchy, Mittal, Schapira, Shenker, POMACS 3(2) / SIGMETRICS 2019 (axiomatizing congestion control — the methodological template).
- Zhang & Hardt, ICML 2024; Gordienko et al., arXiv:2602.07593, 2026 (Arrow for ML benchmarks — adjacent, never imported to architecture).
- Gaubert & Gunawardena, Trans. AMS 356(12), 2004 (topical maps / nonlinear Perron–Frobenius).
- Baccelli, Cohen, Olsder, Quadrat, *Synchronization and Linearity*, 1992 (max-plus).
- Fricker & Jaïbi, Queueing Systems 15, 1994 (monotone embedded-map stability technique).
- Eklov, Black-Schaffer, Hagersten, PACT 2010 (StatCC — the lone fixed-point precedent, theory-free).
- Van Biesbrouck, Sherwood, Calder, ISPASS 2004/2006 (co-phase matrix — structural twin, simulation-only).
- Kawamura, STOC 2024 (pinwheel density threshold — finite case-analysis template).
- Bochnak–Coste–Roy 1998; Mityagin, Math. Notes 107(3), 2020; Bolte–Daniilidis–Lewis, Math. of OR 36(1), 2011 (genericity stack).
- Cerqueira–Stutz–Brandenburg, ECRTS 2016 (Prosa); Bozhko & Brandenburg, ECRTS 2020 (mechanized RTA — the mechanization-acceptance precedent).
- Eeckhout, IEEE CAL 23(1), 2024 (geomean critique — **motivation only**; single-system speedup is the wrong lineage for multiprogram throughput).
