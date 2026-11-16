# Claim-to-Evidence Index

Every substantive claim in `framework.md` and `detection-table.md`,
mapped to the primary source or the unedited log that supports it.
Labels: [FAKTA] verified fact with source and date, [ESTIMASI] modelled
or reported number, [ANALISIS] interpretation. "Evidence" is either a
source URL (with access date) or a log file and the line to look for.

## Specification-derived claims

| # | Claim | Label | Evidence |
|---|---|---|---|
| C1 | XRPL amendments need >80% support from trusted validators for two weeks to be enabled; dropping below 80% restarts the two-week period | [FAKTA] | P1 — https://xrpl.org/docs/concepts/networks-and-servers/amendments, accessed 2026-11-17: "Amendments must maintain two weeks of support from more than 80% of trusted validators to be enabled. If support drops below 80%, the amendment is temporarily rejected, and the two week period restarts." |
| C2 | Flag ledger = every 256th ledger; votes at flag ledger −1, interpretation at the flag ledger, `EnableAmendment` pseudo-transaction at +1 (`tfGotMajority` / `tfLostMajority` / unflagged = enabled), application at +2; flag ledgers typically ~15 minutes apart | [FAKTA] | P1 — same page, "Amendment Process" section, accessed 2026-11-17 |
| C3 | Only votes from trusted validators count; an unconfigured server uses the default vote from source code; amendments whose code was removed without being enabled are vetoed; enabling is one-way | [FAKTA] | P1 — "Amendment Voting" section, accessed 2026-11-17 |
| C4 | Standard consensus quorum is 80% of trusted validators | [FAKTA] | P2 — https://xrpl.org/docs/concepts/consensus-protocol/negative-unl/, accessed 2026-11-17: "The standard quorum requirement is 80% of trusted validators." |
| C5 | Reliability = percentage of the last 256 ledgers where a validator's vote matched the server's view; below 50% is a Negative UNL add candidate, above 80% a remove candidate | [FAKTA] | P2 — "Reliability Measurement" section, accessed 2026-11-17: "Reliability = Va ÷ 256"; "If a validator's reliability is less than 50%, it is a candidate to be added to the Negative UNL. To be removed from the Negative UNL, a validator's reliability must be greater than 80%." |
| C6 | Negative UNL changes by at most one addition and one removal per flag ledger, via `UNLModify` pseudo-transactions; quorum floor is 60% of total UNL; Negative UNL is "full" at 25% of the configured UNL | [FAKTA] | P2 — "Modifying the Negative UNL" and "Negative UNL Limits" sections, accessed 2026-11-17 |
| C7 | Different servers can reach different conclusions about a validator's reliability | [FAKTA] | P2 — "Each server, including validators, independently calculates reliability scores for all of its trusted validators. Different servers may reach different conclusions about a validator's reliability", accessed 2026-11-17 |
| C8 | postfiatd pre-fix amendment threshold is 204/256; post-fix threshold is 67/100; default majority time is 2 weeks | [FAKTA] | P3 — postfiatd `include/xrpl/protocol/SystemParameters.h`, commit `0085a1ff`, lines 148–156, verified live 2026-11-17 |
| C9 | postfiatd passes an amendment at votes `>= threshold` pre-fix and votes `> threshold` post-fix (one-validator exception); threshold = max(1, floor(trusted × ratio)) | [FAKTA] | P4 — postfiatd `src/xrpld/app/misc/detail/AmendmentTable.cpp`, commit `0085a1ff`, `computeThreshold` lines 615–647 and `passes` lines 679–712, verified live 2026-11-17 |
| C10 | `fixAmendmentMajorityCalc` is registered as supported with default-yes voting in postfiatd | [FAKTA] | P5 — postfiatd `include/xrpl/protocol/detail/features.macro:201`, commit `0085a1ff`, verified live 2026-11-17 |
| C11 | postfiatd default majority-hold time is two weeks | [FAKTA] | P3 — postfiatd `include/xrpl/protocol/SystemParameters.h`, `defaultAmendmentMajorityTime`, commit `0085a1ff`, verified live 2026-11-17. Per-node configurability of the hold time and any minimum value were NOT verified from source for this pack — see the [ANALISIS] caveat in framework.md section 2.2 (source P6) |
| C12 | postfiatd logs the vote count at every voting round (`"Counted votes from " << vote->trustedValidations() ...`) | [FAKTA] | P4 — `AmendmentTable.cpp`, line 1612, commit `0085a1ff`, verified live 2026-11-17 |
| C13 | Upstream rippled 2.3.0 uses 80/100 as the post-fix threshold; current upstream master uses a single 80/100 threshold | [FAKTA] | P7 — https://raw.githubusercontent.com/XRPLF/rippled/2.3.0/include/xrpl/protocol/SystemParameters.h and .../master/.../SystemParameters.h, accessed 2026-11-17 |
| C14 | In IDPS terminology, anomaly-based detection complements signature-based detection, and a threshold is "a value that sets the limit between normal and abnormal behavior"; thresholds and alert settings need periodic review and tuning | [FAKTA] | N1 — NIST SP 800-94 (February 2007), sections 2.3 and 3.2.3, accessed 2026-11-17 |
| C15 | ISCM is "maintaining ongoing awareness of information security, vulnerabilities, and threats to support organizational risk management decisions"; "continuous" means a frequency sufficient to support risk-based decisions; data is collected at discrete intervals | [FAKTA] | N2 — NIST SP 800-137 (September 2011), definition and Chapter 3, accessed 2026-11-17 |
| C16 | NIST PQC standards (FIPS 203/204/205) are not applicable to vote telemetry; validations on XRPL-derived networks are Ed25519-signed | [ANALISIS] | No PQC claim is made anywhere in this pack. The exclusion is stated as an interpretation in framework.md section 7; the Ed25519 basis of XRPL validations is standard XRPL protocol knowledge, not re-derived here. |

## Modelled / reported numbers

| # | Claim | Label | Evidence |
|---|---|---|---|
| M1 | Votes needed for a majority: UNL 35 → pre-fix 27 (77.1%), PFTL post-fix 24 (68.6%), XRPL post-fix 29 (82.9%); UNL 53 → 42 (79.2%), 36 (67.9%), 43 (81.1%) | [ESTIMASI] | Computed by `run_drill.py`; `logs/drill-run-1.log`, lines "--- majority-threshold arithmetic (votes needed) ---" |
| M2 | PFTL testnet has 53 validators (reported, September 2026) | [ESTIMASI] | Reported testnet size; not re-verified live for this pack. The threshold table therefore also shows the 35-validator scale. |
| M3 | The real two-week majority clock spans about 1,200–1,350 flag ledgers (14 days at a 3.5–4 s ledger close time, 256 ledgers per flag ledger) | [ESTIMASI] | Arithmetic: 14 × 86,400 s ÷ 3.5 s ≈ 345,600 ledgers ÷ 256 ≈ 1,350 flag ledgers; at 4 s ≈ 1,181. Ledger close time is the assumed input. |
| M4 | Per-ledger support noise is about ±6.7 pp at 62% support and n=53 (binomial standard deviation), and about ±1.3 pp for the 10-ledger mean at 90% support | [ESTIMASI] | Binomial model: sqrt(p(1−p)/n); sqrt(0.62×0.38/53) ≈ 0.067; sqrt(0.90×0.10/53)/sqrt(10) ≈ 0.013. Stated with the formula in framework.md. |
| M5 | Drift falls about 0.93 pp per flag ledger (28 pp over 30 ledgers) | [ESTIMASI] | Drill configuration: `scenarios.json`, `quorum-drift` (90% → 62% over 30 flag ledgers). |

## Measured claims (from the drill)

| # | Claim | Label | Evidence |
|---|---|---|---|
| D1 | Timing skew: TPR 1.00, latency 3/3/3 flag ledgers, mean 1.80 alerts/run | [FAKTA] | `logs/drill-run-1.log`, "--- detection results ---" and "--- per-scenario detail ---" |
| D2 | Quorum drift: TPR 1.00, latency 0/9/12, mean 7.60 alerts/run | [FAKTA] | Same log; see detection-table.md section 4 for the latency-0 note (seed 1003 noise trigger at t=40) |
| D3 | Churn: TPR 1.00, latency 0/0/0, mean 10.00 alerts/run | [FAKTA] | Same log |
| D4 | Replay: TPR 1.00, latency 0/0/0, mean 20.40 alerts/run | [FAKTA] | Same log |
| D5 | Normal traffic false-positive rate: 0.333 WARNING+ alerts per 100 flag ledgers; 1 of 5 runs with an alert; 0 CRITICAL on normal traffic | [FAKTA] | `logs/drill-run-1.log`, "--- detection results ---" (normal row: 0.40 mean alerts/run, 0.333/100 ledgers, 1/5 runs); the two alerts themselves, quoted verbatim, are in `logs/normal-seed-1003-alerts.log` (seed 1003: t=15 R4 WARNING val-38 44%, t=40 R1 WARNING 6.0 pp fall; seeds 1001/1002/1004/1005: 0 alerts) |
| D6 | Per-rule totals over 5 runs (e.g. replay R6 CRITICAL ×100; churn R4 WARNING ×20, CRITICAL ×19; drift R2 CRITICAL ×6) | [FAKTA] | Same log, cross-checked by re-running the detector per scenario/seed (see detection-table.md section 3) |
| D7 | Drill is deterministic: 5 separate invocations byte-identical; same-seed streams and alerts identical; canonical results SHA-256 `9478658cd6bffa6bd696b6bda2751e8453cae0d3e60fe20361605d40e4deb731` | [FAKTA] | `logs/drill-run-1.log` through `logs/drill-run-5.log` (identical SHA-256 — see SHA256SUMS); `logs/fresh-clone-rerun.log` (independent fresh-clone run, same result) |

## Interpretations

| # | Claim | Label | Evidence |
|---|---|---|---|
| A1 | The two-week rule is the network's only defence against a transient or manipulated majority, so telemetry must see support falling before the clock runs out | [ANALISIS] | Follows from C1 + C2; no separate source. |
| A2 | At 53 validators, the PFTL post-fix rule lets an amendment through with 7 fewer yes-votes than XRPL (36 vs 43); a 70% support level is a comfortable majority on PFTL and a lost majority on XRPL | [ANALISIS] | Arithmetic consequence of C8/C9/C13 and M1. |
| A3 | Which majority rule is in force on a PFTL network cannot be determined from source alone; operators must confirm it from observed `EnableAmendment` outcomes | [ANALISIS] | Follows from C10/C11: the fix amendment must itself gain a majority to activate, and the source does not record whether it has. |
| A4 | R1 at 6 pp (not 5 pp), R3 on the rolling mean, and the R4 health gate are the right tradeoffs | [ANALISIS] | Tuning history recorded in framework.md section 6; the measured outcomes are D1–D7. The 5 pp tuning run is described from the earlier drill output, not from a committed log. |
| A5 | Alerting/escalation/rollback procedure (framework.md section 5) | [ANALISIS] | Proposed procedure; grounded in C1–C7 where cited inline, otherwise a recommendation. |
| A6 | Limitations in framework.md section 7 (synthetic data, compressed window, unre-verified 53-validator scale, PQC out of scope) | [ANALISIS] | Stated limitations of this pack's own method. |
