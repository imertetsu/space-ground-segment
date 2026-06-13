"""Versioned processing configuration schema — FROZEN contract (Phase 2).

This module defines the processor configuration consumed by the Phase 2 cloud
screening and SST retrieval processors, and recorded in product provenance
(REQ-CFG-01 — configuration is versioned; REQ-CFG-02 — every output records the
config version used). Phase 3 (validation) and Phase 4 (operations) consume this
same schema, so the field set and semantics are frozen here.

Configuration is loaded from TOML via the stdlib :mod:`tomllib` (Python 3.11+).
Two configs ship under ``payload/config/``:

* ``default.toml`` — the REAL-DATA config, using a CITED simplified split-window
  (MCSST) coefficient set (see :data:`SstConfig.source`).
* ``fixture.toml`` — a clearly-labelled FIXTURE-ONLY synthetic config matching how
  the offline test fixtures were generated; used by the offline demo and tests.

This is the foundation ``config`` layer: it imports no other PDGS package.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SstConfig:
    """Simplified split-window SST coefficient set + valid range (FROZEN).

    The retrieval computes ``SST_K = a0 + a1*T11 + a2*(T11 - T12) + output_offset_k``
    where ``T11`` is the ~10.8 µm band (SLSTR S8) and ``T12`` the ~12 µm band
    (SLSTR S9). This is the **N2 nadir-only dual-channel split-window** SST type of
    the SLSTR SST ATBD (EUMETSAT), but with a SIMPLIFIED constant-coefficient form
    (the MCSST family — McClain/Pichel/Walton 1985) rather than the operational
    water-vapour-binned LUT coefficients. ``source`` cites the coefficient origin.

    ``output_offset_k`` converts a °C-domain coefficient set to Kelvin (MCSST is
    defined in °C → add 273.15); fixture coefficients are already in K → 0.0.

    Out-of-range pixels (SST outside ``[valid_min_k, valid_max_k]``) are FLAGGED,
    never clamped or discarded (REQ-PRO-05).
    """

    coefficient_set_id: str
    a0: float
    a1: float
    a2: float
    output_offset_k: float
    source: str
    valid_min_k: float
    valid_max_k: float


@dataclass(frozen=True)
class CloudScreeningConfig:
    """Threshold-based cloud-screening configuration (FROZEN).

    A deliberate SIMPLIFICATION (not an operational cloud mask). A pixel is screened
    as cloud when its S8 (~10.8 µm) brightness temperature is below
    ``bt_cloud_threshold_k`` (cold ⇒ likely cloud over warm sea) and, when
    ``use_l1_cloud_flag`` is set, also where the L1 ``cloud_flags`` bit-0 is set.
    """

    bt_cloud_threshold_k: float
    use_l1_cloud_flag: bool


@dataclass(frozen=True)
class ProcessingConfig:
    """Top-level versioned processing configuration (FROZEN).

    ``config_version`` is recorded in every derived product's provenance
    (REQ-CFG-01/02). Bundles the SST and cloud-screening sub-configs.
    """

    config_version: str
    sst: SstConfig
    cloud: CloudScreeningConfig


# --- Built-in fallback ------------------------------------------------------

# CITED simplified split-window (MCSST) coefficient set, NOAA-19 day-split, as
# published in the ENVI "Compute AVHRR Sea Surface Temperature" documentation
# (MCSST family — McClain/Pichel/Walton 1985). These are defined in °C, so we add
# 273.15 K via output_offset_k. The nadir view drops the MCSST sec(θ)-1 term.
# Applying AVHRR coefficients to SLSTR bands is a documented cross-sensor
# SIMPLIFICATION (see SLSTR SST ATBD, EUMETSAT, N2 nadir dual-channel type).
_DEFAULT_SST_SOURCE = (
    "Simplified split-window (MCSST family — McClain/Pichel/Walton 1985); "
    "NOAA-19 day-split coefficients per ENVI 'Compute AVHRR Sea Surface "
    "Temperature' documentation. SST type = N2 nadir-only dual-channel "
    "(11/12 µm) of the SLSTR SST ATBD (EUMETSAT). CROSS-SENSOR SIMPLIFICATION: "
    "AVHRR coefficients applied to SLSTR S8/S9; NOT operational SLSTR SST."
)


def default_config() -> ProcessingConfig:
    """Return the built-in fallback REAL-DATA processing configuration.

    Mirrors ``payload/config/default.toml`` so processing can run without an
    on-disk config file. Uses the CITED MCSST coefficient set (see module docs).
    """
    return ProcessingConfig(
        config_version="2.0.0",
        sst=SstConfig(
            coefficient_set_id="mcsst-noaa19-day-split",
            a0=-278.74596,
            a1=1.01922,
            a2=1.72270,
            output_offset_k=273.15,
            source=_DEFAULT_SST_SOURCE,
            valid_min_k=271.15,
            valid_max_k=310.0,
        ),
        cloud=CloudScreeningConfig(
            bt_cloud_threshold_k=270.0,
            use_l1_cloud_flag=True,
        ),
    )


class ConfigError(ValueError):
    """Raised when a TOML processing config is malformed or incomplete."""


def _require(table: dict[str, object], key: str, section: str) -> object:
    try:
        return table[key]
    except KeyError as exc:
        raise ConfigError(f"missing key {key!r} in [{section}] config section") from exc


def _as_float(value: object, key: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigError(f"config key {key!r} must be a number, got {type(value).__name__}")
    return float(value)


def _as_str(value: object, key: str) -> str:
    if not isinstance(value, str):
        raise ConfigError(f"config key {key!r} must be a string, got {type(value).__name__}")
    return value


def _as_bool(value: object, key: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"config key {key!r} must be a boolean, got {type(value).__name__}")
    return value


def _parse_sst(table: dict[str, object]) -> SstConfig:
    return SstConfig(
        coefficient_set_id=_as_str(
            _require(table, "coefficient_set_id", "sst"), "coefficient_set_id"
        ),
        a0=_as_float(_require(table, "a0", "sst"), "a0"),
        a1=_as_float(_require(table, "a1", "sst"), "a1"),
        a2=_as_float(_require(table, "a2", "sst"), "a2"),
        output_offset_k=_as_float(_require(table, "output_offset_k", "sst"), "output_offset_k"),
        source=_as_str(_require(table, "source", "sst"), "source"),
        valid_min_k=_as_float(_require(table, "valid_min_k", "sst"), "valid_min_k"),
        valid_max_k=_as_float(_require(table, "valid_max_k", "sst"), "valid_max_k"),
    )


def _parse_cloud(table: dict[str, object]) -> CloudScreeningConfig:
    return CloudScreeningConfig(
        bt_cloud_threshold_k=_as_float(
            _require(table, "bt_cloud_threshold_k", "cloud"), "bt_cloud_threshold_k"
        ),
        use_l1_cloud_flag=_as_bool(
            _require(table, "use_l1_cloud_flag", "cloud"), "use_l1_cloud_flag"
        ),
    )


def load_config(path: str | Path) -> ProcessingConfig:
    """Load a :class:`ProcessingConfig` from a TOML file (REQ-CFG-01).

    The file must define a top-level ``config_version`` plus ``[sst]`` and
    ``[cloud]`` tables matching :class:`SstConfig` / :class:`CloudScreeningConfig`.
    Raises :class:`ConfigError` on a missing/ill-typed key and
    :class:`FileNotFoundError` if ``path`` does not exist.
    """
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"processing config not found: {config_path}")
    with config_path.open("rb") as fh:
        raw: dict[str, object] = tomllib.load(fh)

    config_version = _as_str(_require(raw, "config_version", "root"), "config_version")

    sst_raw = _require(raw, "sst", "root")
    if not isinstance(sst_raw, dict):
        raise ConfigError("config section [sst] must be a table")
    cloud_raw = _require(raw, "cloud", "root")
    if not isinstance(cloud_raw, dict):
        raise ConfigError("config section [cloud] must be a table")

    return ProcessingConfig(
        config_version=config_version,
        sst=_parse_sst(sst_raw),
        cloud=_parse_cloud(cloud_raw),
    )
