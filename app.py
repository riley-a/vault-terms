"""
Verkada license co-termination planner.

Local single-user tool: lets a Verkada reseller/admin model an org's license
co-termination (all Verkada licenses expire on one weighted-average org-wide
date). The user adds "license columns" (LicenseUnits) from the built-in
catalog (or a custom column), enters the "before" state and any planned
"new" additions, and computes a single org-wide co-term date plus a
per-column breakdown.

No auth, no persistence beyond the request/response cycle -- state lives in
the browser and is POSTed fresh on every compute.
"""
from datetime import date

from flask import Flask, jsonify, render_template, request

from coterm.catalog import CATALOG, FAMILIES
from coterm.engine import LicenseBatch, LicenseUnit, Organization
from coterm.timeline import compute_timeline

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/catalog")
def catalog():
    units = []
    for unit_def in CATALOG.values():
        units.append(
            {
                "key": unit_def.key,
                "label": unit_def.label,
                "family": unit_def.family,
                "unit_basis": unit_def.unit_basis,
                "devices_per_license": unit_def.devices_per_license,
                "term_options_days": list(unit_def.term_options_days),
                "skus": [
                    {
                        "term_days": s.term_days,
                        "us_price": s.us_price,
                        "term_label": s.term_label,
                    }
                    for s in unit_def.skus
                ],
            }
        )
    # Keep a stable, sensible family order; append any unexpected extras.
    families = [f for f in FAMILIES]
    for u in units:
        if u["family"] not in families:
            families.append(u["family"])

    return jsonify(families=families, units=units)


def _parse_date(value):
    if not value:
        return None
    return date.fromisoformat(value)


def _non_negative_int(value, default=0):
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return n if n >= 0 else default


def _non_negative_float(value, default=1.0):
    try:
        n = float(value)
    except (TypeError, ValueError):
        return default
    return n if n > 0 else default


@app.route("/api/coterm/compute", methods=["POST"])
def compute():
    data = request.get_json(silent=True) or {}

    org_name = (data.get("org_name") or "").strip() or "Untitled Org"
    as_of_raw = data.get("as_of_date")
    try:
        as_of_date = _parse_date(as_of_raw) or date.today()
    except ValueError:
        return jsonify(error=f"Invalid as_of_date: {as_of_raw!r}"), 400

    raw_units = data.get("units") or []
    if not raw_units:
        return jsonify(error="At least one license column is required"), 400

    org = Organization(org_name, as_of_date)

    for raw in raw_units:
        key = (raw.get("key") or "").strip()
        label = (raw.get("label") or key or "Untitled License").strip()
        family = (raw.get("family") or "Custom").strip()
        devices_per_license = _non_negative_float(raw.get("devices_per_license"), 1.0)

        unit = LicenseUnit(
            key=key or label.lower().replace(" ", "_"),
            label=label,
            family=family,
            devices_per_license=devices_per_license,
        )

        unit.claimed_before = _non_negative_int(raw.get("claimed_before"), 0)
        unit.active_before = _non_negative_int(raw.get("active_before"), 0)

        try:
            unit.expiration_before = _parse_date(raw.get("expiration_before"))
        except ValueError:
            return (
                jsonify(
                    error=f"Invalid expiration_before for '{label}': "
                    f"{raw.get('expiration_before')!r}"
                ),
                400,
            )

        unit.new_claimed_devices = _non_negative_int(raw.get("new_claimed_devices"), 0)

        batches = []
        for b in raw.get("new_batches") or []:
            term_days = _non_negative_int(b.get("term_days"), 0)
            quantity = _non_negative_int(b.get("quantity"), 0)
            if term_days > 0 and quantity > 0:
                batches.append(LicenseBatch(term_days=term_days, quantity=quantity))
        unit.new_batches = batches

        org.register_unit(unit)

    return jsonify(org.to_dict())


@app.route("/api/coterm/timeline", methods=["POST"])
def timeline():
    data = request.get_json(silent=True) or {}
    org_name = (data.get("org_name") or "").strip() or "Untitled Org"

    starting_raw = data.get("starting_expiration_date")
    try:
        starting_expiration = _parse_date(starting_raw)
    except ValueError:
        return jsonify(error=f"Invalid starting_expiration_date: {starting_raw!r}"), 400
    if not starting_expiration:
        return jsonify(error="starting_expiration_date is required"), 400

    as_of_raw = data.get("as_of_date")
    try:
        as_of_date = _parse_date(as_of_raw)
    except ValueError:
        return jsonify(error=f"Invalid as_of_date: {as_of_raw!r}"), 400

    raw_columns = data.get("columns") or []
    columns = []
    for raw in raw_columns:
        key = (raw.get("key") or "").strip()
        if not key:
            continue
        columns.append({
            "key": key,
            "label": (raw.get("label") or key).strip(),
            "family": (raw.get("family") or "Custom").strip(),
            "devices_per_license": _non_negative_float(raw.get("devices_per_license"), 1.0),
            "claimed_before": _non_negative_int(raw.get("claimed_before"), 0),
            "active_before": _non_negative_int(raw.get("active_before"), 0),
        })

    raw_steps = data.get("steps") or []
    if not raw_steps:
        return jsonify(error="At least one step is required"), 400

    steps = []
    for i, raw in enumerate(raw_steps):
        step_date_raw = raw.get("date")
        try:
            step_date = _parse_date(step_date_raw)
        except ValueError:
            return jsonify(error=f"Invalid date for step {i + 1}: {step_date_raw!r}"), 400
        if not step_date:
            return jsonify(error=f"date is required for step {i + 1}"), 400

        entries = []
        for e in raw.get("entries") or []:
            key = (e.get("key") or "").strip()
            if not key:
                continue
            term_days = _non_negative_int(e.get("term_days"), 0)
            devices_claimed = _non_negative_int(e.get("devices_claimed"), 0)
            if term_days <= 0 or devices_claimed <= 0:
                continue
            entries.append({
                "key": key,
                "label": (e.get("label") or key).strip(),
                "family": (e.get("family") or "Custom").strip(),
                "devices_per_license": _non_negative_float(e.get("devices_per_license"), 1.0),
                "term_days": term_days,
                "kind": "renewal" if e.get("kind") == "renewal" else "capacity",
                "devices_claimed": devices_claimed,
            })
        steps.append({"label": raw.get("label") or f"Order {i + 1}", "date": step_date, "entries": entries})

    result = compute_timeline(org_name, starting_expiration, columns, steps, as_of_date=as_of_date)
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=False)
