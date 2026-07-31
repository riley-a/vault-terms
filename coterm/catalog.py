"""Verkada license catalog.

Static definitions of every license SKU / license unit extracted from
Verkada's official US MSRP pricing sheet (standard, non-government tier,
"new / capacity increase" pricing only). Renewal pricing is intentionally
out of scope for this tool.

The catalog is intentionally just data - all co-termination math lives in
``coterm.engine``. New license units can also be registered dynamically at
runtime via ``Organization.register_unit`` without touching this module.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LicenseSku:
    sku: str
    label: str          # e.g. "1-Year Camera License, Capacity Increase"
    term_days: int       # 365, 1095, 1825, or 3650
    us_price: float
    kind: str            # "new" or "renewal"


@dataclass(frozen=True)
class LicenseUnitDef:
    key: str                     # stable id, e.g. "cam_camera"
    label: str                   # "Camera License"
    family: str                  # "Cameras"
    unit_basis: str              # human description
    devices_per_license: float = 1.0
    term_options_days: tuple = (365, 1095, 1825, 3650)
    skus: tuple = ()              # tuple of LicenseSku


def _skus(key: str, term_days_list, prices) -> tuple:
    """Build a tuple of LicenseSku for the given (term_days, price) pairs."""
    out = []
    for term_days, price in zip(term_days_list, prices):
        years = term_days // 365
        out.append(
            LicenseSku(
                sku=f"{key}-{years}Y",
                label=f"{years}-Year License, Capacity Increase",
                term_days=term_days,
                us_price=price,
                kind="new",
            )
        )
    return tuple(out)


_STANDARD_TERMS = (365, 1095, 1825, 3650)

CATALOG: dict[str, LicenseUnitDef] = {}
FAMILIES: list[str] = [
    "Cameras",
    "Access Control",
    "Alarms",
    "Environmental Sensors",
    "Gateway",
    "Intercom",
    "Workplace",
]


def _register(unit_def: LicenseUnitDef) -> None:
    CATALOG[unit_def.key] = unit_def


# ---------------------------------------------------------------------------
# Cameras
# ---------------------------------------------------------------------------

_register(
    LicenseUnitDef(
        key="cam_camera",
        label="Camera License",
        family="Cameras",
        unit_basis=(
            "One license per Verkada camera, or per non-Verkada "
            "camera/channel connected via Command Connector"
        ),
        devices_per_license=1,
        term_options_days=_STANDARD_TERMS,
        skus=_skus("cam_camera", _STANDARD_TERMS, (249, 659, 1099, 2199)),
    )
)

_register(
    LicenseUnitDef(
        key="cam_multisensor_2",
        label="Two-Camera Multisensor License (MLT2)",
        family="Cameras",
        unit_basis="One license per two-camera multisensor unit",
        devices_per_license=1,
        term_options_days=_STANDARD_TERMS,
        skus=_skus("cam_multisensor_2", _STANDARD_TERMS, (419, 1199, 1999, 3999)),
    )
)

_register(
    LicenseUnitDef(
        key="cam_multisensor_4",
        label="Four-Camera Multisensor License (MLT4)",
        family="Cameras",
        unit_basis="One license per four-camera multisensor unit",
        devices_per_license=1,
        term_options_days=_STANDARD_TERMS,
        skus=_skus("cam_multisensor_4", _STANDARD_TERMS, (699, 1949, 3249, 6499)),
    )
)

_register(
    LicenseUnitDef(
        key="cam_cloud_backup",
        label="Extended Cloud Backup License (30-day increment)",
        family="Cameras",
        unit_basis=(
            "One license per 30-day increment of a single device's cloud "
            "retention"
        ),
        devices_per_license=1,
        term_options_days=_STANDARD_TERMS,
        skus=_skus("cam_cloud_backup", _STANDARD_TERMS, (149, 449, 749, 1499)),
    )
)

_register(
    LicenseUnitDef(
        key="cam_viewing_station",
        label="Viewing Station License",
        family="Cameras",
        unit_basis="One license per viewing station",
        devices_per_license=1,
        term_options_days=(365, 1095, 1825, 3650),
        skus=_skus("cam_viewing_station", (365, 1095, 1825, 3650), (549, 1499, 2499, 4999)),
    )
)

# ---------------------------------------------------------------------------
# Access Control
# ---------------------------------------------------------------------------

_register(
    LicenseUnitDef(
        key="ac_door",
        label="Door License",
        family="Access Control",
        unit_basis="One license per door (AC62, AC42, AC41, AC12)",
        devices_per_license=1,
        term_options_days=_STANDARD_TERMS,
        skus=_skus("ac_door", _STANDARD_TERMS, (249, 599, 999, 1999)),
    )
)

_register(
    LicenseUnitDef(
        key="ac_io_controller",
        label="AX11 IO Controller License",
        family="Access Control",
        unit_basis="One license per AX11 access IO controller",
        devices_per_license=1,
        term_options_days=_STANDARD_TERMS,
        skus=_skus("ac_io_controller", _STANDARD_TERMS, (999, 2599, 3999, 7999)),
    )
)

_register(
    LicenseUnitDef(
        key="ac_mobile_nfc",
        label="Mobile NFC License (20-user pack)",
        family="Access Control",
        unit_basis="One license per 20 mobile NFC credential users",
        devices_per_license=20,
        term_options_days=_STANDARD_TERMS,
        skus=_skus("ac_mobile_nfc", _STANDARD_TERMS, (199, 599, 999, 1999)),
    )
)

# ---------------------------------------------------------------------------
# Alarms
# ---------------------------------------------------------------------------

_register(
    LicenseUnitDef(
        key="alarm_basic_site",
        label="Basic Alarms Site License",
        family="Alarms",
        unit_basis=(
            "One license per physical site/location; unlimited sensors, "
            "no video verification"
        ),
        devices_per_license=1,
        term_options_days=_STANDARD_TERMS,
        skus=_skus("alarm_basic_site", _STANDARD_TERMS, (600, 1800, 3000, 6000)),
    )
)

_register(
    LicenseUnitDef(
        key="alarm_advanced_site",
        label="Advanced Video Alarms Site License",
        family="Alarms",
        unit_basis=(
            "One license per physical site/location; video verification, "
            "covers 15 alarm-triggering cameras per site (stackable in "
            "packs of 15)"
        ),
        devices_per_license=1,
        term_options_days=_STANDARD_TERMS,
        skus=_skus("alarm_advanced_site", _STANDARD_TERMS, (1500, 4500, 7500, 15000)),
    )
)

_register(
    LicenseUnitDef(
        key="alarm_horn_speaker",
        label="BZ11 Horn Speaker License",
        family="Alarms",
        unit_basis="One license per BZ11 horn speaker device",
        devices_per_license=1,
        term_options_days=_STANDARD_TERMS,
        skus=_skus("alarm_horn_speaker", _STANDARD_TERMS, (199, 549, 899, 1799)),
    )
)

_register(
    LicenseUnitDef(
        key="alarm_cellular_backup",
        label="Cellular Backup License",
        family="Alarms",
        unit_basis="One license per cellular backup communicator module",
        devices_per_license=1,
        term_options_days=_STANDARD_TERMS,
        skus=_skus("alarm_cellular_backup", _STANDARD_TERMS, (299, 849, 1349, 2699)),
    )
)

# ---------------------------------------------------------------------------
# Environmental Sensors
# ---------------------------------------------------------------------------

_register(
    LicenseUnitDef(
        key="env_sensor",
        label="Environmental Sensor License (SV)",
        family="Environmental Sensors",
        unit_basis="One license per environmental sensor",
        devices_per_license=1,
        term_options_days=_STANDARD_TERMS,
        skus=_skus("env_sensor", _STANDARD_TERMS, (249, 599, 999, 1999)),
    )
)

# ---------------------------------------------------------------------------
# Gateway
# ---------------------------------------------------------------------------

_register(
    LicenseUnitDef(
        key="gw_cellular",
        label="Cellular Gateway License",
        family="Gateway",
        unit_basis="One license per cellular gateway",
        devices_per_license=1,
        term_options_days=_STANDARD_TERMS,
        skus=_skus("gw_cellular", _STANDARD_TERMS, (349, 999, 1599, 3199)),
    )
)

_register(
    LicenseUnitDef(
        key="gw_wifi",
        label="Wi-Fi Gateway License",
        family="Gateway",
        unit_basis="One license per Wi-Fi gateway",
        devices_per_license=1,
        term_options_days=_STANDARD_TERMS,
        skus=_skus("gw_wifi", _STANDARD_TERMS, (99, 279, 449, 899)),
    )
)

_register(
    LicenseUnitDef(
        key="gw_data_plan",
        label="Cellular Gateway Data Plan",
        family="Gateway",
        unit_basis=(
            "One license per connected camera/intercom video device (a "
            "two-cam multisensor needs 2, a four-cam multisensor needs 4)"
        ),
        devices_per_license=1,
        term_options_days=(365, 1095, 1825),
        skus=_skus("gw_data_plan", (365, 1095, 1825), (599, 1799, 2999)),
    )
)

# ---------------------------------------------------------------------------
# Intercom
# ---------------------------------------------------------------------------

_register(
    LicenseUnitDef(
        key="intercom_device",
        label="Intercom License",
        family="Intercom",
        unit_basis="One license per intercom device",
        devices_per_license=1,
        term_options_days=_STANDARD_TERMS,
        skus=_skus("intercom_device", _STANDARD_TERMS, (399, 1199, 1999, 3999)),
    )
)

_register(
    LicenseUnitDef(
        key="intercom_desk_station",
        label="Desk Station License",
        family="Intercom",
        unit_basis=(
            "One license per iPad running the Verkada Desk Station app"
        ),
        devices_per_license=1,
        term_options_days=_STANDARD_TERMS,
        skus=_skus("intercom_desk_station", _STANDARD_TERMS, (249, 749, 1249, 2499)),
    )
)

# ---------------------------------------------------------------------------
# Workplace
# ---------------------------------------------------------------------------

_register(
    LicenseUnitDef(
        key="workplace",
        label="Workplace License",
        family="Workplace",
        unit_basis=(
            "One license grants access to one Guest iPad and one Mailroom "
            "site"
        ),
        devices_per_license=1,
        term_options_days=_STANDARD_TERMS,
        skus=_skus("workplace", _STANDARD_TERMS, (3600, 10800, 18000, 36000)),
    )
)
