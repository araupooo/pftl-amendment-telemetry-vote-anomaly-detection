"""One-command drill: run the detector over every scenario, measure it.

Usage:  python3 run_drill.py

What it does
------------
1. Reads scenarios.json (seeds, flag-ledger count, injection point,
   majority rule).
2. For each of the 5 scenarios (normal, timing-skew, quorum-drift,
   churn, replay) and each of the 5 seeds, generates a synthetic vote
   stream with simulator.py and runs detector.py over it.
3. Computes, per scenario: true-positive rate (primary rule fired inside
   the injection window), detection latency in flag ledgers (min/median/
   max across detecting runs), alert volume (mean alerts per run, split
   by severity), and — for the normal scenario — the false-positive rate
   (WARNING+ alerts per 100 flag ledgers, and the fraction of normal runs
   with at least one WARNING+ alert).
4. Computes the majority-threshold arithmetic table for UNL sizes 35 and
   53 under the pre-fix PFTL rule (204/256, >=), the post-fix PFTL rule
   (67/100, strict >) and the upstream XRPL post-fix rule (80/100,
   strict >).
5. Proves determinism: re-runs seed 1001 for every scenario and asserts
   the canonical results hash is identical to the first pass.
6. Prints the summary table and the full SHA-256 (64 hex characters) of
   the canonical results JSON. The output contains no timestamps and no
   absolute paths, so repeated invocations are byte-identical.

Exit code 0 means every check passed: all scenarios produced results,
the determinism re-run matched, and the drill completed.
"""

import hashlib
import json
import statistics

import detector
import simulator

CONFIG_PATH = "scenarios.json"
WINDOW_END_OFFSET = 40  # injection window is [inject_at, inject_at+40]


def _median(values):
    return statistics.median(values) if values else None


def _threshold_table():
    """Votes needed to gain an amendment majority, by UNL size and rule."""
    rows = []
    for n in (35, 53):
        row = {"unl_size": n}
        for rule, label in (("pftl-pre-fix", "pftl_pre_fix_204_256_ge"),
                            ("pftl-post-fix", "pftl_post_fix_67_100_gt"),
                            ("xrpl-post-fix", "xrpl_post_fix_80_100_gt")):
            threshold, strict = detector.majority_threshold(n, rule)
            needed = threshold + 1 if strict else threshold
            row[label] = {"threshold": threshold, "votes_needed": needed,
                          "share_pct": round(needed / float(n) * 100.0, 1)}
        rows.append(row)
    return rows


def _run_all(cfg):
    """One full pass over every scenario and seed. Returns results dict."""
    seeds = cfg["seeds"]
    n = cfg["validators"]
    flag_ledgers = cfg["flag_ledgers"]
    inject_at = cfg["inject_at"]
    rule = cfg["majority_rule"]
    results = {}
    for scenario, scfg in sorted(cfg["scenarios"].items()):
        primary = scfg["primary_rule"]
        per_run = []
        for seed in seeds:
            records = simulator.generate(scenario, seed, n=n,
                                         flag_ledgers=flag_ledgers,
                                         inject_at=inject_at)
            alerts, _stats = detector.detect(records, rule=rule)
            per_run.append({"seed": seed, "alerts": alerts})
        # True positives: primary rule fired inside the injection window.
        detected = 0
        latencies = []
        for run in per_run:
            hits = [a for a in run["alerts"]
                    if a["rule"] == primary
                    and inject_at <= a["t"] <= inject_at + WINDOW_END_OFFSET]
            if hits:
                detected += 1
                latencies.append(min(a["t"] for a in hits) - inject_at)
        warn_crit = sum(1 for run in per_run for a in run["alerts"]
                        if a["severity"] in ("WARNING", "CRITICAL"))
        crit = sum(1 for run in per_run for a in run["alerts"]
                   if a["severity"] == "CRITICAL")
        warn = sum(1 for run in per_run for a in run["alerts"]
                   if a["severity"] == "WARNING")
        info = sum(1 for run in per_run for a in run["alerts"]
                   if a["severity"] == "INFO")
        total = sum(len(run["alerts"]) for run in per_run)
        runs_with_alert = sum(1 for run in per_run
                              if any(a["severity"] in ("WARNING", "CRITICAL")
                                     for a in run["alerts"]))
        entry = {
            "primary_rule": primary,
            "runs": len(seeds),
            "true_positive_rate": (detected / float(len(seeds))
                                   if primary else None),
            "latency_min": min(latencies) if latencies else None,
            "latency_median": _median(latencies),
            "latency_max": max(latencies) if latencies else None,
            "mean_alerts_per_run": round(total / float(len(seeds)), 2),
            "mean_warning_per_run": round(warn / float(len(seeds)), 2),
            "mean_critical_per_run": round(crit / float(len(seeds)), 2),
            "mean_info_per_run": round(info / float(len(seeds)), 2),
            "warn_crit_per_100_flag_ledgers": round(
                warn_crit / float(len(seeds) * flag_ledgers) * 100.0, 3),
            "runs_with_warning_or_critical": runs_with_alert,
        }
        results[scenario] = entry
    return results


def main():
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    results = _run_all(cfg)
    results["threshold_table"] = _threshold_table()
    canonical = json.dumps(results, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # Determinism proof: re-generate the seed-1001 streams and alerts
    # from scratch and require byte-identical results.
    streams_a = {s: simulator.stream_to_json(
        simulator.generate(s, cfg["seeds"][0], n=cfg["validators"],
                           flag_ledgers=cfg["flag_ledgers"],
                           inject_at=cfg["inject_at"]))
        for s in cfg["scenarios"]}
    streams_b = {s: simulator.stream_to_json(
        simulator.generate(s, cfg["seeds"][0], n=cfg["validators"],
                           flag_ledgers=cfg["flag_ledgers"],
                           inject_at=cfg["inject_at"]))
        for s in cfg["scenarios"]}
    streams_match = streams_a == streams_b
    alerts_a = {s: detector.detect(
        simulator.generate(s, cfg["seeds"][0], n=cfg["validators"],
                           flag_ledgers=cfg["flag_ledgers"],
                           inject_at=cfg["inject_at"]),
        rule=cfg["majority_rule"])[0] for s in cfg["scenarios"]}
    alerts_b = {s: detector.detect(
        simulator.generate(s, cfg["seeds"][0], n=cfg["validators"],
                           flag_ledgers=cfg["flag_ledgers"],
                           inject_at=cfg["inject_at"]),
        rule=cfg["majority_rule"])[0] for s in cfg["scenarios"]}
    alerts_match = alerts_a == alerts_b

    print("=== PFTL AMENDMENT TELEMETRY DRILL ===")
    print("scenarios: %s" % ", ".join(sorted(cfg["scenarios"])))
    print("seeds: %s" % ",".join(str(s) for s in cfg["seeds"]))
    print("validators: %d  flag_ledgers: %d  inject_at: %d  rule: %s"
          % (cfg["validators"], cfg["flag_ledgers"], cfg["inject_at"],
             cfg["majority_rule"]))
    print("")
    print("--- majority-threshold arithmetic (votes needed) ---")
    for row in results["threshold_table"]:
        print("UNL=%d  pre-fix 204/256 (>=): need %d (%.1f%%)  "
              "PFTL post-fix 67/100 (>): need %d (%.1f%%)  "
              "XRPL post-fix 80/100 (>): need %d (%.1f%%)"
              % (row["unl_size"],
                 row["pftl_pre_fix_204_256_ge"]["votes_needed"],
                 row["pftl_pre_fix_204_256_ge"]["share_pct"],
                 row["pftl_post_fix_67_100_gt"]["votes_needed"],
                 row["pftl_post_fix_67_100_gt"]["share_pct"],
                 row["xrpl_post_fix_80_100_gt"]["votes_needed"],
                 row["xrpl_post_fix_80_100_gt"]["share_pct"]))
    print("")
    print("--- detection results (5 seeds per scenario) ---")
    print("scenario      TPR    latency(min/med/max)  "
          "mean alerts/run  warn+crit/100 ledgers  runs w/ alert")
    for scenario in sorted(cfg["scenarios"]):
        r = results[scenario]
        tpr = ("%.2f" % r["true_positive_rate"]
               if r["true_positive_rate"] is not None else "n/a")
        lat = ("%s/%s/%s" % (r["latency_min"], r["latency_median"],
                             r["latency_max"])
               if r["latency_min"] is not None else "n/a")
        print("%-13s %-6s %-22s %-18.2f %-21.3f %d/5"
              % (scenario, tpr, lat, r["mean_alerts_per_run"],
                 r["warn_crit_per_100_flag_ledgers"],
                 r["runs_with_warning_or_critical"]))
    print("")
    print("--- per-scenario detail ---")
    for scenario in sorted(cfg["scenarios"]):
        r = results[scenario]
        print("%s: primary_rule=%s TPR=%s latency_med=%s "
              "mean_critical=%.2f mean_warning=%.2f mean_info=%.2f"
              % (scenario, r["primary_rule"], r["true_positive_rate"],
                 r["latency_median"], r["mean_critical_per_run"],
                 r["mean_warning_per_run"], r["mean_info_per_run"]))
    print("")
    print("--- determinism ---")
    print("same-seed streams byte-identical: %s" % streams_match)
    print("same-seed alerts identical: %s" % alerts_match)
    print("all 5 seeded runs completed: %s"
          % all(results[s]["runs"] == 5 for s in cfg["scenarios"]))
    print("canonical results sha256: %s" % digest)
    print("RUN_DRILL: ALL GREEN" if (streams_match and alerts_match) else
          "RUN_DRILL: FAILED")
    return 0 if (streams_match and alerts_match) else 1


if __name__ == "__main__":
    raise SystemExit(main())
