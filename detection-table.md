# Measured Detection Table

All numbers below are the unedited output of `python3 run_drill.py`
(canonical results SHA-256
`9478658cd6bffa6bd696b6bda2751e8453cae0d3e60fe20361605d40e4deb731`),
run over 5 scenarios × 5 seeds (1001–1005), 53 validators, 120 flag
ledgers per stream, anomaly injection at flag ledger 40, majority rule
`pftl-post-fix` (67/100, strict). The full drill output is saved in
`logs/drill-run-1.log` (identical across all 5 invocations — see the
determinism note below). No number in this file was hand-typed: every
value is copied from that log.

## 1. Majority-threshold arithmetic (computed by the drill)

Votes needed for an amendment majority, by UNL size and rule.
Threshold = max(1, floor(N × ratio)); strict rules need threshold + 1
votes, the pre-fix rule needs threshold votes.

| UNL size | PFTL pre-fix 204/256 (>=) | PFTL post-fix 67/100 (>) | XRPL post-fix 80/100 (>) |
|---|---|---|---|
| 35 | 27 votes (77.1%) | 24 votes (68.6%) | 29 votes (82.9%) |
| 53 | 42 votes (79.2%) | 36 votes (67.9%) | 43 votes (81.1%) |

## 2. Detection results (5 seeds per scenario)

TPR = fraction of the 5 seeded runs in which the scenario's primary
rule fired at least once inside the injection window [40, 80]. Latency
= flag ledgers from injection (t=40) to the first primary-rule alert,
min / median / max across detecting runs. Alert volume = mean alerts
per run (all rules, all severities). FPR is measured on the normal
scenario only.

| Scenario | Primary rule | TPR | Latency (min/med/max) | Mean alerts/run (critical / warning) | WARNING+ per 100 flag ledgers | Runs with ≥1 WARNING+ |
|---|---|---|---|---|---|---|
| timing-skew | R5 | 1.00 | 3 / 3 / 3 | 1.80 (1.00 / 0.80) | 1.500 | 5/5 |
| quorum-drift | R1 | 1.00 | 0 / 9 / 12 | 7.60 (2.60 / 5.00) | 6.333 | 5/5 |
| churn | R7 | 1.00 | 0 / 0 / 0 | 10.00 (5.80 / 4.20) | 8.333 | 5/5 |
| replay | R6 | 1.00 | 0 / 0 / 0 | 20.40 (20.00 / 0.40) | 17.000 | 5/5 |
| normal | — | n/a | n/a | 0.40 (0.00 / 0.40) | 0.333 | 1/5 |

False-positive rate (normal traffic): **0.333 WARNING+ alerts per 100
flag ledgers** — 2 alerts in 600 flag ledgers (one R1, one R4), in 1
of 5 runs. No CRITICAL alert fired on normal traffic in any run.

## 3. Per-rule alert totals (5 runs combined)

| Scenario | R1 W | R1 C | R2 C | R3 W | R4 W | R4 C | R5 C | R6 C | R7 C | R8 C |
|---|---|---|---|---|---|---|---|---|---|---|
| normal | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| timing-skew | 4 | 0 | 0 | 0 | 0 | 0 | 5 | 0 | 0 | 0 |
| quorum-drift | 11 | 7 | 6 | 7 | 7 | 0 | 0 | 0 | 0 | 0 |
| churn | 1 | 0 | 0 | 0 | 20 | 19 | 0 | 0 | 5 | 5 |
| replay | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 100 | 0 | 0 |

## 4. Reading the numbers

- **Timing skew (latency exactly 3 in all 5 runs):** the 8 skewed
  validators' votes are delayed by exactly 3 flag ledgers, so R5
  fires on their first late arrival. The 4 secondary R1 warnings are
  the apparent support dip while those votes are in flight.
- **Quorum drift (median latency 9):** R1 needs the 10-ledger mean to
  fall 6 pp, which takes about 9 flag ledgers at a drift of ~0.93 pp
  per ledger. The minimum latency of 0 is a noise trigger, not drift
  detection: in seed 1003, R1 fired at t=40 itself, the injection
  ledger, on a random 6 pp fluctuation before the drift had any effect.
  Median 9 is the representative figure.
- **Churn (latency 0):** R7 and R8 both fire on the injection ledger
  itself (12 of 53 validators leaving is a 22.6% online-set change;
  41/53 online is 77.4%, below the 80% quorum floor). The 20 R4
  warnings and 19 R4 criticals are the 4 joining validators, whose
  50% yes-propensity keeps their agreement near the 50% band; each
  produces at most one WARNING and one CRITICAL per episode under the
  80% re-arm rule.
- **Replay (20.00 criticals per run):** R6 fires once per injected
  flag ledger (20 ledgers × 1 alert), by design — each ledger's bad
  messages are distinct evidence. The rate is 100% because every
  injected ledger exceeds the 5% duplicate/stale bound.
- **Quorum drift R2 (6 firings in 5 runs):** R2 fired once per run as
  the majority was lost (t=63–69), plus one re-fire in seed 1001 at
  t=119, where support recovered for 5 consecutive ledgers (re-arming
  R2) and was then lost again. That re-fire is the designed behaviour,
  not a bug.
- **Normal traffic (FPR 0.333/100 ledgers):** the two false alarms are
  one R1 warning (a random 6.0 pp fall in the 10-ledger mean, seed
  1003, t=40: 94.7% -> 88.7%) and one R4 warning (a single validator's
  trailing 16-ledger agreement dipping to 44%, seed 1003, t=15). Both
  are noise, not missed anomalies, and neither reached CRITICAL.

## 5. Determinism

The drill output contains no timestamps and no absolute paths. Five
separate invocations of `python3 run_drill.py` produced byte-identical
stdout (saved as `logs/drill-run-1.log` through `logs/drill-run-5.log`,
all with the same SHA-256), and the drill's internal check re-generates
the seed-1001 streams and alerts and requires them to be identical.
Canonical results SHA-256:
`9478658cd6bffa6bd696b6bda2751e8453cae0d3e60fe20361605d40e4deb731`.
