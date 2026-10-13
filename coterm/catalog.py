"""Verkada license catalog.

Definitions of every license SKU / license unit extracted from Verkada's
official US MSRP pricing sheet (standard, non-government tier, "new /
capacity increase" pricing only). Renewal pricing is intentionally out of
scope for this tool.

The actual pricing/description data lives in ``license_catalog.json`` next
to this module, so updating a price is a data edit rather than a code
change. This module just loads that file and exposes it as the same
dataclass-based API consumers already rely on.

The catalog is intentionally just data - all co-termination math lives in
``coterm.engine``. New license units can also be registered dynamically at
runtime via ``Organization.register_unit`` without touching this module.
"""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LicenseSku:
    sku: str
    label: str           # e.g. "1-Year Camera License, Capacity Increase"
    term_days: int        # 365, 1095, 1825, or 3650
    us_price: float
    kind: str             # "new" or "renewal"
    term_label: str = ""  # optional UI override, e.g. for retention-increment SKUs


@dataclass(frozen=True)
class LicenseUnitDef:
    key: str                     # stable id, e.g. "cam_camera"
    label: str                   # "Camera License"
    family: str                  # "Cameras"
    unit_basis: str              # human description
    devices_per_license: float = 1.0
    term_options_days: tuple = (365, 1095, 1825, 3650)
    skus: tuple = ()              # tuple of LicenseSku


_CATALOG_JSON_PATH = Path(__file__).parent / "license_catalog.json"


def _build_skus(key: str, terms: list) -> tuple:
    """Build a tuple of LicenseSku from the JSON unit's ``terms`` list."""
    out = []
    for term in terms:
        term_days = term["term_days"]
        years = term_days // 365
        out.append(
            LicenseSku(
                sku=f"{key}-{years}Y",
                label=f"{years}-Year License, Capacity Increase",
                term_days=term_days,
                us_price=term["us_price"],
                kind="new",
                term_label=term.get("term_label", ""),
            )
        )
    return tuple(out)


def _load_catalog(path: Path) -> tuple:
    """Load the catalog JSON and return (CATALOG dict, FAMILIES list)."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    families = list(data["families"])
    catalog: dict[str, LicenseUnitDef] = {}
    for unit in data["units"]:
        term_options_days = tuple(term["term_days"] for term in unit["terms"])
        unit_def = LicenseUnitDef(
            key=unit["key"],
            label=unit["label"],
            family=unit["family"],
            unit_basis=unit["unit_basis"],
            devices_per_license=unit.get("devices_per_license", 1.0),
            term_options_days=term_options_days,
            skus=_build_skus(unit["key"], unit["terms"]),
        )
        catalog[unit_def.key] = unit_def

    return catalog, families


CATALOG, FAMILIES = _load_catalog(_CATALOG_JSON_PATH)
