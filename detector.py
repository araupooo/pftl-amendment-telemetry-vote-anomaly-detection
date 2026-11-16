"""Amendment vote-anomaly detector (reference implementation).

Consumes the flag-ledger vote streams produced by ``simulator.py`` and
emits alerts. Pure Python standard library, deterministic: the same stream
always produces the same alerts.

Thresholds are *proposed* values for a PFTL-style network, derived from the
primary sources listed in framework.md. They are not PFTL-official. The
detector is parameterised by the majority rule in force, because postfiatd
has two: the pre-fix rule (204/256, ``>=``) and the post-fix rule (67/100,
strict ``>``) once the ``fixAmendmentMajorityCalc`` amendment is enabled.
Upstream XRPL uses 80/100 post-fix. The detector defaults to the PFTL
post-fix rule and reports which rule it applied.

Rules
-----
R1 SUPPORT-DRIFT: the 10-flag-ledger mean support falls by >= 5 pp
    against the 10-flag-ledger mean 10 ledgers earlier (WARNING), or
    >= 9 pp (CRITICAL). Detects quorum drift before any threshold crossing.
R2 MAJORITY-LOST: the amendment is not passing under the majority rule
    for 2 consecutive flag ledgers after previously passing (CRITICAL).
    Passing means yes-votes > threshold, where
    threshold = max(1, floor(trusted * ratio)).
R3 THIN-MAJORITY: the 10-flag-ledger mean support is within 3 pp above
    the majority threshold (WARNING). A majority this thin can be lost by
    a handful of flips. Uses the rolling mean, not the instantaneous
    support, because per-ledger noise makes a fixed threshold flicker.
R4 DISAGREEMENT: a validator's agreement with the ledger majority over
    the trailing 16 flag ledgers falls below 50% while network support is
    healthy (>= 80%) (WARNING); below 50% for 3 consecutive flag ledgers
    (CRITICAL). Mirrors the Negative UNL reliability bands (<50% add
    candidate, >80% remove). The health gate matters: when support itself
    is drifting, low agreement is the expected behaviour of the whole
    network, not a single-validator fault, so R4 is suppressed while R1
    conditions hold.
R5 TIMING: 3 or more validators' votes arrive with lag > 2 flag ledgers
    in the same flag ledger (WARNING); 6 or more (CRITICAL). Fires once
    when the condition starts and again only if it clears and re-enters.
R6 DUPLICATE-STALE: any duplicate or stale validation message
    (WARNING per flag ledger, listing the count); more than 5% of the
    flag ledger's messages are duplicates/stale (CRITICAL). Fires per
    flag ledger because each ledger's bad messages are distinct evidence.
R7 CHURN: the online validator set changes by >10% within 5 flag ledgers
    (WARNING); >20% (CRITICAL). Measured as the symmetric difference of
    the online sets, so validators going offline and new validators
    joining both count. Fires once per churn episode.
R8 THIN-QUORUM: online validators fall below 80% of the configured UNL
    (CRITICAL). Below that, the consensus quorum itself is at risk.
    Fires once when the floor is first breached.

Alert-fatigue control: rules that describe a persistent state (R1, R3,
R5, R7, R8) are edge-triggered — they fire when the condition starts,
and again only if the condition clears and re-enters (or, for R1/R5,
if severity escalates while active). A condition that stays true for
80 flag ledgers produces one alert, not eighty. R6 stays per-ledger and
R4 stays per-validator-episode, because those are discrete events.

An alert is a dict: {"t", "rule", "severity", "detail"}.
"""

import math

# Majority rules: (numerator, denominator, strict) — strict means the
# amendment passes only when yes-votes are STRICTLY greater than the
# computed threshold; non-strict means >= threshold.
MAJORITY_RULES = {
    "pftl-post-fix": (67, 100, True),
    "pftl-pre-fix": (204, 256, False),
    "xrpl-post-fix": (80, 100, True),
}

# Tunable detector parameters (see framework.md section 5 for the
# rationale and the measured tradeoff of each value).
PARAMS = {
    "drift_window": 10,        # flag ledgers per rolling mean
    "drift_warn_pp": 6.0,      # pp fall over the window -> WARNING
    "drift_crit_pp": 9.0,      # pp fall over the window -> CRITICAL
    "thin_majority_pp": 3.0,   # support within this many pp above threshold
    "disagree_window": 16,     # trailing flag ledgers for agreement rate
    "disagree_warn": 0.50,     # agreement below this -> WARNING
    "disagree_rearm": 0.80,    # agreement must recover to this to re-arm
    "disagree_crit_ledgers": 3,
    "timing_lag": 2,           # lag above this counts as late
    "timing_warn_count": 3,
    "timing_crit_count": 6,
    "replay_crit_rate": 0.05,  # duplicate/stale share of messages
    "churn_window": 5,
    "churn_warn_pct": 0.10,
    "churn_crit_pct": 0.20,
    "quorum_floor": 0.80,      # online / UNL below this -> CRITICAL
    "majority_lost_ledgers": 2,
}


def majority_threshold(trusted, rule="pftl-post-fix"):
    """Votes needed for a majority under the named rule.

    Returns (threshold, passes_fn). ``threshold`` is the computed floor;
    the amendment passes when yes-votes are > threshold (strict rules)
    or >= threshold (pre-fix rule).
    """
    num, den, strict = MAJORITY_RULES[rule]
    threshold = max(1, (trusted * num) // den)
    return threshold, strict


def _support(rec):
    online = len(rec["online"])
    if online == 0:
        return 0.0, 0
    yes = sum(1 for v in rec["votes"].values() if v["yes"])
    return yes / float(online), yes


def detect(records, rule="pftl-post-fix", params=None):
    """Run all rules over a stream. Returns (alerts, ledger_stats).

    ``ledger_stats`` is a list of per-flag-ledger dicts with the support
    series, threshold, passing flag, online share and message counts, so
    the drill can recompute anything it needs without re-running rules.
    """
    p = dict(PARAMS)
    if params:
        p.update(params)
    alerts = []
    stats = []
    seen = set()            # (validator, seq) already observed
    last_seq = {}           # validator -> highest seq seen
    agree_hist = {}         # validator -> list of 1/0 per ledger present
    low_agree_run = {}      # validator -> consecutive ledgers < threshold
    r4_episode = set()      # validators (and "CRIT:"+vid) in an open R4 episode
    passing_run = 0
    ever_passing = False
    not_passing_run = 0
    passing_streak = 0          # consecutive passing ledgers
    r2_active = False           # a majority-loss episode is open
    support_hist = []       # support fraction per ledger
    unl_hist = []           # (t, unl_size)
    online_hist = []        # (t, frozenset(online))
    # Edge-trigger state for persistent-state rules: rule -> active severity
    # (None = inactive). An alert fires on entry, or on severity escalation.
    active = {"R1": None, "R3": None, "R5": None, "R7": None, "R8": None}

    def edge(rule, severity, detail, t):
        """Fire an alert if the rule just became active or escalated."""
        order = {"WARNING": 1, "CRITICAL": 2}
        prev = active[rule]
        if prev is None or order[severity] > order[prev]:
            alerts.append({"t": t, "rule": rule, "severity": severity,
                           "detail": detail})
            active[rule] = severity
            return True
        return False

    def clear(rule):
        active[rule] = None

    for rec in records:
        t = rec["t"]
        support, yes = _support(rec)
        support_hist.append(support)
        unl_hist.append((t, rec["unl_size"]))
        online_hist.append((t, frozenset(rec["online"])))
        trusted = len(rec["online"])
        threshold, strict = majority_threshold(trusted, rule)
        threshold_pct = (threshold + (1 if strict else 0)) / float(trusted)
        passing = (yes > threshold) if strict else (yes >= threshold)

        # --- R2 majority lost (edge-triggered) ---
        # Fires once per majority-loss episode. Re-arms only after the
        # amendment passes for 5 consecutive flag ledgers, so support
        # flickering across the threshold does not produce one alert per
        # crossing.
        if passing:
            ever_passing = True
            not_passing_run = 0
            passing_streak += 1
            if passing_streak >= 5:
                r2_active = False
        else:
            not_passing_run += 1
            passing_streak = 0
        if (not_passing_run == p["majority_lost_ledgers"] and ever_passing
                and not r2_active):
            r2_active = True
            alerts.append({"t": t, "rule": "R2", "severity": "CRITICAL",
                           "detail": "majority lost for %d consecutive "
                           "flag ledgers; yes=%d threshold=%d (rule %s)"
                           % (not_passing_run, yes, threshold, rule)})

        # --- R3 thin majority (edge-triggered, with hysteresis) ---
        # Uses the 10-flag-ledger mean support, not the instantaneous
        # value: per-ledger support noise (about +/-7 pp at n=53) makes a
        # fixed threshold flicker when support hovers near it. The mean
        # has about +/-2 pp of noise, so the band is crossed once.
        # Fires on entering the thin band; re-arms only once the mean is
        # clearly out of the band (>5 pp above the threshold, or >2 pp
        # below it).
        smooth = (sum(support_hist[-p["drift_window"]:])
                  / float(min(len(support_hist), p["drift_window"])))
        band_pp = (smooth - threshold_pct) * 100.0
        smooth_passing = smooth * trusted > threshold + (1 if strict else 0)
        if smooth_passing and band_pp <= p["thin_majority_pp"]:
            edge("R3", "WARNING",
                 "thin majority: 10-ledger mean support %.1f%%, "
                 "threshold %.1f%% (rule %s)"
                 % (smooth * 100.0, threshold_pct * 100.0, rule), t)
        elif band_pp > p["thin_majority_pp"] + 2.0 or band_pp < -2.0:
            clear("R3")

        # --- R1 support drift (10-ledger rolling means, edge-triggered) ---
        w = p["drift_window"]
        if len(support_hist) >= 2 * w:
            now_mean = sum(support_hist[-w:]) / w
            prev_mean = sum(support_hist[-2 * w:-w]) / w
            fall_pp = (prev_mean - now_mean) * 100.0
            if fall_pp >= p["drift_crit_pp"]:
                edge("R1", "CRITICAL",
                     "support fell %.1f pp over %d flag ledgers "
                     "(%.1f%% -> %.1f%%)"
                     % (fall_pp, w, prev_mean * 100.0, now_mean * 100.0), t)
            elif fall_pp >= p["drift_warn_pp"]:
                edge("R1", "WARNING",
                     "support fell %.1f pp over %d flag ledgers "
                     "(%.1f%% -> %.1f%%)"
                     % (fall_pp, w, prev_mean * 100.0, now_mean * 100.0), t)
            else:
                clear("R1")
        else:
            clear("R1")

        # --- per-validator agreement (R4), gated on network health ---
        # Hysteresis mirrors the Negative UNL bands: an episode opens
        # below 50% agreement and re-arms only at 80% recovery, so a
        # persistently unreliable validator produces one WARNING and one
        # CRITICAL per episode instead of one per crossing.
        majority_yes = support >= 0.5
        healthy = support >= 0.80
        for vid, vote in rec["votes"].items():
            agree = 1 if vote["yes"] == majority_yes else 0
            hist = agree_hist.setdefault(vid, [])
            hist.append(agree)
            hist = hist[-p["disagree_window"]:]
            agree_hist[vid] = hist
            if len(hist) < p["disagree_window"] or not healthy:
                continue
            rate = sum(hist) / float(len(hist))
            if rate >= p["disagree_rearm"]:
                low_agree_run[vid] = 0
                r4_episode.discard(vid)
            elif rate < p["disagree_warn"]:
                low_agree_run[vid] = low_agree_run.get(vid, 0) + 1
                if vid not in r4_episode:
                    r4_episode.add(vid)
                    alerts.append({"t": t, "rule": "R4",
                                   "severity": "WARNING",
                                   "detail": "validator %s agreement "
                                   "%.0f%% over trailing %d flag "
                                   "ledgers (<50%% Negative UNL band)"
                                   % (vid, rate * 100.0,
                                      p["disagree_window"])})
                elif low_agree_run[vid] == p["disagree_crit_ledgers"] \
                        and ("CRIT:" + vid) not in r4_episode:
                    r4_episode.add("CRIT:" + vid)
                    alerts.append({"t": t, "rule": "R4",
                                   "severity": "CRITICAL",
                                   "detail": "validator %s agreement "
                                   "below 50%% for %d consecutive "
                                   "flag ledgers"
                                   % (vid, p["disagree_crit_ledgers"])})
            else:
                low_agree_run[vid] = 0

        # --- R5 timing: late arrivals (edge-triggered) ---
        late = [vid for vid, v in rec["votes"].items()
                if v["lag"] > p["timing_lag"]]
        if len(late) >= p["timing_crit_count"]:
            edge("R5", "CRITICAL",
                 "%d validators' votes arrived >%d flag ledgers late: %s"
                 % (len(late), p["timing_lag"], ",".join(sorted(late))), t)
        elif len(late) >= p["timing_warn_count"]:
            edge("R5", "WARNING",
                 "%d validators' votes arrived >%d flag ledgers late: %s"
                 % (len(late), p["timing_lag"], ",".join(sorted(late))), t)
        else:
            clear("R5")

        # --- R6 duplicates / stale messages ---
        dups = 0
        stales = 0
        for m in rec["messages"]:
            key = (m["validator"], m["seq"])
            if m["kind"] == "duplicate":
                dups += 1
            elif m["kind"] == "stale":
                stales += 1
            if key in seen and m["kind"] == "validation":
                dups += 1
            seen.add(key)
            if m["validator"] in last_seq and m["seq"] < last_seq[m["validator"]]:
                if m["kind"] == "validation":
                    stales += 1
            last_seq[m["validator"]] = max(last_seq.get(m["validator"], -1),
                                           m["seq"])
        bad = dups + stales
        if bad:
            rate = bad / float(max(1, len(rec["messages"])))
            sev = "CRITICAL" if rate > p["replay_crit_rate"] else "WARNING"
            alerts.append({"t": t, "rule": "R6", "severity": sev,
                           "detail": "%d duplicate/stale validations "
                           "(%d duplicate, %d stale) in %d messages "
                           "(%.1f%%)" % (bad, dups, stales,
                                         len(rec["messages"]),
                                         rate * 100.0)})

        # --- R7 churn: online-set change over the window (edge-triggered) ---
        if len(online_hist) > p["churn_window"]:
            old_online = online_hist[-p["churn_window"] - 1][1]
            new_online = online_hist[-1][1]
            change = len(old_online ^ new_online) / float(
                max(1, len(old_online)))
            if change >= p["churn_crit_pct"]:
                edge("R7", "CRITICAL",
                     "online validator set changed %.1f%% in %d flag "
                     "ledgers (%d validators joined/left)"
                     % (change * 100.0, p["churn_window"],
                        len(old_online ^ new_online)), t)
            elif change >= p["churn_warn_pct"]:
                edge("R7", "WARNING",
                     "online validator set changed %.1f%% in %d flag "
                     "ledgers (%d validators joined/left)"
                     % (change * 100.0, p["churn_window"],
                        len(old_online ^ new_online)), t)
            else:
                clear("R7")
        else:
            clear("R7")

        # --- R8 thin quorum (edge-triggered) ---
        online_share = len(rec["online"]) / float(max(1, rec["unl_size"]))
        if online_share < p["quorum_floor"]:
            edge("R8", "CRITICAL",
                 "only %d of %d UNL validators online (%.1f%% < 80%% "
                 "quorum floor)"
                 % (len(rec["online"]), rec["unl_size"],
                    online_share * 100.0), t)
        else:
            clear("R8")

        stats.append({"t": t, "support": round(support, 4),
                      "yes": yes, "online": trusted,
                      "unl_size": rec["unl_size"],
                      "threshold": threshold, "passing": passing,
                      "messages": len(rec["messages"]),
                      "late": len(late), "bad_messages": bad})
    return alerts, stats


if __name__ == "__main__":
    import sys
    import simulator
    scenario = sys.argv[1] if len(sys.argv) > 1 else "normal"
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1001
    recs = simulator.generate(scenario, seed)
    alerts, stats = detect(recs)
    print("scenario=%s seed=%d alerts=%d" % (scenario, seed, len(alerts)))
    for a in alerts[:20]:
        print("t=%d %s %s: %s" % (a["t"], a["rule"], a["severity"], a["detail"]))
