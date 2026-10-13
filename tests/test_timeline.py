"""Tests for coterm.timeline - multi-step co-term timeline simulation.

Covers: single-step correctness against hand/engine-computed values, a
multi-step sequence carrying state forward correctly, on-the-fly
registration of brand-new product lines mid-sequence, renewal vs. capacity
entries within one step, and the empty-steps edge case.
"""

from datetime import date, timedelta

import pytest

from coterm.engine import LicenseBatch, LicenseUnit, Organization
from coterm.timeline import compute_timeline


AS_OF = date(2026, 1, 1)


def test_single_step_matches_hand_computed_engine_math():
    """One column, one capacity step -- should exactly match what building
    the equivalent Organization directly (as the single-step engine does)
    would produce."""
    starting_expiration = AS_OF + timedelta(days=100)
    columns = [
        {
            "key": "a",
            "label": "A",
            "family": "Fam",
            "devices_per_license": 1,
            "claimed_before": 4,
            "active_before": 4,
        }
    ]
    steps = [
        {
            "label": "Order 1",
            "date": AS_OF,
            "entries": [
                {
                    "key": "a",
                    "label": "A",
                    "family": "Fam",
                    "devices_per_license": 1,
                    "term_days": 365,
                    "kind": "capacity",
                    "devices_claimed": 3,
                }
            ],
        }
    ]

    result = compute_timeline("Acme Co", starting_expiration, columns, steps)

    # Cross-check against building the equivalent Organization directly.
    expected_unit = LicenseUnit(key="a", label="A", family="Fam", devices_per_license=1)
    expected_unit.claimed_before = 4
    expected_unit.active_before = 4
    expected_unit.expiration_before = starting_expiration
    expected_unit.new_claimed_devices = 3
    expected_unit.new_batches = [LicenseBatch(365, 3)]
    expected_org = Organization("Acme Co", AS_OF)
    expected_org.register_unit(expected_unit)
    expected = expected_org.to_dict()

    assert result["org_name"] == "Acme Co"
    assert len(result["steps"]) == 2  # Starting point + Order 1

    order_1 = result["steps"][1]
    assert order_1["label"] == "Order 1"
    assert order_1["date"] == AS_OF.isoformat()
    assert order_1["org_expiration_date"] == expected["org_expiration_date"]
    assert order_1["org_remaining_days"] == pytest.approx(expected["org_remaining_days"])

    # 400 existing + 1095 added = 1495 total days / 7 required units.
    assert order_1["org_remaining_days"] == pytest.approx(1495.0 / 7.0)


def test_three_step_sequence_carries_claimed_devices_forward():
    """Three chronological capacity steps on one column: claimed devices
    must strictly increase step over step, each step's date must be
    reflected in the output, and the Starting point step must show zero
    added license-days."""
    starting_expiration = AS_OF + timedelta(days=200)
    columns = [
        {
            "key": "cam",
            "label": "Camera License",
            "family": "Cameras",
            "devices_per_license": 1,
            "claimed_before": 5,
            "active_before": 5,
        }
    ]
    step_dates = [AS_OF, AS_OF + timedelta(days=180), AS_OF + timedelta(days=545)]
    steps = [
        {
            "label": f"Order {i + 1}",
            "date": d,
            "entries": [
                {
                    "key": "cam",
                    "label": "Camera License",
                    "family": "Cameras",
                    "devices_per_license": 1,
                    "term_days": 365,
                    "kind": "capacity",
                    "devices_claimed": 2,
                }
            ],
        }
        for i, d in enumerate(step_dates)
    ]

    result = compute_timeline("Acme Co", starting_expiration, columns, steps)

    assert len(result["steps"]) == 4  # Starting point + 3 orders

    starting_point = result["steps"][0]
    assert starting_point["label"] == "Starting point"
    assert starting_point["date"] == step_dates[0].isoformat()
    assert starting_point["rows"][0]["added_license_days"] == 0

    claimed_sequence = [s["rows"][0]["claimed_before"] for s in result["steps"][1:]]
    assert claimed_sequence == [5, 7, 9]
    assert claimed_sequence[0] < claimed_sequence[1] < claimed_sequence[2]

    for step_out, expected_date in zip(result["steps"][1:], step_dates):
        assert step_out["date"] == expected_date.isoformat()


def test_step_introduces_brand_new_column_not_in_starting_columns():
    """An entry referencing a key absent from `columns` entirely is a
    brand-new product line, registered on the fly with claimed_before
    effectively 0."""
    starting_expiration = AS_OF + timedelta(days=100)
    columns = [
        {
            "key": "a",
            "label": "A",
            "family": "Fam",
            "devices_per_license": 1,
            "claimed_before": 4,
            "active_before": 4,
        }
    ]
    steps = [
        {
            "label": "Order 1",
            "date": AS_OF,
            "entries": [
                {
                    "key": "brand_new",
                    "label": "Brand New Product",
                    "family": "New Fam",
                    "devices_per_license": 1,
                    "term_days": 365,
                    "kind": "capacity",
                    "devices_claimed": 6,
                }
            ],
        }
    ]

    result = compute_timeline("Acme Co", starting_expiration, columns, steps)

    order_1 = result["steps"][1]
    keys = [r["key"] for r in order_1["rows"]]
    assert "brand_new" in keys

    row = next(r for r in order_1["rows"] if r["key"] == "brand_new")
    assert row["claimed_before"] == 0
    assert row["existing_license_days"] == 0
    assert row["added_license_days"] == pytest.approx(365 * 6)

    # Not present at all in the Starting point step (introduced later).
    starting_point_keys = [r["key"] for r in result["steps"][0]["rows"]]
    assert "brand_new" not in starting_point_keys


def test_renewal_and_capacity_mixed_in_same_step():
    """Renewal entries add license-days only; capacity entries add both
    license-days and devices carried into the next step -- mirroring the
    single-step engine's existing new_claimed_devices vs new_batches split."""
    starting_expiration = AS_OF + timedelta(days=100)
    columns = [
        {
            "key": "a",
            "label": "A",
            "family": "Fam",
            "devices_per_license": 1,
            "claimed_before": 4,
            "active_before": 4,
        }
    ]
    steps = [
        {
            "label": "Order 1",
            "date": AS_OF,
            "entries": [
                {
                    "key": "a",
                    "label": "A",
                    "family": "Fam",
                    "devices_per_license": 1,
                    "term_days": 365,
                    "kind": "renewal",
                    "devices_claimed": 4,
                },
                {
                    "key": "a",
                    "label": "A",
                    "family": "Fam",
                    "devices_per_license": 1,
                    "term_days": 365,
                    "kind": "capacity",
                    "devices_claimed": 2,
                },
            ],
        },
        {
            "label": "Order 2",
            "date": AS_OF + timedelta(days=180),
            "entries": [],
        },
    ]

    result = compute_timeline("Acme Co", starting_expiration, columns, steps)

    order_1_row = result["steps"][1]["rows"][0]
    # Both batches count toward added license-days: 365*4 (renewal) + 365*2 (capacity).
    assert order_1_row["added_license_days"] == pytest.approx(365 * 4 + 365 * 2)
    # required_units_after only counts claimed_before + capacity devices (not renewal).
    assert order_1_row["required_units_after"] == 4 + 2

    # Next step's "before" claimed count only carries forward the capacity
    # devices (2), not the renewal devices.
    order_2_row = result["steps"][2]["rows"][0]
    assert order_2_row["claimed_before"] == 4 + 2


def test_explicit_as_of_date_anchors_starting_point_not_first_order_date():
    """The Starting point snapshot should reflect the org's position as of
    an explicitly-given `as_of_date` ("today"), not the date of the first
    future order -- a user planning an order 6 months out shouldn't have
    the Starting point silently jump forward to that order's date. Each
    order's own co-term is still computed as of *that order's* claim date,
    independent of as_of_date."""
    starting_expiration = AS_OF + timedelta(days=100)
    columns = [
        {
            "key": "a",
            "label": "A",
            "family": "Fam",
            "devices_per_license": 1,
            "claimed_before": 4,
            "active_before": 4,
        }
    ]
    future_order_date = AS_OF + timedelta(days=180)
    steps = [
        {
            "label": "Order 1",
            "date": future_order_date,
            "entries": [
                {
                    "key": "a",
                    "label": "A",
                    "family": "Fam",
                    "devices_per_license": 1,
                    "term_days": 365,
                    "kind": "capacity",
                    "devices_claimed": 2,
                }
            ],
        }
    ]

    result = compute_timeline("Acme Co", starting_expiration, columns, steps, as_of_date=AS_OF)

    starting_point = result["steps"][0]
    assert starting_point["date"] == AS_OF.isoformat()
    assert starting_point["date"] != future_order_date.isoformat()
    # Starting point as of AS_OF: 100 days remaining / 4 devices.
    assert starting_point["org_remaining_days"] == pytest.approx(100.0)

    order_1 = result["steps"][1]
    assert order_1["date"] == future_order_date.isoformat()


def test_empty_steps_does_not_raise_and_returns_starting_point_only():
    """Calling compute_timeline directly with steps=[] must not raise, even
    though the Flask route rejects this with a 400. Sensible behavior:
    return just the synthetic Starting point entry."""
    starting_expiration = AS_OF + timedelta(days=100)
    columns = [
        {
            "key": "a",
            "label": "A",
            "family": "Fam",
            "devices_per_license": 1,
            "claimed_before": 4,
            "active_before": 4,
        }
    ]

    result = compute_timeline("Acme Co", starting_expiration, columns, [])

    assert result["org_name"] == "Acme Co"
    assert len(result["steps"]) == 1
    assert result["steps"][0]["label"] == "Starting point"
    assert result["steps"][0]["date"] == date.today().isoformat()
