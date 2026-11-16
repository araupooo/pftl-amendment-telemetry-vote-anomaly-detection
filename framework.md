# PFTL Amendment Telemetry and Vote-Anomaly Detection Framework

A reference framework for how operators of a PFTL-style validator network
can monitor amendment activation and detect anomalous validator voting
before an amendment activates wrongly. It is accompanied by a runnable
reference detector (`detector.py`), a deterministic synthetic-vote
simulator (`simulator.py`), and measured detection results
(`detection-table.md`, produced by `run_drill.py`).

Every substantive claim in this document carries exactly one label:

- **[FAKTA]** — a verified fact, with its source and access date.
- **[ESTIMASI]** — a modelled or reported number; the model or report is
  named so the number can be re-derived.
- **[ANALISIS]** — an interpretation or recommendation; not a fact.

## 1. Why amendment voting needs telemetry

[FAKTA] On the XRP Ledger, amendments are transaction-processing changes
that validators vote on, and an amendment passes only after it holds more
than 80% support from trusted validators for two weeks, after which the
change applies permanently to all subsequent ledger versions
(xrpl.org, Amendments, accessed 2026-11-17). [FAKTA] If support drops
below 80% at any point, the amendment is temporarily rejected and the
two-week period restarts (same source). [ANALISIS] The two-week rule is
the network's only defence against a transient or manipulated majority:
telemetry that cannot see support falling, validators disappearing, or
votes arriving late cannot warn anyone before the clock runs out — or
before a bad majority is locked in. [ANALISIS] That is the gap this
framework closes: it watches the vote stream at flag-ledger granularity
and raises alerts while there is still time to investigate, escalate,
or roll back a vote.

## 2. How amendment activation works — PFTL vs XRPL

### 2.1 The XRPL baseline

[FAKTA] Every 256th ledger is a flag ledger, and the amendment process
happens around it: at flag ledger −1 validators submit amendment votes
with their validations; at the flag ledger servers interpret the votes;
at flag ledger +1 servers insert an `EnableAmendment` pseudo-transaction
flagged `tfGotMajority` (more than 80% support), `tfLostMajority`
(support fell to 80% or less), or unflagged (the amendment is enabled);
at flag ledger +2 an enabled amendment applies to transactions
(xrpl.org, Amendments, accessed 2026-11-17). [FAKTA] Flag ledgers occur
typically about 15 minutes apart on XRPL mainnet (same source).
[FAKTA] Only votes from trusted validators count, and a server's default
vote for an amendment it has not configured comes from the source code
(same source). [FAKTA] Amendments whose source code was removed without
being enabled are considered vetoed by the network (same source).

### 2.2 The PFTL rule is different — 67%, not 80%

[FAKTA] postfiatd (the PFTL node implementation, a rippled fork) defines
its amendment majority threshold in
`include/xrpl/protocol/SystemParameters.h` (commit `0085a1ff`,
verified live from the postfiatd repository on 2026-11-17, lines 148–156):

```cpp
constexpr std::ratio<204, 256> preFixAmendmentMajorityCalcThreshold;
constexpr std::ratio<67, 100> postFixAmendmentMajorityCalcThreshold;
constexpr std::chrono::seconds const defaultAmendmentMajorityTime =
    std::chrono::weeks{2};
```

[FAKTA] The same file's comment says the 204/256 value "is used by
legacy code and will become obsolete once the fixAmendmentMajorityCalc
amendment activates". [FAKTA] `AmendmentTable.cpp` computes the threshold
as `max(1, trustedValidations * ratio)` and passes an amendment when
votes are `>= threshold` under the pre-fix rule or `> threshold` under
the post-fix rule (strictly greater), with a one-validator exception
(postfiatd `src/xrpld/app/misc/detail/AmendmentTable.cpp`, `computeThreshold` lines 615–647 and `passes` lines 679–712, commit `0085a1ff`, verified live 2026-11-17).
[FAKTA] The `fixAmendmentMajorityCalc` amendment itself is registered
as supported with default-yes voting in
`include/xrpl/protocol/detail/features.macro:201` (same commit).
[FAKTA] Upstream rippled 2.3.0 defines the post-fix threshold as
80/100 in the same file, and current upstream master uses a single
`kAmendmentMajorityCalcThreshold` of 80/100 (verified from
raw.githubusercontent.com/XRPLF/rippled on 2026-11-17). [ANALISIS] So
postfiatd diverges from upstream XRPL here: once
`fixAmendmentMajorityCalc` is enabled on a PFTL network, an amendment
needs only a 67% majority, not 80%.

[FAKTA] The default majority-hold time is two weeks (postfiatd
`SystemParameters.h`, `defaultAmendmentMajorityTime`, commit
`0085a1ff`, verified live 2026-11-17). [ANALISIS] Rippled-derived
deployments expose the hold time as a per-node setting
(`amendment_majority_time`); whether a given PFTL node does, and any
minimum value, was not verified from source for this pack — treat the
two-week default as the baseline and confirm the in-force value from
observed `EnableAmendment` outcomes. [ANALISIS] Whether `fixAmendmentMajorityCalc` is itself
already enabled on the PFTL testnet cannot be determined from the
source code — the amendment must itself gain a majority to activate —
so an operator cannot assume which threshold is in force from the
source alone. The detector in this pack therefore takes the majority
rule as a parameter and supports all three: `pftl-post-fix` (67/100,
strict), `pftl-pre-fix` (204/256, `>=`), and `xrpl-post-fix` (80/100,
strict). [ANALISIS] An operator should confirm the in-force rule from
observed `EnableAmendment` outcomes, not from the binary version.

### 2.3 Votes needed — the arithmetic

[ESTIMASI] The table below is computed by `run_drill.py` from the
ratios in section 2.2 (threshold = max(1, floor(N × ratio)); the
amendment passes at threshold + 1 votes under strict rules, or at
threshold votes under the pre-fix rule):

| UNL size | PFTL pre-fix 204/256 (>=) | PFTL post-fix 67/100 (>) | XRPL post-fix 80/100 (>) |
|---|---|---|---|
| 35 | 27 votes (77.1%) | 24 votes (68.6%) | 29 votes (82.9%) |
| 53 | 42 votes (79.2%) | 36 votes (67.9%) | 43 votes (81.1%) |

[ANALISIS] At the PFTL testnet scale of 53 validators, the post-fix
rule lets an amendment through with 7 fewer yes-votes than the XRPL
rule (36 vs 43). [ANALISIS] The practical consequence for telemetry:
a support level of 70% is a comfortable majority on PFTL and a lost
majority on XRPL — the same vote stream is safe on one network and an
incident on the other, so thresholds must be parameterised per network
and never copied from XRPL documentation. [ESTIMASI] The 53-validator
figure is the reported size of the PFTL testnet validator set as of
September 2026; it was not re-verified live for this pack, and the
table therefore also shows the 35-validator default-UNL scale for
comparison.

### 2.4 The surrounding machinery a monitor must watch

[FAKTA] The standard consensus quorum is 80% of trusted validators
(xrpl.org, Negative UNL, accessed 2026-11-17). [FAKTA] Each server
tracks each trusted validator's reliability as the percentage of the
last 256 ledgers where that validator's validation vote matched the
server's view of consensus (same source). [FAKTA] A validator with
reliability below 50% is a candidate to be added to the Negative UNL,
and one above 80% is a candidate to be removed (same source).
[FAKTA] The Negative UNL can change by at most one addition and one
removal per flag ledger, is proposed via `UNLModify` pseudo-transactions,
and cannot reduce the quorum below 60% of total UNL entries — a server
treats it as full at 25% of its configured UNL (same source).
[FAKTA] postfiatd logs the vote count at every voting round
(`AmendmentTable.cpp`, line 1612: `JLOG(j_.debug()) << "Counted votes from " << vote->trustedValidations() ...`, verified live 2026-11-17) — a ready-made telemetry
signal operators can scrape without new instrumentation.

## 3. Vote signals to watch

| # | Signal | Source in the node | Cadence | Why it matters |
|---|---|---|---|---|
| S1 | Amendment support % (yes-votes / trusted validations) | `feature` RPC; `EnableAmendment` flags; `AmendmentTable` vote log | Every flag ledger | The activation variable itself; see section 2.3 |
| S2 | Majority-clock state (gained/lost, hold duration) | `EnableAmendment` `tfGotMajority` / `tfLostMajority` | Every flag ledger | A lost majority restarts the two-week clock |
| S3 | Per-validator agreement / reliability | Validation votes vs ledger outcome, trailing 256 ledgers | Every flag ledger | The Negative UNL input; a falling validator is a candidate for exclusion |
| S4 | Validation arrival timing (lag in flag ledgers) | Validation message timestamps | Every ledger | Late votes look like missing votes and depress apparent support |
| S5 | Duplicate / stale validations | Validation stream (validator, ledger sequence) | Every ledger | Replays inflate or confuse the vote count |
| S6 | Online validator set (UNL membership, online share) | Peer/validation presence | Every flag ledger | Below 80% online, the consensus quorum itself is at risk |
| S7 | Negative UNL membership and size | `NegativeUNL` ledger object; `UNLModify` pseudo-transactions | Flag ledgers only | Shows the network's own verdict on who is unreliable |

[ANALISIS] S1–S3 are the activation-critical signals; S4–S7 explain
*why* S1 moved. A monitor that records only S1 can say an amendment
lost its majority, but not whether the cause was drift, churn, timing,
or replay — and the response differs for each.

## 4. Detection rules (reference implementation: `detector.py`)

All rules operate on flag-ledger records. Thresholds are proposed
values, not PFTL-official; each rule's rationale names its source.

| Rule | Condition | Severity | Rationale / source |
|---|---|---|---|
| R1 | 10-flag-ledger mean support falls ≥6 pp vs the previous 10 ledgers (≥9 pp: CRITICAL) | WARNING / CRITICAL | Drift must be caught before any threshold crossing; the 10-ledger window keeps noise near ±1.3 pp at n=53 (binomial model, [ESTIMASI]) |
| R2 | Amendment not passing for 2 consecutive flag ledgers after previously passing | CRITICAL | Encodes the majority-clock reset; `tfLostMajority` is the same event in the ledger (xrpl.org Amendments [FAKTA]) |
| R3 | 10-flag-ledger mean support within 3 pp above the majority threshold | WARNING | A majority this thin is lost by a handful of flips; uses the rolling mean because per-ledger noise (±6.7 pp at 62% support, n=53 [ESTIMASI]) makes a fixed threshold flicker |
| R4 | A validator's agreement with the ledger majority over the trailing 16 flag ledgers is below 50% while network support is ≥80% (below 50% for 3 consecutive ledgers: CRITICAL) | WARNING / CRITICAL | Mirrors the Negative UNL bands <50% add / >80% remove (xrpl.org Negative UNL [FAKTA]); the health gate suppresses it during drift, when low agreement is network-wide, not a single-validator fault |
| R5 | ≥3 validators' votes arrive >2 flag ledgers late in one flag ledger (≥6: CRITICAL) | WARNING / CRITICAL | Late votes depress apparent support; 2 ledgers of lag is beyond normal propagation at flag-ledger granularity [ANALISIS] |
| R6 | Any duplicate or stale validation in a flag ledger (>5% of the ledger's messages: CRITICAL) | WARNING / CRITICAL | Duplicates/stales are never legitimate in a healthy stream; the 5% bound separates an isolated glitch from a replay campaign [ANALISIS] |
| R7 | Online validator set changes >10% within 5 flag ledgers (>20%: CRITICAL) | WARNING / CRITICAL | Symmetric difference of the online sets; 12 of 53 validators leaving is 22.6% [FAKTA from the drill config] |
| R8 | Online validators below 80% of the configured UNL | CRITICAL | The consensus quorum floor (xrpl.org Negative UNL [FAKTA]) |

[ANALISIS] Rules for persistent states (R1, R2, R3, R5, R7, R8) are
edge-triggered with hysteresis: they fire when the condition starts
and re-arm only after a clear recovery (R1/R5 on the condition
clearing, R2 after 5 consecutive passing ledgers, R3 after the mean
leaves the band by 5 pp above or 2 pp below, R4 after agreement
recovers to 80%). Without this, one stuck condition produces one
alert per flag ledger — the first version of this detector produced
120 R8 alerts in a single 120-ledger run. R6 stays per-ledger because
each ledger's bad messages are distinct evidence.

## 5. Alerting, escalation, and rollback triggers

[ANALISIS] The following procedure is proposed for operators; it is a
recommendation, not a PFTL rule.

1. **WARNING (any rule):** log with the flag-ledger index, rule, and
   detail; include in the next scheduled operator review (within one
   flag-ledger cycle, ~15 minutes). No vote change.
2. **CRITICAL R1/R2/R3 (majority at risk):** page the on-call operator
   immediately. Actions: verify the support count from an independent
   node (a second UNL view — different servers can score the same
   validator differently, xrpl.org Negative UNL [FAKTA]); check whether
   the validators driving the fall are the same set across ledgers
   (coordinated) or scattered (noise); if the amendment is one the
   operator supports, prepare to flip the vote to `no` before the
   majority clock completes — a flipped vote removes support and, if
   enough operators do the same, stops activation.
3. **CRITICAL R5/R6 (timing/replay):** page the on-call operator.
   Actions: check the affected validators' network paths and clocks;
   a replay campaign (R6 CRITICAL) is treated as a possible attack
   until proven otherwise — preserve the raw validation stream.
4. **CRITICAL R7/R8 (churn/quorum):** page immediately. Actions: if
   online share is below the 80% quorum floor, consensus itself is at
   risk — this outranks any amendment concern. Check Negative UNL
   membership: if the missing validators are being added to it, the
   network is already compensating; if not, the outage is too sudden
   for the Negative UNL's one-change-per-flag-ledger rate to absorb.
5. **Rollback trigger:** an amendment that gained a majority while any
   CRITICAL alert was open for that amendment's vote stream should be
   treated as suspect: the operator's default response is to vote `no`
   (or veto, if the amendment is already enabled and a superseding
   amendment exists — enabling is one-way, xrpl.org Amendments
   [FAKTA]). [ANALISIS] There is no in-protocol "un-enable"; prevention
   before activation is the only rollback, which is why detection
   latency is measured in flag ledgers, not hours.

## 6. Threshold tradeoffs (measured)

[FAKTA] The measured results are in `detection-table.md`; the headline
numbers from `run_drill.py` (5 seeds per scenario, 53 validators, 120
flag ledgers, injection at flag ledger 40) are: every anomaly type is
detected in all 5 runs (TPR 1.00); median detection latency is 0 flag
ledgers for churn and replay, 3 for timing skew, and 9 for quorum drift;
the false-positive rate on normal traffic is 0.333 WARNING+ alerts per
100 flag ledgers (2 alerts in 600 flag ledgers: one R1, one R4).
[ANALISIS] The tradeoffs behind those numbers:

- **R1 at 6 pp (not 5 pp):** an earlier tuning run at 5 pp produced a
  noise-triggered R1 warning on normal traffic; 6 pp removes that
  specific trigger while adding roughly 2 flag ledgers of drift latency
  (the drift falls ~0.93 pp per flag ledger). Lowering the threshold
  buys latency with false positives; raising it buys quiet with delay.
- **R3 on the rolling mean (not instantaneous support):** the first
  version used instantaneous support and produced 39 thin-majority
  alerts in 5 drift runs, because per-ledger support noise (±6.7 pp)
  repeatedly re-crossed the threshold. The 10-ledger mean (±2.1 pp)
  cut that to 7 with no loss of detection.
- **R4 gated on network health:** the first version fired 40–59
  disagreement warnings per drift run, because when support falls
  every validator's agreement with the majority degrades. Gating R4
  on support ≥80% removes those; it fires only when the network
  agrees and one validator does not.
- **R6 has no tuning knob that helps:** duplicates and stales are
  binary — present or absent — so the rule is exact on synthetic data
  and its false-positive rate on normal traffic is zero by
  construction. On live data, a single duplicated validation from a
  retransmitting peer would be a false positive; operators should
  confirm the 5% CRITICAL bound against their own retransmission rate.

## 7. Limitations

- [ANALISIS] All detection numbers come from synthetic vote streams,
  not live-network data. The simulator models vote timing, drift,
  churn, and replay at flag-ledger granularity; it does not model
  network propagation, peer topology, clock skew between nodes, or
  real validator behaviour. A detector that scores 1.00 TPR on
  synthetic data has proven its logic, not its live performance.
- [ANALISIS] The simulation window is 120 flag ledgers (~30 hours at
  15 minutes per flag ledger). The real majority clock is two weeks
  (about 1,200–1,350 flag ledgers at a 3.5–4 second ledger close time
  [ESTIMASI]); the drill measures detection latency, not activation,
  and the majority-clock tracking in R2 is per-ledger, not
  time-weighted.
- [ANALISIS] The 53-validator scale is the reported PFTL testnet size
  (September 2026) and was not re-verified live; results at other UNL
  sizes will differ, and the threshold table shows both 35 and 53 for
  that reason.
- [ANALISIS] Which majority rule is in force on a given PFTL network
  depends on whether `fixAmendmentMajorityCalc` is enabled there; the
  pack cannot determine that from source alone. Run the detector with
  the rule that matches observed `EnableAmendment` outcomes.
- [ANALISIS] The NIST PQC standards (FIPS 203/204/205) are not
  applicable to vote telemetry: validations on XRPL-derived networks
  are Ed25519-signed, and quantum exposure of validation signatures is
  a separate assessment from vote-anomaly detection. No PQC claim is
  made in this pack.

## 8. Primary sources

| # | Source | What was taken from it | Accessed |
|---|---|---|---|
| P1 | https://xrpl.org/docs/concepts/networks-and-servers/amendments | >80% for two weeks; flag-ledger process; `EnableAmendment` flags; vetoed amendments; enabling is one-way | 2026-11-17 |
| P2 | https://xrpl.org/docs/concepts/consensus-protocol/negative-unl/ | 80% consensus quorum; reliability = Va/256; <50% add / >80% remove; one change per flag ledger; 60% quorum floor; 25% Negative UNL cap | 2026-11-17 |
| P3 | postfiatd `include/xrpl/protocol/SystemParameters.h`, commit `0085a1ff` | Pre-fix threshold 204/256 (lines 148); post-fix threshold 67/100 (line 151); default majority time 2 weeks (lines 154–156) | 2026-11-17 (live) |
| P4 | postfiatd `src/xrpld/app/misc/detail/AmendmentTable.cpp`, commit `0085a1ff` | Threshold computation (`computeThreshold`, lines 615–647); strict `>` post-fix, `>=` pre-fix, one-validator exception (`passes`, lines 679–712); vote-count log line (line 1612) | 2026-11-17 (live) |
| P5 | postfiatd `include/xrpl/protocol/detail/features.macro:201`, commit `0085a1ff` | `fixAmendmentMajorityCalc` supported, default-yes voting | 2026-11-17 (live) |
| P6 | postfiatd `src/xrpld/core/Config.h` / `Config.cpp` | `amendment_majority_time` per-node configurability and minimum value — NOT verified from source for this pack; only the two-week default is verified (P3) | not verified |
| P7 | https://raw.githubusercontent.com/XRPLF/rippled/2.3.0/include/xrpl/protocol/SystemParameters.h | Upstream post-fix threshold 80/100 (contrast with P3) | 2026-11-17 |
| N1 | NIST SP 800-94, Guide to Intrusion Detection and Prevention Systems (IDPS), February 2007 | Signature-based vs anomaly-based detection; a threshold is "a value that sets the limit between normal and abnormal behavior"; tuning and false-positive management | 2026-11-17 |
| N2 | NIST SP 800-137, Information Security Continuous Monitoring (ISCM), September 2011 | ISCM definition ("maintaining ongoing awareness of information security, vulnerabilities, and threats"); six-step process; "continuous" means a frequency sufficient to support risk-based decisions; data collected at discrete intervals (here: flag ledgers) | 2026-11-17 |

## 9. Reproduction

```
python3 run_drill.py
```

Runs every scenario over 5 seeds, prints the threshold arithmetic, the
detection table, and the determinism proof, and exits 0 only if all
checks pass. See `README.md` for the fresh-clone rerun command and
results, and `claim-to-evidence-index.md` for the claim-by-claim
mapping to sources and logs.
