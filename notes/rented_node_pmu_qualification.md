# Rented-Node Qualification Guide — Is This Server Usable for RRR Measurement Work?

**Audience:** Claude workers (and humans) in other sessions who are handed SSH access to a
rented/cloud node and must decide whether it can contribute to the RRR-Forge measurement
campaign on SPEC CPU2026.

**Scope:** qualification of the *measurement substrate* only. Experiment design lives in
`.claude/knowledge/rrr/rrr-cross-vendor-equal-work.md`; statistics gates live in
`references/notes/statistics_policy.md`; SPEC license rules live in the `spec-rules` skill.

**Authoritative project context (do not re-litigate):** the hardware matrix for the hero
experiment is the local pair — AMD Ryzen 9 9955HX (Zen 5) + Intel i9-12900 (Alder Lake,
P-cores only), both x86_64, identical `-march=x86-64-v3` binaries (DEC-7). Rented nodes are
*supplementary at most*. ARM instances are out of scope entirely (descope 2026-06-10).

---

## 1. The 30-second verdict procedure

A node earns one of five tiers. Every tier boundary is decided by one observable.

| Tier | Name | Deciding observable | Usable for |
|---|---|---|---|
| **A** | mechanism-grade | precise sampling works (IBS on AMD / PEBS `:ppp` on Intel) **and** uncore PMUs present | hero mechanism cases (DEC-8), bandwidth attribution — in practice: bare metal only |
| **A−** | core-mechanism | precise sampling works, **no** uncore | core-side mechanism only; no memory-bandwidth attribution |
| **B** | profile-grade | plain `perf record` works, precise fails | hotspots, IPC/MPKI vectors, black-box co-run timing (if enough cores) |
| **C** | counting-grade | `perf stat` counts, sampling fails | aggregate per-run counter vectors only |
| **D** | reject | no `cpu` PMU / software events only / syscall-emulated sandbox / persistent steal | nothing |

Fast triage, in order (details and mechanisms below):

```
ls /sys/bus/event_source/devices/        # inventory: kernel truth, cannot be faked
perf stat -e cycles,instructions -- <busy-loop>          # does counting work?
perf record -e cycles -F 999 -- <busy-loop>              # does sampling (PMI) work?
perf record -e cycles:pp -- <busy-loop>   (Intel)        # does PRECISE work?
perf record -e ibs_op// -- <busy-loop>    (AMD)          #   "      "      "
ls /sys/bus/event_source/devices/ | grep -E 'uncore|amd_l3|amd_df|amd_umc'
```

**Hard rule learned the hard way:** test plain sampling and precise sampling *separately*.
On AMD, a precise request (`cycles:p`) is internally routed to IBS; when IBS is absent the
perf tool can print `PMU Hardware doesn't support sampling/overflow-interrupts` — which
reads like "no sampling at all" but only means "no IBS". Plain `-F 999` sampling may still
work perfectly (it did on the Tencent SA9 case study in §6).

---

## 2. What the RRR experiment actually demands from a node

Each layer of the hero experiment consumes a specific hardware facility. If the facility is
absent, that layer of evidence cannot come from this node — there is no software workaround.

```
  Experiment layer                          Facility required            Min tier
  ───────────────────────────────────────────────────────────────────────────────
  Mechanism attribution of ranking          IBS (AMD) / PEBS (Intel)        A−
  inversions (DEC-8): which instructions/   = skidless, per-instruction
  ops stall, where, why                     sampling at retirement

  Memory-bandwidth / LLC contention side    uncore PMUs (CHA/IMC on          A
  of the co-run overlap story               Intel; L3/DF/UMC on AMD)

  Solo PMU vectors (TMA-ish buckets,        ≥6 core counters, vendor         B
  MPKI, instruction mix) feeding the        events (aliases or raw
  mixture model                             encodings), low multiplexing

  Hotspot sanity checks                     PMI-driven sampling              B

  Realized co-run overlap timelines         only timestamps + enough         C
  (who overlapped whom, for how long)       physical cores

  Equal-copies binding discipline           1 copy per PHYSICAL core,       (any,
  (rotation structure must be identical     SMT siblings idle, stable        but see
  across vendors; only speeds may differ)   pinning                          §5.7)

  Statistics gates (CV thresholds,          stable frequency, zero           (any)
  bootstrap CIs)                            steal time
```

The project consequence: **virtualized instances top out at Tier B** (AMD: always, because
IBS is never virtualized — §3.3; Intel: Tier A− is theoretically reachable on new hosts via
guest PEBS, §3.4, but uncore is never exposed). Mechanism-grade evidence requires bare
metal — the local pair, or bare-metal cloud families (Tencent CBM, Aliyun ebm\*).

---

## 3. Mechanisms: why virtualization strips exactly these facilities

### 3.1 The exposure funnel

PMU visibility is monotonically non-increasing down the stack. Each layer can only shrink
what the layer above granted. This is why "what if we enable nested virtualization?" is a
non-question: an L2 guest sees a subset of L1, which sees a subset of L0.

```
            PMU facility visibility through the virtualization stack
        (monotonically non-increasing; no layer can add a facility back)

  ┌────────────────────────────────────────────────────────────────────────┐
  │ L0  BARE-METAL HOST     core PMU ▪ PMI ▪ PEBS/IBS ▪ uncore ▪ MSR ▪ freq│
  └────────────────────────────────┬───────────────────────────────────────┘
                                   │ KVM vPMU policy — cloud-controlled
                                   ▼
  ┌────────────────────────────────────────────────────────────────────────┐
  │ L1  GUEST VM (the rented node)                                         │
  │     typical grant:  core counting ▪ maybe PMI                          │
  │     PEBS:   only Ice Lake+ hosts with explicit host opt-in (§3.4)      │
  │     IBS:    never — virtualization support not in mainline KVM (§3.3)  │
  │     uncore: never — socket-global, cross-tenant (§3.5)                 │
  └────────────────────────────────┬───────────────────────────────────────┘
                                   │ seccomp / capability filters — fixable
                                   ▼
  ┌────────────────────────────────────────────────────────────────────────┐
  │ CONTAINER on L1         whatever L1 has, minus syscall filters         │
  │   (a blocked perf_event_open here is container policy, not hardware)   │
  └────────────────────────────────┬───────────────────────────────────────┘
                                   │ nested KVM, if the vendor enabled it
                                   ▼
  ┌────────────────────────────────────────────────────────────────────────┐
  │ L2  NESTED GUEST        ⊆ L1 — nesting NEVER recovers a facility       │
  └────────────────────────────────────────────────────────────────────────┘
```

Diagnostic corollary: `ls /sys/bus/event_source/devices/` reports what the *running kernel*
registered. A container cannot hide or fake entries in it. If `ibs_op` or uncore PMUs are
absent there, the verdict is final at the hypervisor layer — no container flag, vendor
ticket about your container, or nesting trick changes it. If devices are present but
`perf_event_open` returns `EPERM`, suspect the container/sandbox layer (check
`grep Seccomp /proc/self/status` and `CapEff`), which *is* fixable.

### 3.2 Why counting usually survives virtualization

Core-counter *counting* is cheap to virtualize: KVM intercepts the guest's writes to the
counter-configuration MSRs, programs matching host perf events bound to that vCPU, and
context-switches counter state with the vCPU. No interrupt path is needed. This is why a
guest can show a live `AMD PMU driver` / `arch_perfmon` and produce accurate `perf stat`
output. Tencent notably upstreamed AMD PerfMon-v2 vPMU support (kernel 6.5), so their
newer AMD instances virtualize the full 6-counter Zen complement.

*Sampling* additionally requires delivering the counter-overflow interrupt (PMI) into the
guest (injected via the virtual LAPIC). KVM supports this, but a cloud may run with vPMU
fully or partially disabled — so counting-works/sampling-fails (Tier C) is a real
configuration. Test both; never infer one from the other.

### 3.3 AMD: precise sampling = IBS, and IBS is never in a VM

The AMD core PMU has **no precise mode**. Skidless, per-instruction attribution comes only
from IBS (Instruction-Based Sampling): dedicated hardware tags one fetch/op, then records
its full provenance at retirement — exact IP, physical address, cache/TLB hit level,
latency. `perf` exposes it as separate PMU devices `ibs_fetch` / `ibs_op`, and implements
the `:p`/`:pp` modifiers on AMD *by routing to IBS*.

KVM does not virtualize IBS. AMD posted a "VIBS" patch series (September 2023); it was
never merged — KVM merge coverage through Linux 7.0 shows other AMD features landing
(CET, Secure AVIC, x2AVIC, ERAPS) but not IBS. Therefore on **any** virtualized AMD
instance, from any vendor, regardless of size or price:

```
  no /sys/bus/event_source/devices/ibs_op  ⇒  no precise sampling  ⇒  ≤ Tier B
```

Do not spend money re-testing other AMD instance families hoping for IBS. The limit is
kernel-merge history, not vendor policy.

### 3.4 Intel: guest PEBS exists but is narrow

Intel's PEBS writes sample records to a memory buffer (DS area) in hardware. Historically
unvirtualizable (the host couldn't take page faults from PEBS writes); Ice Lake added
"EPT-friendly PEBS", and KVM gained guest-PEBS support in Linux 6.0 (authored largely by
Tencent engineers), extended to Sapphire Rapids (PDIR++/PDist). Requirements stack up:

- host CPU Ice Lake or newer, **and**
- host kernel ≥ 6.0 with KVM exposing PDCM/DS/DTES64 to the guest, **and**
- the host itself not using PEBS concurrently.

All three are L0 decisions you cannot see directly — so the test is empirical: does
`perf record -e cycles:ppp` succeed in the guest, and does `grep -ow pdcm /proc/cpuinfo`
show the capability bit? A passing Intel VM is Tier A− (core mechanism, still no uncore).

### 3.5 Why uncore never appears in guests

Uncore PMUs (Intel CHA/IMC/UPI; AMD L3/DF/UMC) count *socket- or CCX-global* traffic. They
cannot be sliced per-tenant: exposing them to one guest both leaks other tenants' memory
activity (side channel) and produces numbers that do not correspond to the guest's own
work. No mainstream hypervisor exposes them. Consequence: bandwidth-side contention
attribution is bare-metal-only, period.

### 3.6 Topology and SMT: the vCPU illusion

Cloud vCPUs are SMT *threads*, normally sold in sibling pairs. Check the truth:

```
cat /sys/devices/system/cpu/cpu0/topology/core_cpus_list
```

```
        physical core 0
       ┌───────────────────┐
       │   vCPU0    vCPU1  │      core_cpus_list: 0-1
       └───────────────────┘      ⇒ a "2 vCPU" instance is ONE physical core
```

The equal-copies discipline (identical rotation structure across vendors, one copy per
physical core, siblings idle) therefore needs **2×k vCPUs for k copies**, and even then the
guest cannot control the vCPU→pCPU mapping or guarantee it is stable across the run. The
guest's `smt/control` knob only offlines its own sibling vCPUs — it does not give you a
dedicated physical core unless the instance type guarantees it.

### 3.7 Frequency and steal: the statistics killers

Guests get no cpufreq interface (`/sys/devices/system/cpu/cpu0/cpufreq/` absent) — the host
governs clocks invisibly. The only observable is realized GHz from `perf stat`
(cycles ÷ task-clock); record it per run into the environment manifest. Steal time
(`vmstat` `st` column) is cycles the hypervisor gave to someone else: any persistent
non-zero value invalidates timing comparisons. Both failure modes surface as inflated CV —
the statistics policy's escalation rules treat that as signal, not noise to average away.

---

## 4. The qualification protocol

Run as root (`sudo su`). Stages are ordered so that early exits save money.

### Stage 0 — what AM I running on?

```bash
[ -f /.dockerenv ] && echo "container (docker)"
cat /proc/1/cgroup            # init.scope ⇒ full VM/host; docker/kubepods ⇒ container
cat /proc/version             # gVisor or odd kernel string ⇒ syscall sandbox ⇒ Tier D
cat /proc/self/uid_map        # "0 0 4294967295" ⇒ no userns remap
grep -E 'Seccomp|CapEff' /proc/self/status     # Seccomp: 2 ⇒ filtered sandbox
P=$(cat /proc/sys/kernel/perf_event_paranoid)
echo "$P" > /proc/sys/kernel/perf_event_paranoid 2>/dev/null \
  && echo "sysctl writable (real root)" || echo "read-only (sandboxed)"
```

### Stage 1 — identity (the instance lottery)

Some instance families are backed by several host CPU models; allocation can change across
recreations. Record per instance, every time:

```bash
lscpu | grep -E 'Model name|Vendor ID|Socket|Core|Thread|L3|Hypervisor'
grep -m1 -E 'cpu family|^model[[:space:]]|stepping' /proc/cpuinfo
cat /sys/class/dmi/id/sys_vendor /sys/class/dmi/id/product_name 2>/dev/null
```

Notes: brand strings may be custom SKUs (e.g. "AMD EPYC 9K65" = Tencent-custom Turin);
identify by family/model (family 25 = Zen 3/4, family 26 = Zen 5). A `Hypervisor vendor`
line or the `hypervisor` CPUID flag ⇒ VM. Dense parts (Bergamo / Turin-D = Zen 4c/5c) and
E-core-only parts (Sierra Forest) have different cache hierarchies — never mix them into a
vendor pair silently.

### Stage 2 — tooling + knobs

```bash
apt-get update && apt-get install -y linux-tools-common linux-tools-$(uname -r) procps
perf --version    # if the wrapper rejects a kernel mismatch (custom cloud kernels):
                  # PERF=$(find /usr/lib/linux-tools* -name perf | head -1)
sysctl -w kernel.perf_event_paranoid=-1
cat /proc/sys/kernel/nmi_watchdog     # 1 steals a counter; set to 0 for campaigns
```

### Stage 3 — PMU inventory (kernel truth)

```bash
ls /sys/bus/event_source/devices/
cat /sys/bus/event_source/devices/cpu/caps/pmu_name 2>/dev/null   # Intel only
dmesg | grep -A4 'Performance Events'
```

Read the dmesg block carefully — it is the vPMU's self-description:

```
Performance Events: Fam17h+ core perfctr, AMD PMU driver.   ← live driver (good)
... generic registers:      6                               ← counter count
Performance Events: ... software events only.               ← Tier D, stop here
```

### Stage 4 — counting fidelity and counter arithmetic

```bash
BUSY="sh -c 'i=0; while [ \$i -lt 2000000 ]; do i=\$((i+1)); done'"
perf stat -e task-clock,cycles,instructions,branches,branch-misses,cache-references,cache-misses -- sh -c 'i=0; while [ $i -lt 2000000 ]; do i=$((i+1)); done'
perf stat -e cycles,instructions,branches,branch-misses,cache-references,cache-misses,stalled-cycles-frontend,stalled-cycles-backend -- sh -c 'i=0; while [ $i -lt 2000000 ]; do i=$((i+1)); done'
```

Interpretation:
- `<not supported>` / `<not counted>` rows ⇒ that event has no backing counter.
- Trailing `(NN.NN%)` annotations = multiplexing. The arithmetic identifies the virtual
  counter count: N active hardware events sharing K counters each get ≈ K/N of wall time.
  Seven events all showing `(85.71%)` ⇒ 6/7 ⇒ **K = 6 counters** (cross-check dmesg).
  The first command above carries 6 hardware events (task-clock is software) and should
  show *no* percentages on a 6-counter vPMU; the second oversubscribes deliberately.
- Sanity-check magnitudes: a tight shell arithmetic loop should show high IPC (≈4–5 on
  Zen 5), near-zero branch misses, near-zero cache misses. Garbage values ⇒ distrust the
  vPMU entirely.

### Stage 5 — sampling, then precise sampling (separately!)

```bash
# 5a. plain sampling — tests PMI virtualization only
perf record -o /tmp/s.data -e cycles -F 999 -- sh -c 'i=0; while [ $i -lt 5000000 ]; do i=$((i+1)); done' \
  && echo SAMPLING-OK

# 5b. precise — the mechanism gate. AMD path:
ls /sys/bus/event_source/devices/ | grep -E '^ibs' || echo "NO IBS  =>  <= Tier B on AMD"
perf record -o /tmp/i.data -e ibs_op// -- sh -c 'i=0; while [ $i -lt 5000000 ]; do i=$((i+1)); done' \
  && echo IBS-OK
# 5b'. Intel path:
grep -m1 -ow pdcm /proc/cpuinfo || echo "PDCM hidden => no guest PEBS"
perf record -o /tmp/p.data -e cycles:ppp -- sh -c 'i=0; while [ $i -lt 5000000 ]; do i=$((i+1)); done' \
  && echo PEBS-OK
```

Trap (worth repeating): on AMD, the failure message for `cycles:p` without IBS can claim
the PMU "doesn't support sampling/overflow-interrupts". It is talking about the IBS path
only. 5a is the ground truth for sampling; 5b for precise.

### Stage 6 — vendor events: aliases vs raw encodings

```bash
perf list 2>/dev/null | grep -cE 'de_no_dispatch|ls_any_fills|topdown'
```

Zero has **two distinct causes** — distinguish them, they have opposite consequences:

1. *CPUID model masked by the hypervisor* ⇒ perf cannot know the event tables; raw events
   are also untrustworthy. (Rare on KVM; family/model usually passes through.)
2. *perf tool predates the CPU* (e.g. perf 6.8 has no Zen 5 / Turin JSON tables) ⇒ aliases
   are missing but **raw encodings work fine**:

```bash
perf stat -e r076,rC0 -- sh -c 'i=0; while [ $i -lt 2000000 ]; do i=$((i+1)); done'
# r076 must ≈ the `cycles` count, rC0 ≈ `instructions`. Match ⇒ cause 2; build the
# event set from raw codes:  -e cpu/event=0xEE,umask=0xUU/  (vendor PPR/SDM encodings)
```

### Stage 7 — uncore, topology, control surfaces

```bash
ls /sys/bus/event_source/devices/ | grep -E 'uncore|amd_l3|amd_df|amd_umc|cha|imc' || echo NO-UNCORE
cat /sys/devices/system/cpu/smt/control 2>/dev/null
cat /sys/devices/system/cpu/cpu0/topology/core_cpus_list
nproc
ls /sys/devices/system/cpu/cpu0/cpufreq/ 2>/dev/null || echo "no cpufreq control"
```

### Stage 8 — noise floor

```bash
vmstat 1 10        # 'st' column: any persistent non-zero = noisy neighbor, fails gating
# repeat Stage 4's perf stat 5×; compute CV of cycle counts — feeds the statistics policy
```

### Stage 9 — evidence ledger

Write the raw outputs of every stage into `references/notes/preflight_<host>.md` (repo
convention), together with: date, vendor, region/zone, instance type, hourly price, brand
string, family/model, counter count, realized GHz, and the tier verdict. Counters that
need facilities the node lacks are recorded as `unavailable` in the equivalence-class
table — the table policy refuses to populate those cells rather than approximating.

---

## 5. Decision rubric

```
              ┌──────────────────────────────────────────────┐
              │ Stage 0: gVisor / fake root unfixable / VM    │
              │ image is syscall-emulated                     │──────► TIER D
              └──────────────┬───────────────────────────────┘
                             │ clean VM or bare metal
                             ▼
              ┌──────────────────────────────────────────────┐
              │ Stage 3: `cpu` PMU absent or "software        │──────► TIER D
              │ events only"                                  │
              └──────────────┬───────────────────────────────┘
                             │ PMU present
                             ▼
              ┌──────────────────────────────────────────────┐
              │ Stage 4: counts wrong / heavy `<not           │──────► TIER D
              │ supported>` on basics                         │
              └──────────────┬───────────────────────────────┘
                             │ counting OK
                             ▼
              ┌──────────────────────────────────────────────┐
              │ Stage 5a: plain sampling works?               │──no──► TIER C
              └──────────────┬───────────────────────────────┘
                             │ yes
                             ▼
              ┌──────────────────────────────────────────────┐
              │ Stage 5b: precise (IBS / PEBS:ppp) works?     │──no──► TIER B
              └──────────────┬───────────────────────────────┘
                             │ yes
                             ▼
              ┌──────────────────────────────────────────────┐
              │ Stage 7: uncore PMUs present?                 │──no──► TIER A−
              └──────────────┬───────────────────────────────┘
                             │ yes (you are on bare metal)
                             ▼
                          TIER A
```

Tier is necessary, not sufficient. A Tier B node with 2 vCPUs (1 physical core) still
cannot host a co-run mix; a Tier A node with persistent steal still fails statistics
gating. Size, steal, and frequency stability are orthogonal gates from Stages 7–8.

---

## 6. Worked case study — Tencent CVM "SA9", 2026-06-12

Instance: 2 vCPU SA9 (standard family), Ubuntu 24.04, kernel 6.8.0-117-generic.

| Stage | Observed | Reading |
|---|---|---|
| 0 | `/proc/1/cgroup` = `0::/init.scope`, no `/.dockerenv`, sysctl writable after `sudo su` | full VM, real root — not a container, despite initial assumption |
| 1 | `AMD EPYC 9K65 192-Core` (custom Tencent Turin SKU), `cpu family: 26` (Zen 5 passthrough), `Hypervisor vendor: KVM`, BIOS vendor "Red Hat" (QEMU) | identity nailed; lottery result recorded |
| 3 | devices: `breakpoint cpu kprobe msr software tracepoint uprobe`; dmesg: `Fam17h+ core perfctr, AMD PMU driver`, `generic registers: 6`, `bit width: 48` | live vPMU with the full 6-counter Zen complement; **no `ibs_*`, no uncore** |
| 4 | 6-event `perf stat` un-multiplexed; 7-event run all at `(85.71%)` = 6/7; busy-loop IPC 4.75–4.80, ~0% branch & cache misses; realized 3.72 GHz | counting accurate; counter arithmetic confirms 6 |
| 5a | `perf record -e cycles -F 999` → **3,432 samples captured** | PMI is virtualized — sampling works |
| 5b | `ibs_*` absent; `cycles:p` → "PMU Hardware doesn't support sampling/overflow-interrupts" | precise unavailable; error message is the misleading IBS-path one (§4 Stage 5 trap) |
| 6 | `perf list` aliases = 0, **but** `r076` ≈ `cycles` and `rC0` ≈ `instructions` exactly | perf 6.8 simply predates Turin JSON tables; raw encodings fully usable |
| 7 | no uncore; `core_cpus_list: 0-1` ⇒ 2 vCPUs = 1 physical core; no cpufreq | too small for any co-run; no frequency control |
| 8 | steal 0 over the sampled window (idle box) | clean so far; re-check under load |

**Verdict: Tier B (profile-grade), at an unusable size.** The node could supply hotspots
and aggregate counter vectors via raw encodings on a larger sibling instance, but never
mechanism-grade evidence: IBS absence is a mainline-KVM fact (§3.3), uniform across all
virtualized AMD instances of every vendor. The interesting positive finding is that
Tencent's vPMU is unusually complete (accurate 6-counter counting *and* working PMI/
sampling) — consistent with Tencent engineers having authored much of KVM's vPMU/guest-PEBS
work. An Intel CVM instance on an Ice Lake+/SPR host is worth one cheap probe (Stage 5b'
may pass ⇒ Tier A−) if core-side Intel data from a server part is ever needed.

---

## 7. Standing conclusions for this project

1. **The hero matrix stays local** (9955HX + i9-12900): both are bare metal ⇒ Tier A
   facilities (IBS/PEBS, uncore, SMT and frequency control) plus zero rental cost.
2. **Virtualized AMD nodes can never reach the mechanism gate** — stop probing for IBS in
   VMs; it is not a configuration problem.
3. **Bare-metal cloud families (Tencent CBM, Aliyun ebm\*) are the only rented option for
   Tier A** — relevant solely for an optional server-class robustness appendix; pick
   standard-core SKUs (Genoa/Turin classic, Ice Lake+/SPR), never dense (Bergamo/Turin-D)
   or E-core (Sierra Forest) parts, and never ARM (descoped).
4. **License hygiene on rented nodes:** SPEC materials may be installed on machines under
   our control, but **never** baked into reusable cloud images or snapshots (that is
   redistribution). Wipe SPEC trees before releasing an instance; run
   `redistribution_audit.py` thinking before snapshotting anything.
5. Every probed node gets a `references/notes/preflight_<host>.md` evidence ledger, even
   (especially) the failures — negative results stop the next session from paying to
   rediscover them.

---

## 8. References

Project knowledge base:
- `.claude/skills/perf-pmu/SKILL.md` — paranoid ladder, equivalence-class cell labels, vendor PMU posture
- `.claude/skills/top-down/SKILL.md` — TMA buckets; AMD derived top-down needs vendor events
- `.claude/knowledge/rrr/rrr-cross-vendor-equal-work.md` — the hero experiment these tiers gate
- `.claude/memory/descope_2026-06-10.md` — matrix = 1 Intel + 1 AMD x86_64; ARM terminated
- `references/notes/statistics_policy.md` — CV gating that steal/throttling trips

External (verified 2026-06-12):
- KVM guest PEBS via DS area — https://lwn.net/Articles/841660/ (landed Linux 6.0, Ice Lake+; Phoronix: https://www.phoronix.com/news/Linux-6.0-KVM)
- Sapphire Rapids guest PEBS enablement (Tencent-authored) — https://lore.kernel.org/lkml/20220921064827.936-1-likexu@tencent.com/T/
- AMD IBS virtualization ("VIBS") series, unmerged — https://lore.kernel.org/all/20230908133114.GK19320@noisy.programming.kicks-ass.net/T/
- KVM merge coverage through Linux 7.0 (no VIBS) — https://www.phoronix.com/news/Linux-7.0-KVM
- Tencent vPMU contributions (AMD PerfMon-v2, guest PEBS) — https://blog.csdn.net/csdnnews/article/details/131467250
