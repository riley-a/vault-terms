"""Tests for coterm.engine - the co-termination math core.

Covers Verkada's two official worked examples plus the org-wide pooling,
dynamic registration, and zero-state edge cases described in the design
spec.
"""

from datetime import date, timedelta

import pytest

from coterm.engine import LicenseBatch, LicenseUnit, Organization


AS_OF = date(2026, 1, 1)


def test_example_1_initial_purchase_same_day():
    """Verkada doc example 1: 1x 1-year camera license + 1x 3-year camera
    license purchased same day -> co-term = (1095*1 + 365*1) / 2 = 730 days.
    """
    org = Organization("Acme Co", AS_OF)
    unit = LicenseUnit(
        key="cam_camera", label="Camera License", family="Cameras",
        devices_per_license=1,
    )
    # No prior licensing state at all - this is an initial purchase.
    unit.claimed_before = 0
    unit.expiration_before = None
    unit.new_claimed_devices = 2
    unit.new_batches = [LicenseBatch(365, 1), LicenseBatch(1095, 1)]
    org.register_unit(unit)

    assert unit.existing_license_days(AS_OF) == 0.0
    assert unit.added_license_days() == 365 * 1 + 1095 * 1
    assert unit.standalone_remaining_days(AS_OF) == pytest.approx(730.0)
    assert unit.standalone_expiration_date(AS_OF) == AS_OF + timedelta(days=730)

    # With only one unit registered, org-wide should match the standalone math.
    assert org.org_remaining_days() == pytest.approx(730.0)
    assert org.org_expiration_date() == AS_OF + timedelta(days=730)


def test_example_2_mid_term_addition():
    """Verkada doc example 2: org has 10 cameras w/ 8 months (approx, 30-day
    months) remaining on 1-year licenses, then buys 3 more 1-year licenses
    for 3 new cameras.

    Existing pool: 8 months * 30 days/month * 10 cameras = 2400 license-days.
    Added pool: 365 days * 3 new licenses = 1095 license-days.
    New device count: 10 + 3 = 13.
    -> remaining = (2400 + 1095) / 13 = 3495 / 13 ~= 268.85 days
       (~8.96 months at 30-day months), which is within 0.5 months of the
       doc's 8.92-month figure (the doc itself mixes 30-day-month and
       365-day-year conventions; this engine uses real days consistently).
    """
    unit = LicenseUnit(
        key="cam_camera", label="Camera License", family="Cameras",
        devices_per_license=1,
    )
    unit.claimed_before = 10
    unit.expiration_before = AS_OF + timedelta(days=240)  # 8 months * 30 days
    unit.new_claimed_devices = 3
    unit.new_batches = [LicenseBatch(365, 3)]

    assert unit.required_units_before() == 10
    assert unit.existing_license_days(AS_OF) == pytest.approx(2400.0)
    assert unit.added_license_days() == pytest.approx(1095.0)
    assert unit.required_units_after() == 13
    assert unit.total_license_days(AS_OF) == pytest.approx(3495.0)

    remaining_days = unit.standalone_remaining_days(AS_OF)
    assert remaining_days == pytest.approx(3495.0 / 13.0)

    remaining_months = remaining_days / 30.0
    assert remaining_months == pytest.approx(8.92, abs=0.5)


def test_register_unit_dynamic_custom_unit():
    """A brand-new, not-in-CATALOG license unit can be registered at runtime
    and shows up correctly in the breakdown with no other code changes."""
    org = Organization("Acme Co", AS_OF)
    custom = LicenseUnit(
        key="custom_thing",
        label="Custom Future Product License",
        family="Future Products",
        devices_per_license=1,
    )
    custom.claimed_before = 5
    custom.expiration_before = AS_OF + timedelta(days=100)
    custom.new_claimed_devices = 0
    custom.new_batches = []

    org.register_unit(custom)

    assert "Future Products" in org.families
    assert org.families["Future Products"].units["custom_thing"] is custom

    rows = org.breakdown()
    keys = [r["key"] for r in rows]
    assert "custom_thing" in keys

    row = next(r for r in rows if r["key"] == "custom_thing")
    assert row["label"] == "Custom Future Product License"
    assert row["family"] == "Future Products"
    assert row["claimed_before"] == 5
    assert row["existing_license_days"] == pytest.approx(100 * 5)


def test_org_wide_pooling_multi_unit():
    """Hand-computed 3-unit example verifying org_remaining_days() ==
    sum(total_license_days) / sum(required_units_after)."""
    org = Organization("Acme Co", AS_OF)

    # Unit A: 4 devices, 100 days remaining existing, no new purchase.
    unit_a = LicenseUnit(key="a", label="A", family="Fam", devices_per_license=1)
    unit_a.claimed_before = 4
    unit_a.expiration_before = AS_OF + timedelta(days=100)
    org.register_unit(unit_a)

    # Unit B: 2 devices, 50 days remaining existing, plus a new batch adding
    # 3 more devices with a 365-day license each.
    unit_b = LicenseUnit(key="b", label="B", family="Fam", devices_per_license=1)
    unit_b.claimed_before = 2
    unit_b.expiration_before = AS_OF + timedelta(days=50)
    unit_b.new_claimed_devices = 3
    unit_b.new_batches = [LicenseBatch(365, 3)]
    org.register_unit(unit_b)

    # Unit C: brand new unit, 5 devices, single 1095-day (3yr) batch.
    unit_c = LicenseUnit(key="c", label="C", family="OtherFam", devices_per_license=1)
    unit_c.new_claimed_devices = 5
    unit_c.new_batches = [LicenseBatch(1095, 5)]
    org.register_unit(unit_c)

    # Hand-computed expectations.
    a_days = 100 * 4  # 400
    a_units = 4
    b_days = 50 * 2 + 365 * 3  # 100 + 1095 = 1195
    b_units = 5
    c_days = 1095 * 5  # 5475
    c_units = 5

    expected_total_days = a_days + b_days + c_days  # 400+1195+5475 = 7070
    expected_total_units = a_units + b_units + c_units  # 4+5+5 = 14
    expected_remaining = expected_total_days / expected_total_units

    assert org.org_total_license_days() == pytest.approx(expected_total_days)
    assert org.org_total_required_units() == pytest.approx(expected_total_units)
    assert org.org_remaining_days() == pytest.approx(expected_remaining)
    assert org.org_expiration_date() == AS_OF + timedelta(days=expected_remaining)


def test_zero_state_brand_new_org_does_not_raise():
    """A brand new org with no units, and a unit with all-zero state, must
    not raise (guard against ZeroDivisionError)."""
    org = Organization("Empty Co", AS_OF)

    # No units registered at all.
    assert org.org_total_license_days() == 0.0
    assert org.org_total_required_units() == 0.0
    assert org.org_remaining_days() == 0.0
    assert org.org_expiration_date() == AS_OF
    assert org.breakdown() == []
    assert org.to_dict()["rows"] == []

    # A registered unit with zero claimed devices and no purchases at all.
    empty_unit = LicenseUnit(
        key="empty", label="Empty Unit", family="Fam", devices_per_license=1,
    )
    org.register_unit(empty_unit)

    assert empty_unit.required_units_before() == 0
    assert empty_unit.required_units_after() == 0
    assert empty_unit.existing_license_days(AS_OF) == 0.0
    assert empty_unit.added_license_days() == 0.0
    assert empty_unit.standalone_remaining_days(AS_OF) == 0.0
    assert empty_unit.standalone_expiration_date(AS_OF) is None

    assert org.org_remaining_days() == 0.0
    assert org.org_expiration_date() == AS_OF

    rows = org.breakdown()
    assert len(rows) == 1
    assert rows[0]["standalone_expiration_date"] is None
    assert rows[0]["share_of_org_days_pct"] == 0.0
