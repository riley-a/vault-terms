"""Multi-step co-term timeline simulation.

Models a chronological sequence of purchase events ("steps") against a
single org-wide pooled co-term date. Verkada's org-wide co-term is always
one date shared across every license type -- so after each step's
purchase, the org's newly-computed pooled date becomes the single
``expiration_before`` fed into every column for the *next* step. Per-column
claimed-device counts evolve independently: "capacity" entries add to a
column's running claimed count (and to its license-days); "renewal"
entries only add license-days, never claimed devices -- mirroring
``LicenseUnit.new_claimed_devices`` vs ``LicenseUnit.new_batches`` in
coterm.engine.

Pure module: no Flask dependency. See app.py's /api/coterm/timeline route
for the HTTP-facing wrapper.
"""

import math
from datetime import date

from coterm.engine import LicenseBatch, LicenseUnit, Organization


def compute_timeline(org_name, starting_expiration_date, columns, steps, as_of_date=None):
    """Simulate a chronological sequence of co-term purchase events.

    Args:
        org_name: str
        starting_expiration_date: date -- the single org-wide expiration
            date shared by every column before the first step.
        columns: list of dicts, the starting known product lines:
            {"key", "label", "family", "devices_per_license",
             "claimed_before", "active_before"}
        steps: list of dicts, in chronological order:
            {"label", "date", "entries": [
                {"key", "label", "family", "devices_per_license",
                 "term_days", "kind" ("capacity"|"renewal"), "devices_claimed"}
            ]}
            An entry's key may reference a column not in `columns` at all,
            or not yet introduced by an earlier step -- it is registered on
            the fly with an implicit claimed_before/active_before of 0.
        as_of_date: date, optional -- the reference date for the synthetic
            "Starting point" snapshot (i.e. "today", or whatever the caller
            considers the org's current position to be). This is distinct
            from each step's own `date`: a step's co-term is always computed
            as of *that step's* claim date (its purchase is assumed to have
            full value starting that day), regardless of when "today" is.
            Defaults to the first step's date, or today if `steps` is empty,
            for backward compatibility with callers that don't pass it.

    Returns:
        {"org_name": str, "steps": [
            {"label", "date" (iso str), "org_expiration_date",
             "org_remaining_days", "rows"}, ...
        ]}
        One entry for a synthetic "Starting point" step (no purchases, as of
        `as_of_date`), followed by one entry per input step -- each computed
        as of that step's own claim date -- in order.
    """
    running = {}  # key -> {"label", "family", "devices_per_license", "claimed", "active"}
    for col in columns:
        running[col["key"]] = {
            "label": col["label"],
            "family": col["family"],
            "devices_per_license": col["devices_per_license"] or 1,
            "claimed": col["claimed_before"],
            "active": col["active_before"],
        }

    current_expiration = starting_expiration_date
    results = []

    starting_as_of = as_of_date or (steps[0]["date"] if steps else date.today())

    def build_org(as_of, new_by_key):
        org = Organization(org_name, as_of)
        for key, col in running.items():
            unit = LicenseUnit(
                key=key,
                label=col["label"],
                family=col["family"],
                devices_per_license=col["devices_per_license"],
            )
            unit.claimed_before = col["claimed"]
            unit.active_before = col["active"]
            unit.expiration_before = current_expiration
            bucket = new_by_key.get(key)
            if bucket:
                unit.new_claimed_devices = bucket["devices"]
                unit.new_batches = bucket["batches"]
            org.register_unit(unit)
        return org

    # Starting point: snapshot with no purchases applied.
    d0 = build_org(starting_as_of, {}).to_dict()
    results.append(
        {
            "label": "Starting point",
            "date": starting_as_of.isoformat(),
            "org_expiration_date": d0["org_expiration_date"],
            "org_remaining_days": d0["org_remaining_days"],
            "rows": d0["rows"],
        }
    )

    for i, step in enumerate(steps):
        # Register any brand-new product lines this step introduces.
        for e in step["entries"]:
            if e["key"] not in running:
                running[e["key"]] = {
                    "label": e["label"],
                    "family": e["family"],
                    "devices_per_license": e["devices_per_license"] or 1,
                    "claimed": 0,
                    "active": 0,
                }

        # Aggregate this step's entries per key -- capacity adds to device
        # count AND license-days, renewal adds ONLY to license-days (never
        # to device count).
        new_by_key = {}
        for e in step["entries"]:
            bucket = new_by_key.setdefault(e["key"], {"devices": 0, "batches": []})
            dpl = running[e["key"]]["devices_per_license"] or 1
            qty = max(1, math.ceil(e["devices_claimed"] / dpl))
            bucket["batches"].append(LicenseBatch(e["term_days"], qty))
            if e["kind"] != "renewal":
                bucket["devices"] += e["devices_claimed"]

        org = build_org(step["date"], new_by_key)
        d = org.to_dict()
        results.append(
            {
                "label": step.get("label") or f"Order {i + 1}",
                "date": step["date"].isoformat(),
                "org_expiration_date": d["org_expiration_date"],
                "org_remaining_days": d["org_remaining_days"],
                "rows": d["rows"],
            }
        )

        # Carry state forward: the org's new pooled date becomes next
        # step's shared expiration_before, and capacity (not renewal)
        # devices join the running claimed count.
        current_expiration = org.org_expiration_date()
        for key, bucket in new_by_key.items():
            running[key]["claimed"] += bucket["devices"]

    return {"org_name": org_name, "steps": results}
