"""Deterministic synthetic amendment vote-stream simulator.

Generates flag-ledger-granularity amendment vote streams for a PFTL-style
validator set, for use by the detector in ``detector.py`` and the drill in
``run_drill.py``. Pure Python standard library, no network access. All
randomness comes from an explicit integer seed, so the same seed always
produces the same stream.

Model
-----
* One record per flag ledger (every 256th ledger). The simulation window is
  120 flag ledgers by default.
* ``N`` validators (default 53, the reported size of the PFTL testnet
  validator set as of September 2026; see framework.md). Each validator has
  a fixed yes-propensity drawn from a seeded RNG; the baseline amendment
  support is about 90%.
* A vote is a validation message carrying the validator's amendment vote for
  that flag ledger. Normally it arrives in the same flag ledger (lag 0).
* Four anomaly scenarios inject, from flag ledger ``inject_at`` onward:
  - ``timing-skew``: 8 validators' votes are delayed by 3 flag ledgers.
  - ``quorum-drift``: amendment support drifts linearly from ~90% down to
    ~62% over 30 flag ledgers, crossing both the XRPL 80% and the PFTL 67%
    post-fix majority thresholds.
  - ``churn``: 12 validators go offline at ``inject_at``; 4 new validators
    with a 50% yes-propensity join 10 flag ledgers later.
  - ``replay``: 15% of validation messages are duplicated and 5% are stale
    (sequence number two flag ledgers old) for 20 flag ledgers.
* ``normal`` injects nothing.

A flag-ledger record::

    {
      "t": int,                        # flag-ledger index
      "unl_size": int,                 # configured UNL size at t
      "online": [validator ids],       # validators expected to vote at t
      "votes": {vid: {"seq": int, "yes": bool, "lag": int}},
                                       # votes that ARRIVED at t
      "messages": [{"validator": vid, "seq": int,
                    "kind": "validation" | "duplicate" | "stale"}],
    }

Votes that are delayed have not arrived yet, so they are absent from
``votes`` at their own ledger and appear later with ``lag`` > 0. A
duplicate message carries no new vote; a stale message carries an old
sequence number.
"""

import json
import random

DEFAULT_N = 53
FLAG_LEDGERS = 120
INJECT_AT = 40
DRIFT_LEN = 30
DRIFT_END_SUPPORT = 0.62
BASELINE_SUPPORT = 0.90
SKEW_COUNT = 8
SKEW_LAG = 3
CHURN_OFFLINE = 12
CHURN_JOIN = 4
CHURN_JOIN_AT = 10
REPLAY_LEN = 20
REPLAY_DUP_RATE = 0.15
REPLAY_STALE_RATE = 0.05

SCENARIOS = ["normal", "timing-skew", "quorum-drift", "churn", "replay"]


def make_validators(n, rng, yes_low=0.85, yes_high=1.0):
    """One entry per validator: id and fixed yes-propensity."""
    return [
        {"id": "val-%02d" % i, "yes_p": rng.uniform(yes_low, yes_high)}
        for i in range(n)
    ]


def _drift_factor(t, inject_at, drift_len, end_support, baseline):
    """Multiplier on yes-propensity while support drifts down."""
    if t < inject_at:
        return 1.0
    frac = min(1.0, (t - inject_at + 1) / float(drift_len))
    target = baseline + (end_support - baseline) * frac
    return target / baseline


def generate(scenario, seed, n=DEFAULT_N, flag_ledgers=FLAG_LEDGERS,
             inject_at=INJECT_AT):
    """Generate one vote stream. Returns a list of flag-ledger records."""
    if scenario not in SCENARIOS:
        raise ValueError("unknown scenario: %r" % scenario)
    rng = random.Random(seed)
    validators = make_validators(n, rng)
    by_id = {v["id"]: v for v in validators}

    # Churn bookkeeping.
    offline = set()
    joined = []
    if scenario == "churn":
        offline = set(rng.sample([v["id"] for v in validators],
                                 CHURN_OFFLINE))
    skew_ids = set()
    if scenario == "timing-skew":
        skew_ids = set(rng.sample([v["id"] for v in validators],
                                  SKEW_COUNT))

    pending = {}  # vid -> list of (seq, yes) held for late delivery
    records = []
    for t in range(flag_ledgers):
        # Membership changes for churn.
        if scenario == "churn" and t == inject_at + CHURN_JOIN_AT:
            for j in range(CHURN_JOIN):
                vid = "val-new-%02d" % j
                joined.append({"id": vid, "yes_p": 0.5})
                by_id[vid] = joined[-1]
        online = [v["id"] for v in validators
                  if not (scenario == "churn" and t >= inject_at
                          and v["id"] in offline)]
        online += [v["id"] for v in joined]
        unl_size = len(validators) + len(joined)

        drift = 1.0
        if scenario == "quorum-drift":
            drift = _drift_factor(t, inject_at, DRIFT_LEN,
                                  DRIFT_END_SUPPORT, BASELINE_SUPPORT)

        votes = {}
        messages = []
        for vid in online:
            yes = rng.random() < by_id[vid]["yes_p"] * drift
            if scenario == "timing-skew" and vid in skew_ids \
                    and t >= inject_at:
                # Vote is generated now, delivered SKEW_LAG ledgers later.
                pending.setdefault(vid, []).append((t, yes))
                continue
            votes[vid] = {"seq": t, "yes": yes, "lag": 0}
            messages.append({"validator": vid, "seq": t,
                             "kind": "validation"})

        # Deliver delayed votes whose arrival ledger is now.
        if scenario == "timing-skew":
            for vid, held in list(pending.items()):
                due = [(s, y) for (s, y) in held if s + SKEW_LAG <= t]
                for (s, y) in due:
                    votes[vid] = {"seq": s, "yes": y, "lag": t - s}
                    messages.append({"validator": vid, "seq": s,
                                     "kind": "validation"})
                pending[vid] = [(s, y) for (s, y) in held
                                if s + SKEW_LAG > t]

        # Replay injection: duplicates and stale validations.
        if scenario == "replay" and inject_at <= t < inject_at + REPLAY_LEN:
            for vid in online:
                r = rng.random()
                if r < REPLAY_DUP_RATE:
                    messages.append({"validator": vid, "seq": t,
                                     "kind": "duplicate"})
                elif r < REPLAY_DUP_RATE + REPLAY_STALE_RATE:
                    messages.append({"validator": vid, "seq": max(0, t - 2),
                                     "kind": "stale"})

        records.append({
            "t": t,
            "unl_size": unl_size,
            "online": sorted(online),
            "votes": votes,
            "messages": messages,
        })
    return records


def stream_to_json(records):
    """Canonical JSON encoding of a stream (sorted keys, no whitespace)."""
    return json.dumps(records, sort_keys=True, separators=(",", ":"))


if __name__ == "__main__":
    import sys
    scenario = sys.argv[1] if len(sys.argv) > 1 else "normal"
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1001
    recs = generate(scenario, seed)
    print("scenario=%s seed=%d flag_ledgers=%d" % (scenario, seed, len(recs)))
    last = recs[-1]
    yes = sum(1 for v in last["votes"].values() if v["yes"])
    print("final ledger t=%d online=%d votes=%d yes=%d support=%.3f"
          % (last["t"], len(last["online"]), len(last["votes"]), yes,
             yes / max(1, len(last["online"]))))
