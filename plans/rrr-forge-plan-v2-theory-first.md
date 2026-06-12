# RRR-Forge v2: An Axiomatic and Algorithmic Theory of Rolling Round-Robin Scoring — Theorem-First Plan

Plan version: v2 (2026-06-12). Supersedes `rrr-forge-plan-v1.md` (IISWC empirical-first; deleted in the re-scoping refactor, recoverable from git history at commit `1781a39`). Authoritative scope records: `.claude/memory/theory_first_pivot_2026-06-12.md`; full research proposal: `spec2026/notes/theory_first_rrr_proposal_2026-06-12.md`.

## Goal Description

Deliver a theorem-first paper and a machine-checked artifact answering SPEC CPU2026's open RRR-scoring call (Madhav et al., ISCA 2026, arXiv 2605.01575), targeting **ACM TACO (primary, rolling)** or **SIGMETRICS 2027 Fall round (stretch; abstract 2026-10-02, paper 2026-10-09)** per the DEC-1 decision rule, with **ICPE 2027 / ISPASS 2027** as conference fallbacks.

The paper proves five results (full statements and machinery in the proposal note):

- **T1 — Rotation calculus.** RRR formalized as a deterministic cyclic co-schedule; full-rotation equal incidence; exact piecewise-rational overlap matrix from realized durations; finite overlap-pattern cell decomposition.
- **T2 — Fixed-point steady state.** Predictive durations↔overlap coupling; existence via topical maps / nonlinear Perron–Frobenius (Gaubert–Gunawardena 2004), proven cell-wise; uniqueness where structure permits; honest counterexample catalog.
- **T3 — Vendor genericity.** Distinct solo-runtime vectors generically induce distinct overlap weights (semialgebraic stack: Bochnak–Coste–Roy + Mityagin 2020 + Bolte–Daniilidis–Lewis 2011); one measured machine-pair witness discharges the model-specific nonvanishing obligation.
- **T4 — Impossibility.** No score computed from wall-clock segment times alone satisfies the axiom set {anonymity, progress-monotonicity, scale invariance, machine-invariant weighting, overlap-independence}; every axiom is individually satisfied by an existing metric (anti-rigging discipline). Mechanically: Z3 QF_LRA grounding + MARCO minimal-unsat-core enumeration outside, Lean 4 finite case analysis verifying the minimal core inside (the Brandl–Brandt–Eberl–Geist JACM 2018 / Holliday et al. 2023 trust architecture).
- **T5 — Characterization.** In the icount-anchored regime, the equal-reference-work + ANTT-style aggregate with the closed-form staggered-tail-bias correction is the unique satisfying score up to monotone transform (Aczél–Saaty / Lan-style functional-equation uniqueness).

The empirical component is witness-grade by design: solo runtime + retired-icount vectors on the 2-vendor consumer matrix (AMD 9955HX + Intel i9-12900, identical x86-64-v3 pinned binaries, 8 copies on 8 P-cores), then 20–40 theory-selected RRR mixes exhibiting (a) the T3 witness, (b) CI-gated ranking inversions under the committee's candidate aggregates, and (c) rank stability under the T5 corrected aggregate. Per-segment timing comes natively from RRR (runcpu log start lines at 1 s + per-segment run-directory `speccmds.out` at ns precision + `.rsf` per-record durations); per-segment counters attach via `monitor_pre_bench`/`monitor_post_bench` with `$SPECCOPYNUM` (officially supported in rrr-rate mode).

The plan distinguishes throughout: **user-only items** (config re-pin ratification, Intel-node SPEC install, venue go/no-go), **Claude-doable items** (all proofs, simulator, parsers, Lean/Z3 artifact, campaign automation, manuscript), and **risk-tracked items** (T2 monotonicity scope, Lean Tier-2 time-box, SIGMETRICS timing).

## Acceptance Criteria

Following TDD philosophy, each criterion includes positive and negative tests for deterministic verification.
The `AC-*` items are current RLCR completion gates for this implementation loop.

- AC-1: T1 rotation calculus is written up and implemented as an exact-rational RRR overlap simulator whose descriptive computation is provably faithful to the calculus.
  - Positive Tests (expected to PASS):
    - Property suite: for every (k, copies, inc) in the bounded grid {k = 2..6} × {copies = 1..16} × {inc = 0..k}, the simulator's queue construction matches SPEC's documented rule (initial benchmark = copy index mod k; wrap-around for copies > k; inc-stepping), and for the full-rotation configuration each benchmark's incidence count is equal across copies.
    - Overlap reconstruction on synthetic duration fixtures is exact (rational arithmetic, zero error): the per-pair overlap durations sum to each segment's duration partitioned over co-runners, and permuting copy labels permutes the matrix accordingly (anonymity sanity).
    - Cell decomposition: for fixture instances (k ≤ 3, copies ≤ 4) the simulator enumerates the finitely many overlap-pattern cells and certifies the overlap map is rational on each (symbolic boundary handling, Simulation-of-Simplicity-style tie-breaking).
  - Negative Tests (expected to FAIL):
    - Feeding float durations into the exact path raises an explicit type error (no silent float contamination).
    - An `inc` value not coprime to k triggers a queue-coverage warning (some benchmarks never run on some copies, per SPEC's wrap rule); asserting full coverage on such a config fails.
- AC-2: A per-segment timeline parser reconstructs realized RRR schedules from native SPEC outputs on real runs from both vendor nodes.
  - Positive Tests:
    - Parser ingests (layer 1) runcpu log `Running (#i) <bench> ... for copy N [timestamp]` lines, (layer 2) `.rsf` per-record durations keyed by `NNN = iteration × copies + copynum`, and (layer 3) per-segment run-directory `speccmds.out` epoch+ns start/finish records, and emits a per-(copy, benchmark, iteration) interval table; layer-3 intervals agree with layer-2 durations within 1%, and the overlap matrix computed from real intervals equals the simulator's descriptive computation on those same intervals exactly.
    - First-install verification checklist passes and is filed as a note: CPU2026 `speccmds.out` record format confirmed; `.rsf` confirmed durations-only; `runcpu -v 35` variable dump captured; `$SPECCOPYNUM` expansion inside `monitor_wrapper` under RRR tested and its result recorded.
  - Negative Tests:
    - A run directory tree produced with `--minimize_rundirs` (or with rundirs cleaned) causes the parser to refuse with an explicit missing-layer error rather than silently degrading to 1 s log precision; the 1 s fallback exists but only behind an explicit `--coarse` flag that watermarks the output.
    - Overlapping intervals on the same copy (impossible in a valid RRR schedule) are rejected as corrupt input.
- AC-3: The axiom set is finalized with an anti-rigging satisfaction table, and the T4 impossibility is machine-verified end to end.
  - Positive Tests:
    - `axioms.md` defines each axiom formally; the satisfaction table covers at minimum {cumulative IPC, average throughput, harmonic mean, a fairness index, STP, ANTT, SPECrate-style equal-weight} and every axiom is satisfied by ≥1 existing metric and violated by ≥1 (so no axiom is vacuous or universal).
    - Z3 (Python `z3-solver`, ground QF_LRA over finite instance spaces, rational constants only) proves UNSAT for the claimed-impossible axiom conjunction on the witness instance family; MARCO-style MUS enumeration emits all minimal unsatisfiable axiom subsets; the results are committed as machine-readable JSON.
    - Lean 4 re-proves the minimal core by finite case analysis using kernel-checked `decide`/`decide_cbv` only; `#print axioms` on the impossibility theorem reports exactly `propext, Classical.choice, Quot.sound`.
  - Negative Tests:
    - An axiom that no existing metric satisfies causes the rigging lint (table checker) to fail the build.
    - If Z3 returns SAT for the claimed-impossible set, AC-3 fails loudly (the model is printed as a counterexample); no silent axiom strengthening is permitted without a documented revision entry in `axioms.md`.
    - Any use of `native_decide` (axiom fingerprint `Lean.ofReduceBool`) anywhere in the Lean tree fails the artifact gate.
- AC-4: T3 genericity is proven and the measured machine-pair witness discharges the nonvanishing obligation.
  - Positive Tests:
    - The written proof composes the verified lemma stack (BCR cell decomposition; Mityagin null zero-sets; BDL genericity collapse) with T1's cells; the statement is "null AND meager AND nowhere dense" via the single BDL citation.
    - The coincidence polynomial for ≥1 pre-registered mix family, evaluated at the measured (v_Intel, v_AMD) solo-runtime vectors in exact rational arithmetic, is nonzero; the evaluation script and inputs are in the artifact.
    - The Lean linear-case lemma (coincidence loci as proper affine subspaces are Lebesgue-null, via `MeasureTheory.Measure.addHaar_affineSubspace`) builds with zero sorry.
  - Negative Tests:
    - Witness evaluation in floating point is rejected by the same exact-arithmetic guard as AC-1.
    - A fixture with v_Intel = v_AMD (identical vectors) is correctly detected as lying ON the coincidence set (sanity: the detector is not pathologically permissive).
- AC-5: T2 steady-state theory is established at honest scope and validated predictively against real mixes.
  - Positive Tests:
    - Written proof: within each overlap-pattern cell, the lap map is monotone + additively homogeneous for the declared contention-model class, hence topical; existence of the periodic steady state follows; uniqueness is proven exactly where the stated structural conditions hold.
    - The simulator's fixed-point iteration converges on measured solo vectors for all E3 mixes, and the predicted overlap shares match realized overlap shares within the DEC-2 ratified tolerance on ≥80% of mixes; misses are individually diagnosed (cell-boundary crossing, frequency drift, tail idle) in the run notes.
    - The counterexample catalog documents ≥1 explicit boundary-crossing instance where monotonicity fails, with the simulator trace.
  - Negative Tests:
    - A divergent or cycling fixed-point iteration is reported with status `nonconvergent` and excluded from prediction-accuracy claims — never averaged in.
    - Manuscript lint: the words "unique" / "uniqueness" applied to T2 outside the proven-conditions scope fail the over-claim check.
- AC-6: The solo + icount measurement campaign (E1/E2) completes on both nodes under the pinned, audited configuration.
  - Positive Tests:
    - Both `gcc.cfg`-built suites are rebuilt with `-march=x86-64-v3`; the config-diff lint asserts the Intel and AMD configs are identical except portability sections, and asserts the absence of `znver5`/`-march=native`/benchmark-name-derived flags.
    - All rate-class benchmarks (14 INT + 12 FP) × 2 machines complete ≥5 solo repetitions; per-benchmark runtime CV ≤ the `statistics_policy.md` threshold (escalation rule applied otherwise); retired-icount (rC0 / equivalent event) per benchmark agrees across vendors within the DEC-2 icount tolerance, certifying the equal-reference-work premise.
    - Every run carries a complete environment manifest (CPU model, kernel, governor, frequency residency, SMT state, swap counters, perf version, config hash); `vmstat` si/so = 0 for the measurement window.
  - Negative Tests:
    - A run with any missing manifest field is refused by ingestion.
    - A run with nonzero swap activity, or with the SMT-sibling-active topology, is marked invalid and excluded; asserting campaign completeness over a set containing an invalid run fails.
- AC-7: The inversion phenomenon and its T5 repair are exhibited on pre-registered mixes (E3/E4), and T5's uniqueness proof is complete.
  - Positive Tests:
    - The E3 mix list (20–40 mixes, k = 2..4, copies = 8, inc coprime to k unless deliberately testing wrap) is selected by predicted overlap divergence and hash-committed (pre-registered) before any E3 run executes.
    - ≥1 mix family exhibits a vendor ranking inversion under ≥2 committee candidate aggregates (cumulative IPC, mean per-copy time, harmonic mean), gated by non-overlapping 95% bootstrap CIs per `statistics_policy.md`.
    - The T5 corrected aggregate (icount-anchored equal-reference-work + ANTT composition + tail-bias correction, with the final-iteration idle-tail handling documented) is rank-stable across vendors on the same data; the tail-bias correction term is validated against the measured final-iteration idle windows.
    - The T5 written uniqueness proof (functional-equation argument over the post-T4 axiom subset) is complete and adversarially reviewed.
  - Negative Tests:
    - An inversion whose CIs overlap is reported as `indistinguishable`, never as a finding.
    - Any mix not in the pre-registered hash-committed list is excluded from headline claims; the pre-registration checker fails if headline tables reference unregistered mixes.
    - If no CI-gated inversion materializes across the full pre-registered set, AC-7 fails and triggers DEC-6 (negative-result reframing) — no silent threshold loosening.
- AC-8: The Lean artifact meets the zero-trust-gap engineering bar.
  - Positive Tests:
    - Pinned `lean-toolchain` + `lake-manifest.json`; `lake exe cache get` documented; `lake build --wfail` green; `#print axioms` on every exported theorem reports exactly the three standard axioms; `lake env leanchecker --fresh` passes on all modules; CI via `leanprover/lean-action` runs all gates on every push.
    - Tier-1 contents complete: rotation equal-incidence theorem, the axiom-lattice impossibility core, and the affine-subspace null lemma application.
  - Negative Tests:
    - A `sorry` (i.e. `sorryAx` in the axiom print), `native_decide`, or unpinned dependency fails the artifact gate.
    - Tier-2 (polynomial null zero-set, confirmed absent from mathlib) exceeding its DEC-3 time-box without completion is descoped to the pen-and-paper citation path; claiming it in the manuscript while absent from the Lean tree fails the traceability check.
- AC-9: The open artifact reproduces all results and passes SPEC-compliance gates.
  - Positive Tests:
    - From a clean checkout + a user-supplied SPEC CPU2026 install, `make -C artifact reproduce` regenerates every figure/table from raw interval/counter CSV/JSON; `scripts/publish_gate.py` (existing, 65/65 audit tests) reports zero redistribution violations.
    - The framing lint passes: RRR results labeled research-mode/"Estimated", subset/non-reportable disclosure present, no energy fields, no "SPEC ratio" language applied to RRR numbers.
  - Negative Tests:
    - A SPEC source/binary/input file anywhere in the artifact tree fails `redistribution_audit.py` before publish.
    - A manuscript table value not derivable from artifact data fails the number-traceability check.
- AC-10: A submission-ready manuscript exists and the venue decision rule has been executed.
  - Positive Tests:
    - Full draft in the chosen venue's format (TACO 20 pp or SIGMETRICS double-column), containing T1–T5 with proofs (appendix as venue permits), the witness measurements, the satisfaction table, the mechanization statement, and related work covering the four mandatory lineages (STP/ANTT + TPEX; war-of-the-means; axiomatic social choice incl. JACM 2018; cyclic-schedule/max-plus theory).
    - The DEC-1 decision rule was applied on its trigger date and the outcome logged.
  - Negative Tests:
    - The geomean-speedup line cited as governing lineage (rather than motivation-only) fails the lineage self-review checklist.
    - Submission without the scoop re-check note (IISWC 2026 notifications, 2026-07-27) in the related-work audit trail fails the runbook gate.

## Path Boundaries

Path boundaries define the acceptable range of implementation quality and choices.

### Upper Bound (Maximum Acceptable Scope)

All of T1–T5 with full proofs; Lean Tier-1 complete plus Tier-2 (polynomial null zero-set via Fubini induction) if it lands inside its time-box, with an upstream mathlib PR; T2 uniqueness proven on a characterized cell class; E3 at 40 mixes with per-segment `perf` counter attachment via `monitor_pre_bench`/`monitor_post_bench`; SIGMETRICS Fall submission with TACO as the post-notification fallback; artifact with full figure pipeline and one-command reproduction.

### Lower Bound (Minimum Acceptable Scope)

T1, T3, T4, T5 fully proven; T2 at existence-with-conditions plus counterexample catalog (no uniqueness claim); Lean Tier-1 only (equal incidence + axiom core + affine-null); Z3 impossibility verification on one witness instance family with MUS enumeration; E1/E2 complete on both nodes; E3 at 20 pre-registered mixes with ≥1 CI-gated inversion family and rank-stable corrected aggregate; TACO submission; artifact passing the publish gate without the full figure pipeline (tables regenerable, figures minimal).

### Allowed Choices

- Can use: Python 3 stdlib + `fractions` for the exact simulator (matching the repo's stdlib-only stats posture); `z3-solver` via pip; Lean 4 + mathlib pinned via lake; existing `scripts/rrr_forge/` modules (scorer, stats, budget, candidate_gen) extended rather than rewritten; existing policy notes (`statistics_policy.md`, `compute_budget.md`, `data_schema.md`) amended in place with a v2 changelog block; `monitor_pre_bench`/`monitor_post_bench` or `submit`-wrapped `perf` for per-segment counters (choose after the first-install checklist, AC-2).
- Cannot use: floating point anywhere in overlap/witness computation (exact rationals only); `native_decide` or unpinned Lean dependencies; quantified SMT encodings over infinite sorts (finite grounding only); `-march=znver5`/`-march=native` or any benchmark-name-derived compiler flag; SPEC-licensed files in the artifact tree; FDO in base; reportable-mode claims for RRR results; the geomean-speedup lineage as keystone; post-hoc mix selection (pre-registration is mandatory); server/cloud rentals (out of scope per the pivot); terminated directions (energy, cross-ISA/ARM, agentic-AI, DCPerf unless DEC-5 revives it).

> Note on deterministic designs: the trust architecture is fixed per the proposal — SMT searches outside, Lean verifies the minimal core inside, no Lean↔SMT runtime interop (lean-smt is cvc5-only and theory-limited; the JACM 2018 split is the ratified pattern). Upper and lower bounds converge on this point.

## Feasibility Hints and Suggestions

> Note: This section is for reference and understanding only. These are conceptual suggestions, not prescriptive requirements.

### Conceptual Approach

1. Build the simulator first (it is T1's executable semantics, T2's iteration engine, T3's witness evaluator, and E3's mix selector — one component, four consumers).
2. Derive everything timing-related from SPEC-native outputs: log start lines → coarse intervals; `.rsf` `cN_time`/per-record durations → validation; per-segment rundir `speccmds.out` → ns intervals. RRR forbids `--minimize_rundirs` (silently overridden), so rundirs are guaranteed present — but they multiply disk usage (one rundir per benchmark × copy × iteration); run `spec2026/scripts/clean_stale_spec.sh` between campaigns and budget disk in `compute_budget.md`.
3. Mix design respects the documented wrap rule: with copies=8 and k ∈ {2,4}, copies ≡ (mod k) have identical queues — that is the proxy regime under study, not a bug; with k=3, inc must avoid queue-skipping unless deliberately probed.
4. The final-iteration idle tail ("all cores idle until all processes finish") is measured directly from intervals and feeds the T5 tail-bias correction — treat it as signal.
5. Z3 axiom encoding: one Real per (instance, score) point, axioms expanded quantifier-free, `smt.core.minimize=true`, MARCO for the MUS lattice; rationals only.
6. Lean order of attack: axiom-lattice core (pure finite), then equal incidence (Fintype + decide), then the affine-null application; Tier-2 last, time-boxed.

### Relevant References

- `scripts/rrr_forge/` — scorer/stats/budget/candidate_gen reusable as-is; `runner.py` real backend is the E1/E3 stub to fill.
- `scripts/redistribution_audit.py`, `scripts/publish_gate.py` — working publish gates (AC-9).
- `references/notes/statistics_policy.md`, `compute_budget.md`, `data_schema.md`, `spec_compliance.md`, `runbook.md` — amend, don't recreate.
- `cpu2026/config/gcc.cfg` (+ `aocc.cfg` as sensitivity control only) — re-pin target; `cpu2026/Docs/` — installed-kit doc mirror for monitor/submit syntax.
- `spec2026/notes/theory_first_rrr_proposal_2026-06-12.md` — theorem statements, machinery, venue ladder.
- Verified instrumentation facts (2026-06-12 research): runcpu.html §1.8 (RRR flags, per-copy log lines, deferred verification, rundir-per-segment, "Estimated" labeling); monitors.html (`monitor_pre_bench`/`monitor_post_bench` + `$SPECCOPYNUM` in rrr-rate); config.html §IV.C (`submit = taskset -c $SPECCOPYNUM ${command}` unchanged; `$SPECCOPYNUM`/`$BIND` expanded by runcpu in RRR).
- Verified Lean facts: `MeasureTheory.Measure.addHaar_affineSubspace` / `addHaar_submodule` (exact signatures confirmed); Schwartz–Zippel in mathlib is the finite counting version only; `decide_cbv` since v4.29; `leanchecker` in-toolchain since v4.28; `leanprover/lean-action` v1.5.0.

## Dependencies and Sequence

### Milestones

1. **M1 — Theory core I + tooling bring-up**: T1 write-up + exact-rational simulator + cell decomposition; Lean project scaffold with CI gates; config-diff lint; timeline-parser spec against documented formats.
2. **M2 — Measurement bring-up (user-gated)**: x86-64-v3 re-pin + rebuild on AMD (DEC-4); Intel node SPEC install + perf-privilege checklist (DEC-4); first-install verification checklist (AC-2's four flagged unknowns); E1 solo + E2 icount campaigns; environment-manifest capture.
3. **M3 — Axiomatic core**: axiom finalization + satisfaction table + rigging lint; Z3 grounding + MUS enumeration; Lean axiom-lattice impossibility core (T4 done end to end).
4. **M4 — Genericity + fixed point**: T3 proof + measured witness (needs M2 vectors); T2 cell-wise existence proof + counterexample catalog; predictive validation harness.
5. **M5 — Mix campaign + corrected metric**: pre-registered E3 mix list (simulator-selected from M2 vectors); E3 runs on both nodes; inversion analysis + T5 corrected-aggregate instantiation + tail-bias validation; T5 uniqueness proof.
6. **M6 — Artifact + manuscript + submission**: Lean Tier-2 time-box; figure/table pipeline; publish + framing + traceability gates; manuscript; DEC-1 venue execution.

Dependency spine: M1 → {M3, M4-theory}; M2 → {M4-witness, M5}; {M3, M4} → M5-analysis; all → M6. M1 and M2's user-gated items can proceed in parallel; M3 is independent of measurement entirely (pure theory + finite computation) and is the schedule buffer.

## Task Breakdown

Each task must include exactly one routing tag:
- `coding`: implemented by Claude
- `analyze`: executed via Codex (`/humanize:ask-codex`)

Every `AC-*` must be covered by at least one task. Every task must target at least one `AC-*`. Do not target `FUT-*`, `DEC-*`, or `-` in the Target AC column.

| Task ID | Description | Target AC | Tag (`coding`/`analyze`) | Depends On |
|---------|-------------|-----------|----------------------------|------------|
| task1 | T1 written formalization: schedule definition matching runcpu §1.8 semantics (queue rule, wrap, inc-stepping, deferred verification, tail idle), equal-incidence theorem, descriptive overlap-matrix construction, cell decomposition | AC-1 | coding | - |
| task2 | Exact-rational overlap simulator (`fractions`-based) with property-test suite over the (k, copies, inc) grid, symbolic tie-breaking, float-contamination guards | AC-1 | coding | task1 |
| task3 | Adversarial review of T1 + simulator semantics against SPEC docs (queue rule edge cases: copies>k wrap, inc=0 quick-validation, non-coprime inc) | AC-1 | analyze | task2 |
| task4 | Timeline parser: 3-layer ingestion (log lines, .rsf records, speccmds.out), interval table emission, corruption/missing-layer refusal, `--coarse` watermark path | AC-2 | coding | task1 |
| task5 | First-install verification run + checklist note (speccmds.out format, .rsf timestamp absence, `runcpu -v 35` variable dump, `$SPECCOPYNUM`-in-monitor_wrapper test) on the AMD node | AC-2 | coding | task4 |
| task6 | Config re-pin support: config-diff lint (vendor-identity assertion, forbidden-flag scan incl. znver5/native/benchmark-name), rebuild runbook amendment | AC-6 | coding | - |
| task7 | Environment-manifest capture + run-validity gating (frequency residency, swap counters, SMT state, governor); ingestion refusal on missing fields | AC-6 | coding | task6 |
| task8 | E1 solo campaign automation on both nodes (26 rate benchmarks × ≥5 reps, CV escalation per policy) + E2 retired-icount audit; cross-vendor icount-equality report | AC-6 | coding | task5, task7 |
| task9 | Axiom formalization (`axioms.md`) + satisfaction table over {committee candidates, STP, ANTT, SPECrate-style} + rigging lint | AC-3 | coding | task1 |
| task10 | Adversarial axiom review: attack each axiom as rigged/vacuous/non-independent; verify the satisfaction table's claims metric by metric | AC-3 | analyze | task9 |
| task11 | Z3 harness: ground QF_LRA encoding, witness instance families, UNSAT verification, MARCO MUS enumeration, machine-readable results | AC-3 | coding | task9 |
| task12 | Lean project scaffold: pinned toolchain + mathlib, lake CI (`lean-action`), zero-sorry gate scripts (`--wfail`, `#print axioms`, `leanchecker`), native_decide ban lint | AC-8 | coding | - |
| task13 | Lean Tier-1a: axiom-lattice impossibility core (finite structures, `decide`/`decide_cbv`), re-proving the task11 minimal core | AC-3, AC-8 | coding | task11, task12 |
| task14 | Lean Tier-1b: rotation equal-incidence theorem + affine-subspace null application (`addHaar_affineSubspace`) | AC-4, AC-8 | coding | task12 |
| task15 | T3 written proof (BCR + Mityagin + BDL stack over T1 cells) + exact-rational witness evaluator + identical-vector sanity fixture | AC-4 | coding | task1, task2 |
| task16 | T3 witness evaluation on measured (v_Intel, v_AMD) vectors; pre-registered mix-family selection for the witness | AC-4 | coding | task8, task15 |
| task17 | T2 written proof: cell-wise monotonicity for the declared contention class, topical-map existence, scoped uniqueness, counterexample catalog | AC-5 | coding | task1, task15 |
| task18 | Adversarial review of T2's monotonicity argument and the uniqueness scope language | AC-5 | analyze | task17 |
| task19 | Fixed-point prediction harness: simulator iteration on measured vectors, predicted-vs-realized overlap comparison vs DEC-2 tolerance, nonconvergence reporting | AC-5 | coding | task2, task8, task17 |
| task20 | E3 campaign: pre-registration (hash-committed mix list), RRR runs on both nodes (k=2..4, copies=8, submit/taskset binding, monitor hooks per task5 outcome), interval + counter collection | AC-7 | coding | task8, task16, task19 |
| task21 | Inversion analysis: committee-candidate aggregates + bootstrap CI gating (reuse `rrr_forge.stats`); T5 corrected-aggregate computation incl. tail-bias term from measured idle tails; rank-stability report | AC-7 | coding | task20 |
| task22 | T5 written uniqueness proof (functional-equation argument over the post-T4 axiom subset) + tail-bias well-posedness | AC-7 | coding | task9, task17 |
| task23 | Adversarial review of T5 uniqueness (attack: alternative metrics satisfying the same subset; monotone-transform equivalence class edge cases) | AC-7 | analyze | task22 |
| task24 | Lean Tier-2 time-boxed attempt: polynomial null zero-set Fubini induction (descope to citation on DEC-3 expiry) | AC-8 | coding | task14 |
| task25 | Artifact assembly: figure/table pipeline from interval/counter data, `make reproduce`, publish gate + framing lint + number-traceability check wiring | AC-9 | coding | task21 |
| task26 | Manuscript: full draft (venue per DEC-1), four-lineage related work, mechanization statement, scoop re-check note (2026-07-27) | AC-10 | coding | task13, task16, task19, task21, task22, task25 |
| task27 | Adversarial full-paper review against the venue-fit recipe (axiom-rigging, over-claim lint, lineage keystone check, 2-box framing) | AC-10 | analyze | task26 |

## Future Work / Out of Scope

Future, deferred, post-work, successor-loop, and out-of-scope items belong here, not under `## Acceptance Criteria`.

- FUT-1: ITP/CPP-venue framework paper if the Lean development grows past Tier-2 (overlap calculus + genericity as a reusable library).
  - Source DEC: DEC-3
  - Current-loop handoff: AC-8
  - Promotion trigger: Tier-2 completes inside its time-box AND the library exceeds ~3 kLOC of reusable lemmas.
- FUT-2: Upstream mathlib PR for the polynomial null zero-set lemma.
  - Source DEC: DEC-3
  - Current-loop handoff: AC-8
  - Promotion trigger: task24 completes; PR effort is post-submission.
- FUT-3: Server-class validation (8–12 channel memory subsystems, bare-metal cloud) as a robustness appendix or follow-up.
  - Source DEC: DEC-1 (venue feedback)
  - Current-loop handoff: AC-7
  - Promotion trigger: reviewer demand, or a follow-up empirical paper after acceptance.
- FUT-4: DCPerf-django proxy-fidelity revival.
  - Source DEC: DEC-5
  - Current-loop handoff: AC-7
  - Promotion trigger: a venue/reviewer demands an application anchor.
- FUT-5: Cross-ISA/ARM extension of T3/T5 (cross-ISA icount confound re-enters; stays a future-work paragraph only).
  - Source DEC: DEC-5 (scope record: terminated 2026-06-10)
  - Current-loop handoff: AC-10
  - Promotion trigger: ARM hardware materializes AND a successor loop re-opens the axis.
- FUT-6: T2 uniqueness beyond the proven cell class; alignment-engineering (choosing inc/stagger to optimize a score) as a follow-up algorithmic paper.
  - Source DEC: DEC-2
  - Current-loop handoff: AC-5
  - Promotion trigger: counterexample catalog reveals exploitable structure.

## Claude-Codex Deliberation

### Agreements

- Not executed this round: the plan was generated single-agent per the user's explicit instruction not to invoke the gen-plan/gen-idea skills (token budget). The deliberation function is partially substituted by (a) the seven-agent verified research corpus of 2026-06-12 and the three-agent execution research in this loop, and (b) the `analyze`-tagged adversarial-review tasks (task3, task10, task18, task23, task27), which route the contested surfaces (simulator semantics, axiom rigging, T2 monotonicity, T5 uniqueness, full-paper claims) through Codex during execution rather than at plan time.

### Resolved Disagreements

- None recorded at plan time (no deliberation run). Disagreements arising in `analyze` tasks are to be logged in this section retroactively with resolution rationale.

### Convergence Status

- Final Status: `partially_converged` (single-agent plan; convergence deferred to in-loop adversarial tasks)

## Pending User Decisions

- DEC-1: Venue decision rule.
  - Claude Position: SIGMETRICS 2027 Fall (abstract 2026-10-02 / paper 2026-10-09) iff T1, T3, T4, T5 are drafted and E1–E3 data is in hand by 2026-09-20; otherwise TACO directly. A SIGMETRICS plain reject (notification 2026-12-09) falls back to TACO immediately.
  - Codex Position: not consulted (no deliberation this round).
  - Tradeoff Summary: SIGMETRICS = CORE A* + native axiomatic genre but out-of-community object and 13–20%/round; TACO = in-venue TPEX lineage + rolling deadline + ~30% but CORE B.
  - Decision Status: `PENDING`
- DEC-2: Numeric tolerances.
  - Claude Position: predicted-vs-realized overlap-share mean absolute error ≤ 10% per mix (AC-5 gate at ≥80% of mixes); cross-vendor retired-icount equality ≤ 0.5% per benchmark (same binaries); inversion gate = non-overlapping 95% bootstrap CIs; layer-3 vs layer-2 duration agreement ≤ 1%.
  - Codex Position: not consulted.
  - Tradeoff Summary: tighter tolerances strengthen claims but raise the risk of honest misses dominating; all four numbers are pre-registered constants once ratified.
  - Decision Status: `PENDING`
- DEC-3: Lean Tier-2 time-box.
  - Claude Position: 2 calendar weeks inside M6; on expiry, descope to the pen-and-paper Mityagin citation (the paper's claims do not depend on Tier-2).
  - Codex Position: not consulted.
  - Tradeoff Summary: Tier-2 is the only open-ended formalization item (lemma confirmed absent from mathlib); uncapped it threatens the venue window.
  - Decision Status: `PENDING`
- DEC-4: User-only operational gates for M2.
  - Claude Position: (a) approve the x86-64-v3 re-pin + full rebuild on the AMD node (run `clean_stale_spec.sh --apply` first; 72.1 GB reclaimable); (b) install the licensed kit on the Intel i9-12900 node and run the perf-privilege checklist there; (c) execute the first-install verification checklist items requiring a live `runcpu`.
  - Codex Position: not consulted.
  - Tradeoff Summary: M2 is the only externally gated milestone; M1/M3 proceed regardless, so delay here costs witness/measurement schedule only.
  - Decision Status: `PENDING`
- DEC-5: DCPerf-django stays dropped.
  - Claude Position: confirmed dropped (default from the 2026-06-12 pivot); revival only on FUT-4's trigger.
  - Codex Position: not consulted.
  - Tradeoff Summary: dropping saves a full target-suite install + campaign; the theory paper does not need an application anchor.
  - Decision Status: `PENDING`
- DEC-6: Negative-result protocol.
  - Claude Position: if AC-7's pre-registered set yields no CI-gated inversion, reframe the empirical section as "bounded divergence under the impossibility's premises" (T4 stands regardless — it is existence-independent); the paper survives with T1–T5 + witness + bounded-divergence measurements; do not loosen thresholds or extend the mix list post hoc.
  - Codex Position: not consulted.
  - Tradeoff Summary: pre-registration discipline vs. the temptation to chase the phenomenon; the theorem-first structure is exactly what makes the negative outcome publishable.
  - Decision Status: `PENDING`

## Implementation Notes

### Code Style Requirements

- Implementation code and comments must NOT contain plan-specific terminology such as "AC-", "Milestone", "Step", "Phase", or similar workflow markers
- These terms are for plan documentation only, not for the resulting codebase
- Use descriptive, domain-appropriate naming in code instead (e.g., `OverlapMatrix`, `RotationSchedule`, `SegmentInterval`, `CoincidenceWitness`, `AxiomSatisfactionTable`, `LapMap`, `TailIdleCorrection`, `EnvironmentManifest`)
- Existing guards to preserve: exact-arithmetic enforcement mirrors the `ScorerNaiveCentroidError` pattern already in `scripts/rrr_forge/score.py`; tests use domain language (`test_overlap_matrix_partitions_segment_durations`, `test_rotation_full_coverage_requires_coprime_increment`, `test_impossibility_core_axiom_print_is_standard_three`)
- SPEC compliance is non-negotiable throughout: research-mode framing, no SPEC assets in the artifact, `redistribution_audit.py` as the publish gate
