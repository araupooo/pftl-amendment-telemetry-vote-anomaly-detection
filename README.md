# PFTL Amendment Telemetry and Vote-Anomaly Detection Evidence Pack

How PFTL operators can monitor amendment activation and detect anomalous
validator voting — vote-timing anomalies, quorum drift, validator churn,
and replayed or out-of-order validations — before an amendment activates
wrongly. Framework, runnable simulator and detector, measured detection
results, and a claim-to-evidence index, as one integrated assessment.

## What is in this pack

| File | What it is |
|---|---|
| [framework.md](framework.md) | Telemetry framework: vote signals, detection rules R1–R8 with thresholds, alerting/escalation/rollback procedure, threshold tradeoffs, limitations, primary sources |
| [simulator.py](simulator.py) | Deterministic synthetic amendment vote-stream simulator (normal + 4 anomaly scenarios, pure stdlib, explicit seeds) |
| [detector.py](detector.py) | Reference anomaly detector implementing rules R1–R8 (parameterised by majority rule: `pftl-post-fix`, `pftl-pre-fix`, `xrpl-post-fix`) |
| [scenarios.json](scenarios.json) | Scenario configurations, seeds, and metric definitions used by the drill |
| [run_drill.py](run_drill.py) | One-command drill: runs all scenarios over 5 seeds, prints the detection table and the determinism proof |
| [detection-table.md](detection-table.md) | Measured detection table (TPR, latency, alert volume, false-positive rate) — every number copied from the drill log |
| [claim-to-evidence-index.md](claim-to-evidence-index.md) | Every substantive claim mapped to its primary source or its unedited log |
| [logs/drill-run-1.log](logs/drill-run-1.log) … [logs/drill-run-5.log](logs/drill-run-5.log) | Unedited stdout of five separate `python3 run_drill.py` invocations (byte-identical) |
| [logs/fresh-clone-rerun.log](logs/fresh-clone-rerun.log) | Unedited stdout of the drill run from a fresh copy of this pack (see below) |
| [logs/normal-seed-1003-alerts.log](logs/normal-seed-1003-alerts.log) | Per-seed normal-traffic alert record: the two WARNING+ false-positive alerts (seed 1003) quoted verbatim, with the other four seeds at 0 alerts — the evidence behind the 0.333/100-ledgers false-positive rate |
| [SHA256SUMS](SHA256SUMS) | SHA-256 of every file in this pack |

## Key finding

postfiatd diverges from upstream XRPL on the amendment majority
threshold: once the `fixAmendmentMajorityCalc` amendment is enabled, a
PFTL amendment needs only a **67%** majority
(`postFixAmendmentMajorityCalcThreshold = 67/100`, strictly greater),
not XRPL's 80%. At 53 validators that is 36 yes-votes instead of 43.
The detector is parameterised by majority rule for exactly this
reason — see framework.md section 2 for the source-level evidence.

## Headline results

From `python3 run_drill.py` (5 seeds per scenario, 53 validators, 120
flag ledgers, injection at flag ledger 40):

| Scenario | TPR | Latency, flag ledgers (min/med/max) | Mean alerts/run |
|---|---|---|---|
| timing-skew | 1.00 | 3 / 3 / 3 | 1.80 |
| quorum-drift | 1.00 | 0 / 9 / 12 | 7.60 |
| churn | 1.00 | 0 / 0 / 0 | 10.00 |
| replay | 1.00 | 0 / 0 / 0 | 20.40 |
| normal (false positives) | — | — | 0.40 warnings/run; 0.333 WARNING+ per 100 flag ledgers |

Canonical results SHA-256:
`9478658cd6bffa6bd696b6bda2751e8453cae0d3e60fe20361605d40e4deb731`.
Full numbers, per-rule totals, and the reading of each result are in
[detection-table.md](detection-table.md).

## Reproduce it (one command)

```sh
python3 run_drill.py
```

Requires Python 3.8+ and nothing else (standard library only, no
network access). Exit code 0 means every check passed. The output
contains no timestamps and no absolute paths, so repeated invocations
are byte-identical.

## Fresh-clone rerun

The documented commands were validated from a fresh copy of this pack
(a plain directory copy to a fresh location, no prior state):

```sh
cp -r pack fresh-copy
cd fresh-copy
python3 run_drill.py
```

Result (unedited log: [logs/fresh-clone-rerun.log](logs/fresh-clone-rerun.log)):

```text
--- determinism ---
same-seed streams byte-identical: True
same-seed alerts identical: True
all 5 seeded runs completed: True
canonical results sha256: 9478658cd6bffa6bd696b6bda2751e8453cae0d3e60fe20361605d40e4deb731
RUN_DRILL: ALL GREEN
```

Exit code 0. The fresh-clone log is byte-identical to
`logs/drill-run-1.log` (same SHA-256:
`16a35fb486ae297c0e2fa1e66271b17eb6045b2ac82787cd3f6f6a7eceef2cba`).

## Verify the pack

```sh
sha256sum -c SHA256SUMS
```

## Limitations (short version)

All detection numbers come from synthetic vote streams, not
live-network data; the simulation window is 120 flag ledgers while the
real majority clock is two weeks; the 53-validator scale is the
reported testnet size and was not re-verified live; which majority
rule is in force depends on whether `fixAmendmentMajorityCalc` is
enabled on the network. See framework.md section 7 for the full list.
