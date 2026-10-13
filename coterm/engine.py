"""Verkada co-termination math engine.

Core model:
    Organization -> ProductFamily (display grouping only) -> LicenseUnit
        (one independent column per license SKU, e.g. "Door License")

Every LicenseUnit tracks license-days (term_days * quantity). The
org-wide co-term date is the weighted average across every license-day
pool in the org: sum(total_license_days) / sum(required_units_after).

Each LicenseUnit also exposes a standalone remaining-days/expiration as
if it were the only license type in the org, purely for the per-row
breakdown display.

Real calendar days (365-day years) are used consistently throughout -
Verkada's own worked examples sometimes use a 30-day-month
approximation, but this engine does not mix conventions.
"""

import math
from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass
class LicenseBatch:
    term_days: int
    quantity: int

    @property
    def license_days(self) -> float:
        return self.term_days * self.quantity


class LicenseUnit:
    def __init__(
        self,
        key: str,
        label: str,
        family: str,
        devices_per_license: float = 1.0,
    ):
        self.key = key
        self.label = label
        self.family = family
        self.devices_per_license = devices_per_license

        # "before" state (existing licensing prior to any new purchase)
        self.claimed_before: int = 0
        self.active_before: int = 0
        self.expiration_before: date | None = None

        # "new" additions (the co-term planning scenario being modeled)
        self.new_claimed_devices: int = 0
        self.new_batches: list[LicenseBatch] = []

    def required_units(self, claimed: int) -> float:
        if self.devices_per_license <= 0:
            return 0
        return math.ceil(claimed / self.devices_per_license)

    def required_units_before(self) -> float:
        return self.required_units(self.claimed_before)

    def required_units_after(self) -> float:
        return self.required_units(self.claimed_before + self.new_claimed_devices)

    def existing_license_days(self, as_of: date) -> float:
        """License-days remaining in the pre-existing licensing pool.

        Zero if there is no prior expiration (brand-new unit/org) or no
        prior claimed devices. Floored at 0 (never negative, e.g. if the
        unit is already past its expiration).
        """
        if self.expiration_before is None or self.claimed_before <= 0:
            return 0.0
        remaining_days = (self.expiration_before - as_of).days
        if remaining_days <= 0:
            return 0.0
        return remaining_days * self.required_units_before()

    def added_license_days(self) -> float:
        return sum(b.license_days for b in self.new_batches)

    def total_license_days(self, as_of: date) -> float:
        return self.existing_license_days(as_of) + self.added_license_days()

    def standalone_remaining_days(self, as_of: date) -> float:
        """This unit's own remaining days per required unit, as if it were
        the only license type in the org."""
        units = self.required_units_after()
        if not units:
            return 0.0
        return self.total_license_days(as_of) / units

    def standalone_expiration_date(self, as_of: date) -> date | None:
        remaining = self.standalone_remaining_days(as_of)
        if not remaining:
            return None
        return as_of + timedelta(days=remaining)


class ProductFamily:
    def __init__(self, name: str):
        self.name = name
        self.units: dict[str, LicenseUnit] = {}

    def add_unit(self, unit: LicenseUnit):
        self.units[unit.key] = unit


class Organization:
    def __init__(self, name: str, as_of_date: date):
        self.name = name
        self.as_of_date = as_of_date
        self.families: dict[str, ProductFamily] = {}

    def register_unit(self, unit: LicenseUnit):
        fam = self.families.setdefault(unit.family, ProductFamily(unit.family))
        fam.add_unit(unit)

    def all_units(self) -> list[LicenseUnit]:
        units: list[LicenseUnit] = []
        for fam in self.families.values():
            units.extend(fam.units.values())
        return units

    def org_total_license_days(self) -> float:
        return sum(u.total_license_days(self.as_of_date) for u in self.all_units())

    def org_total_required_units(self) -> float:
        return sum(u.required_units_after() for u in self.all_units())

    def org_remaining_days(self) -> float:
        total_units = self.org_total_required_units()
        return self.org_total_license_days() / total_units if total_units else 0.0

    def org_expiration_date(self) -> date:
        return self.as_of_date + timedelta(days=self.org_remaining_days())

    def breakdown(self) -> list[dict]:
        org_total_days = self.org_total_license_days()
        rows = []
        for u in self.all_units():
            total_days = u.total_license_days(self.as_of_date)
            standalone_exp = u.standalone_expiration_date(self.as_of_date)
            share = (total_days / org_total_days * 100.0) if org_total_days else 0.0
            rows.append(
                {
                    "key": u.key,
                    "label": u.label,
                    "family": u.family,
                    "claimed_before": u.claimed_before,
                    "active_before": u.active_before,
                    "expiration_before": (
                        u.expiration_before.isoformat()
                        if u.expiration_before
                        else None
                    ),
                    "existing_license_days": u.existing_license_days(self.as_of_date),
                    "added_license_days": u.added_license_days(),
                    "total_license_days": total_days,
                    "required_units_after": u.required_units_after(),
                    "standalone_remaining_days": u.standalone_remaining_days(
                        self.as_of_date
                    ),
                    "standalone_expiration_date": (
                        standalone_exp.isoformat() if standalone_exp else None
                    ),
                    "share_of_org_days_pct": share,
                }
            )
        return rows

    def to_dict(self) -> dict:
        return {
            "org_name": self.name,
            "as_of_date": self.as_of_date.isoformat(),
            "org_remaining_days": self.org_remaining_days(),
            "org_expiration_date": self.org_expiration_date().isoformat(),
            "rows": self.breakdown(),
        }
