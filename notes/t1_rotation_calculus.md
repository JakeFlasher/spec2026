# T1 — The Rotation Calculus of SPEC CPU2026 Rolling Round-Robin Mode

Status: working formalization, 2026-06-12. This is the written half of the T1 theory
deliverable; the executable half is the exact-rational simulator in
`scripts/rrr_forge/{rotation,overlap,cells}.py`. Companion documents:
`theory_first_rrr_proposal_2026-06-12.md` (§3 theorem program) and
`.humanize/plans/rrr-forge-plan-v2-theory-first.md` (acceptance gates).

Everything below is stated over exact rationals. No real-number analysis is needed for
T1; the piecewise-linear structure is combinatorial. Floating point is forbidden in any
computation that instantiates these definitions (enforced in code by
`ExactArithmeticError`).

---

## 0. Semantics register: documented vs. inferred

The calculus must model what `runcpu --rrrrate` actually does. Every semantic input is
classified as **[D]ocumented** (verbatim or directly paraphrased from SPEC's published
docs, verified 2026-06-12 against the raw HTML of `runcpu.html` §1.8, `monitors.html`,
`config.html` §IV.C) or **[A]ssumed** (inferred; must be confirmed by the first-install
checklist before any measured-data claim relies on it).

| ID | Rule | Class |
|----|------|-------|
| D1 | Copy `n`'s initial benchmark index is `n mod k` ("benchmark process number modulo the number of benchmarks"). | D |
| D2 | After each segment, the queue advances by `inc` = `--rrrrate_inc` (default 1), modulo `k`. | D |
| D3 | `inc = 0`: each copy runs only its initial benchmark (quick-validation idiom: `copies = k`, `iterations = 1`). Negative `inc` is a runcpu error. | D |
| D4 | All copies start simultaneously; there is **no further synchronization** between copies. | D |
| D5 | In the final iteration, copies that finish idle until all copies finish ("all cores will start idling and wait"). | D |
| D6 | Wrap rule: with `copies > k`, copies congruent mod `k` have **identical queues**. | D |
| D7 | `inc` not coprime to `k` ⇒ queues **skip benchmarks** (some benchmarks never run on some copies). | D |
| D8 | One run directory per (benchmark × copy × iteration); `--minimize_rundirs` silently overridden. Verification deferred to a parallel phase after the queues complete. | D |
| A1 | **Lap length**: for `inc ≥ 1` each iteration corresponds to exactly `k` queue steps, so each copy executes `k × iterations` segments; for `inc = 0`, one step per iteration. Basis: the `.rsf` record keying `NNN = iteration × copies + copynum` implies one record per (benchmark, iteration, copy) in the coprime case. For `gcd(inc, k) > 1` it is unverified whether runcpu keeps `k` steps per lap (each reachable benchmark visited `gcd` times per lap — the modeled variant) or shortens the lap to `k/gcd` steps. **First-install checklist item.** | A |
| A2 | **Back-to-back idealization**: the idealized timeline places a copy's segments end-to-start with zero gap. Real runs interleave setup/teardown slivers; therefore every *descriptive* claim about measured runs consumes **measured intervals** (timeline parser), and the idealization is used only for the *predictive* map `durations ↦ overlap` (T2's lap map) and for the cell geometry. | A |

The remaining first-install unknowns (CPU2026 `speccmds.out` record grammar, `.rsf` field
names, `$SPECCOPYNUM` expansion inside `monitor_wrapper` under RRR) are inputs to the
timeline parser, not to the calculus; they are tracked in the parser's provisional-grammar
block (`scripts/rrr_forge/timeline_parse.py`) and in the plan's AC-2 checklist.

---

## 1. Rotation schedules

**Definition 1 (rotation schedule).** A rotation schedule is a tuple
`σ = (B, C, I, M)` where `B = (b_0, …, b_{k−1})` is the ordered benchmark subset
(`k ≥ 1`, suite order), `C ≥ 1` the copy count, `I ≥ 0` the increment, `M ≥ 1` the
iteration count. Write `[m] = {0, …, m−1}`. The **queue map** of copy `n ∈ [C]` is

```
Q_n(j) = (n + j·I) mod k          for j ∈ [L],
L = k·M   if I ≥ 1        (A1)
L = M     if I = 0        (D3)
```

Copy `n` executes the benchmark sequence `b_{Q_n(0)}, b_{Q_n(1)}, …, b_{Q_n(L−1)}`;
`j` is the **slot** index, and slots `[t·k, (t+1)·k)` (resp. slot `t` when `I = 0`)
constitute **iteration** (lap) `t ∈ [M]`.

**Definition 2 (rotation subgroup).** Let `g(σ) = gcd(I, k)` for `I ≥ 1` and
`g(σ) = k` for `I = 0`. (The convention `gcd(0, k) = k` makes the second clause the
first; we keep it explicit because the lap length differs.)

The structural results are elementary number theory, but they are exactly the facts the
scoring axioms consume, so they are stated and proved once, here, and re-checked three
ways: by the simulator's property suite (exhaustive over the bounded grid
`k ∈ 2..6 × C ∈ 1..16 × I ∈ 0..k`), and later by `decide` in Lean over the same grid
(Tier-1).

**Theorem 1.1 (wrap rule ⇒ D6).** `Q_n = Q_{n'}` iff `n ≡ n' (mod k)`.

*Proof.* `Q_n(j) − Q_{n'}(j) ≡ n − n' (mod k)` for every `j`, so the queues coincide iff
`n ≡ n' (mod k)`; conversely congruent copies have identical queue maps pointwise. ∎

**Theorem 1.2 (coverage ⇒ D7).** The set of benchmark indices visited by copy `n` is the
residue coset

```
R_n = { m ∈ [k] : m ≡ n (mod g) },     |R_n| = k/g,
```

(for `I = 0` this reads `R_n = {n mod k}`, consistent with `g = k`). In particular every
copy visits every benchmark iff `g = 1`.

*Proof.* For `I ≥ 1` the image of `j ↦ n + j·I (mod k)` is the coset `n + ⟨I⟩` of the
subgroup `⟨I⟩ = g·Z_k` of order `k/g`; membership in `n + g·Z_k` is exactly congruence to
`n` mod `g`. For `I = 0` the image is `{n mod k}`. ∎

**Theorem 1.3 (per-copy equal incidence).** If `g = 1` (and `I ≥ 1`), every benchmark
occurs exactly once per lap on every copy, hence exactly `M` times per copy in total.

*Proof.* Within a lap, `j ↦ (n + j·I) mod k` for `j ∈ [k]` is a bijection on `[k]`
because `I` is invertible mod `k`. ∎

**Theorem 1.4 (aggregate incidence).** Let `N_b(σ)` be the total number of segments
running benchmark `b_m` summed over all copies. Then for `I ≥ 1`

```
N_{b_m} = M · g · #{ n ∈ [C] : n ≡ m (mod g) },
```

and for `I = 0`, `N_{b_m} = M · #{ n ∈ [C] : n ≡ m (mod k) }`. Consequently:

1. **(equal incidence)** `N_b = M·C` for every benchmark iff `g | C` (for `I = 0`:
   `N_b = M·C/k` iff `k | C`); in particular equal incidence always holds when `g = 1`.
2. **(failure is quantified)** if `g ∤ C`, the incidence spread is exactly
   `max_b N_b − min_b N_b = M·μ`, where `μ` is the per-lap visit multiplicity:
   `μ = g` for `I ≥ 1` and `μ = 1` for `I = 0`.
3. **(quick-validation idiom)** for `I = 0, C = k, M = 1`: `N_b = 1` for every `b` —
   each benchmark runs exactly once, matching D3's documented purpose.

*Proof.* By Theorem 1.2 copy `n` visits exactly the coset `R_n`; within one lap the cycle
`(n + j·I)_{j∈[k]}` has period `k/g` and is traversed `g` times, so each member of `R_n`
is visited exactly `g` times per lap, i.e. `M·g` times over the run. Benchmark `b_m`
belongs to `R_n` iff `m ≡ n (mod g)`. Counting copies in each residue class mod `g`:
the classes have size `⌈(C − r)/g⌉` for class representative `r`, all equal iff `g | C`
(then `C/g`), giving `N_b = M·g·(C/g) = M·C`; otherwise the largest and smallest class
sizes differ by exactly 1, giving spread `M` times the per-lap multiplicity (`g` for
`I ≥ 1`). The `I = 0` case is the same count with one visit per lap and classes mod `k`,
hence spread `M`. ∎

**Corollary 1.5 (equal-work dispatch).** Under the same-binary premise (identical
`x86-64-v3`-pinned binaries on both machines), a schedule with `g | C` dispatches exactly
the same multiset of benchmark executions — `M·C` per benchmark — on every machine. This
is the suite-level "equal work" property the scoring theory consumes; *per-copy* balance
additionally requires `g = 1` (Theorem 1.3). Note the refinement: aggregate equal
incidence does **not** require coprimality, only `g | C` — e.g. `k = 4, I = 2, C = 8` is
aggregate-balanced although every copy skips half the benchmarks.

---

## 2. Realized timelines

**Definition 3 (realized timeline).** A realized timeline over benchmarks `B` and copies
`[C]` is a finite set `T` of **segments** `σ = (n, b, t, [s, e))` — copy, benchmark,
iteration, half-open execution interval with `s, e ∈ Q`, `s < e` — satisfying the
**same-copy disjointness invariant**: intervals of segments on the same copy are pairwise
disjoint. (Half-open intervals make back-to-back segments disjoint by construction.)

Two constructions matter:

- **Measured timeline**: intervals taken from the timeline parser (layers 1–3 of the
  native SPEC outputs). Disjointness is *validated*, not assumed; violation means corrupt
  input (per A2 this is the only construction allowed to ground descriptive claims about
  real runs).
- **Idealized timeline** `T(σ, d)`: given a schedule `σ` and a **duration assignment**
  `d : (n, j) ↦ Q_{>0}`, set

  ```
  s(n, 0) = 0,    s(n, j+1) = s(n, j) + d(n, j),        (D4 + A2)
  T(σ, d) = { (n, b_{Q_n(j)}, ⌊j/τ⌋, [s(n,j), s(n,j) + d(n,j))) : n ∈ [C], j ∈ [L] }
  ```

  with `τ = k` for `I ≥ 1` and `τ = 1` for `I = 0`.

**Definition 4 (completion, makespan, tail idle).** `F_n = max{ e : (n,·,·,[s,e)) ∈ T }`,
makespan `T_max = max_n F_n`, tail idle `ι_n = T_max − F_n` (D5: the machine is not idle
*between* a copy's segments under the idealization; real timelines may also contain
inter-segment slack, which the same definitions handle since they are interval-level).
The tail-idle vector `(ι_n)_n` is the input to T5's tail-bias correction — it is signal,
not noise.

---

## 3. The overlap matrix

**Definition 5 (overlap matrix).** For a realized timeline `T` and benchmarks `a, b`:

```
O(a, b) = Σ  |J ∩ J'|
```

summed over ordered segment pairs `(σ, σ') ∈ T × T` with `copy(σ) ≠ copy(σ')`,
`bench(σ) = a`, `bench(σ') = b`, and `J, J'` their intervals. Units: copy-pair-seconds.

Conventions, fixed once: the sum is over **ordered** copy pairs, so `O(a, b) = O(b, a)`
by the pairing `(σ, σ') ↔ (σ', σ)`, and the diagonal `O(a, a)` counts each unordered
co-residency of two copies of `a` twice. The **overlap shares** are
`W(a, b) = O(a, b) / Σ_{a', b'} O(a', b')` whenever the denominator is positive.

**Theorem 1.6 (partition identity).** Fix a segment `σ = (n, a, t, J) ∈ T` and a copy
`n' ≠ n`. Let `coRes(σ, n', b) = Σ_{σ' on n', bench b} |J ∩ J'|` and
`idle(σ, n') = |J \ ⋃_{σ' on n'} J'|`. Then

```
Σ_b coRes(σ, n', b) + idle(σ, n') = |J|.
```

*Proof.* By same-copy disjointness on `n'`, the sets `{J ∩ J'}` over segments `σ'` of
copy `n'` are pairwise disjoint subsets of `J`; their measures therefore add, and the
complement within `J` is by definition `idle(σ, n')`. ∎

**Corollary 1.7 (row-sum accounting).** For every benchmark `a`:

```
Σ_b O(a, b) = Σ_{σ : bench a} ( (C−1)·|J_σ| − Σ_{n' ≠ copy(σ)} idle(σ, n') ).
```

This is the exact ledger tying the overlap matrix to total runtime and cross-copy idle;
it is the consistency check the simulator asserts on every computed matrix, and the
quantity through which tail idle (D5) enters the scoring theory.

**Theorem 1.8 (relabeling equivariance / anonymity hooks).** Let `π` be a bijection of
copy labels and `ρ` a bijection of benchmark names. Then `O` is invariant under `π`
(it never inspects copy identity beyond equality), and transforms by conjugation under
`ρ`: `O^ρ(ρa, ρb) = O(a, b)`.

*Proof.* Immediate from Definition 5: the sum ranges over unordered structure preserved
by `π`; renaming benchmarks renames the index set. ∎

This is the timeline-level fact behind the **anonymity** axiom (A1 of the axiom set,
M3): any score functional defined through `O` (or through the interval multiset)
automatically satisfies copy-anonymity, and benchmark-anonymity becomes a statement about
the score's dependence on the matrix alone.

---

## 4. Piecewise-linear structure and the cell decomposition

Fix a schedule `σ` and flatten the duration assignment to a vector
`d ∈ Q_{>0}^N`, `N = C·L`, in copy-major slot-minor order. All starts and ends of the
idealized timeline are `{0,1}`-linear forms in `d`:
`s(n, j) = Σ_{j' < j} d(n, j')`, `e(n, j) = s(n, j) + d(n, j)`.

**Definition 6 (difference forms, cells).** For each cross-copy segment pair
`p = (σ_1, σ_2)` let `Δ_p = { e_1 − s_2, e_2 − s_1, e_1 − e_2, s_1 − s_2 }`, a set of
four integer-coefficient linear forms (coefficients in `{−1, 0, 1}`), and let
`Δ(σ) = ⋃_p Δ_p` (a finite ordered list). The **cell signature** of `d` is

```
Σ(d) = ( sign(ℓ · d) )_{ℓ ∈ Δ(σ)} ∈ {−, 0, +}^{|Δ(σ)|},
```

and a **cell** is a nonempty level set of `Σ` inside the open positive orthant.

**Theorem 1.9 (cell decomposition).** For every schedule `σ`:

1. There are finitely many cells (at most `3^{|Δ(σ)|}`, with
   `|Δ(σ)| ≤ 4·(#cross-copy segment pairs)`); each is a relatively open convex cone
   (sign conditions on linear forms are convex and invariant under positive scaling).
2. On each cell, `d ↦ O(d) := O(T(σ, d))` is the restriction of a single linear map
   with integer coefficients.
3. Globally, `O` is continuous and positively homogeneous of degree 1:
   `O(λd) = λ·O(d)` for `λ ∈ Q_{>0}`.
4. The share map `W` is constant along rays and is a ratio of linear forms on each cell —
   the piecewise-rational structure quoted by T2/T3/T5.

*Proof.* (1) Finiteness and convexity are immediate; positive scaling preserves all signs.
(2) Each pairwise term `|J_1 ∩ J_2| = max(0, min(e_1, e_2) − max(s_1, s_2))` is, once the
four signs of `Δ_p` are fixed, either the zero form or one of the four linear forms
`{e_i − s_{j}}`-combinations selected by the signs (which of `e_1, e_2` is smaller, which
of `s_1, s_2` is larger, and whether the difference is positive); summing finitely many
linear forms per matrix entry gives a single linear map per cell. (3) Continuity holds
because `max/min` of continuous functions are continuous and the selected linear pieces
agree on sign-boundaries; homogeneity because every endpoint form is linear with zero
constant term. (4) Immediate from (2)–(3). ∎

**Definition 7 (lexicographic tie-breaking, Simulation-of-Simplicity).** On cell
boundaries (`ℓ·d = 0` with `ℓ ≠ 0`) the *bookkeeping* signature uses the symbolic
perturbation `d_ε = d + (ε, ε², …, ε^N)`:

```
sign*(ℓ, d) = sign(ℓ·d)                  if ℓ·d ≠ 0,
            = sign(first nonzero coefficient of ℓ)   if ℓ·d = 0, ℓ ≠ 0,
            = 0                                       if ℓ = 0 identically.
```

For sufficiently small `ε > 0` this equals `sign(ℓ · d_ε)` (the first nonzero coefficient
dominates the tail geometrically), so `Σ*` is a total, deterministic refinement of `Σ`
that assigns boundary points to an adjacent full-dimensional cell. `O` itself needs no
tie-breaking — it is continuous (Theorem 1.9.3); only the cell bookkeeping does.
Structural zero forms (`ℓ = 0`) do occur: e.g. the pair of first segments on any two
copies has `s_1 − s_2 = 0` identically (simultaneous start, D4); these receive the honest
sign `0` everywhere and never delimit cells.

**Remark (where the cells are consumed).** The cells of Theorem 1.9 are the strata on
which T2 proves the lap map monotone (and across whose boundaries the counterexample
catalog lives), and the semialgebraic pieces over which T3's genericity argument runs.
Getting them exactly right — including tie-breaking — is why the simulator is
exact-rational end to end.

---

## 5. Mapping to the executable artifact

| Object / result | Code | Verifying tests |
|---|---|---|
| Def 1, 2; Thm 1.1–1.4, Cor 1.5 | `scripts/rrr_forge/rotation.py` (`RotationSchedule`) | `tests/test_rotation.py`: exhaustive grid `k=2..6 × copies=1..16 × inc=0..k`; closed forms vs. direct counting; `test_rotation_full_coverage_requires_coprime_increment`; negative-increment rejection; quick-validation idiom |
| Def 3, 4; Def 5; Thm 1.6–1.8 | `scripts/rrr_forge/overlap.py` (`SegmentInterval`, `RealizedTimeline`, `OverlapMatrix`) | `tests/test_overlap.py`: hand-computed fixture; `test_overlap_matrix_partitions_segment_durations`; row-sum ledger; anonymity/conjugation; same-copy overlap rejection; float rejection (`ExactArithmeticError`) |
| Def 6, 7; Thm 1.9 | `scripts/rrr_forge/cells.py` | `tests/test_cells.py`: cell enumeration on fixtures (`k ≤ 3, copies ≤ 4`); exact midpoint-interpolation linearity certificates per cell; homogeneity; tie-break consistency with explicit `ε`-perturbation; structural-zero handling |
| Exactness discipline | `scripts/rrr_forge/exact.py` | float/complex inputs raise `ExactArithmeticError` at every construction site |

Lean Tier-1 re-proves Theorems 1.1–1.4 over the bounded grid by `decide`
(`formal/`, plan AC-8); the general-`k` statements above are one-line number theory and
will be stated in full generality there if the bounded `decide` form proves too weak for
the impossibility core's needs.

## 6. Open ends feeding other workstreams

- **A1 (non-coprime lap length)** and the parser grammars are first-install checklist
  items (plan AC-2 / task5); the calculus is parameterized so that resolving A1 the other
  way changes only `L` and `τ`, no theorem statements.
- The **partition identity** (Thm 1.6) is the bridge to the axiom set's
  *overlap-independence* axiom; the **row-sum ledger** (Cor 1.7) is where the
  tail-idle term that T5 corrects for enters.
- **Theorem 1.4.2's quantified failure** (`spread = M·g`) is a candidate axiom-violation
  witness for the satisfaction table (a schedule family on which "SPECrate-style
  equal-weight" misweights work even before contention enters).

## References

- SPEC CPU2026 `runcpu.html` §1.8, `monitors.html`, `config.html` §IV.C (raw-HTML
  verification of 2026-06-12; see `.humanize/plans/rrr-forge-plan-v2-theory-first.md`
  Feasibility notes for the verbatim items).
- Edelsbrunner & Mücke, *Simulation of Simplicity*, ACM TOG 1990 (symbolic perturbation).
- Proposal note §3 (T1–T5 statements), §2 (provability map row "overlap matrix exactly
  computable").
