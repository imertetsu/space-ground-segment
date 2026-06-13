"""Configuration model + TOML loader (stdlib ``tomllib``).

SIMULATED telemetry. Loads simulator configuration from a TOML file: UDP target,
emit rate, per-parameter nominal + soft/hard limits + encoding, anomaly toggles +
magnitudes, and the RNG seed. The shipped defaults live in
``control/simulator/config/default.toml``.

Runtime is stdlib only — no third-party config library.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

# --- Defaults ---------------------------------------------------------------

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 10015
"""Yamcs UdpTmDataLink default port (1 datagram = 1 packet)."""

DEFAULT_TC_HOST = "127.0.0.1"
"""Bind host for the TC receiver (where Yamcs' udp-out sends TCs)."""

DEFAULT_TC_PORT = 10025
"""Yamcs UdpTcDataLink default port — the simulator binds here to receive TCs."""

DEFAULT_RATE_HZ = 1.0
DEFAULT_SEED = 42


@dataclass(frozen=True)
class ParameterConfig:
    """Per-parameter dynamics + limit configuration (all in raw counts)."""

    nominal: float
    """Nominal raw value the dynamics drift around."""

    noise: float
    """Std-dev (raw counts) of the bounded gaussian noise per tick."""

    drift: float
    """Slow per-tick drift (raw counts/tick); sign gives direction."""

    soft_min: int
    soft_max: int
    hard_min: int
    hard_max: int

    def clamp_raw(self, value: float) -> int:
        """Clamp ``value`` to the hard limits and round to an int raw count."""
        v = round(value)
        if v < self.hard_min:
            return self.hard_min
        if v > self.hard_max:
            return self.hard_max
        return v


@dataclass(frozen=True)
class AnomalyConfig:
    """One anomaly scenario: on/off + a magnitude/rate (raw counts/tick)."""

    enabled: bool = False
    rate: float = 0.0
    """Per-tick push (raw counts) toward/past the limit while active."""


@dataclass(frozen=True)
class AnomaliesConfig:
    """The four configurable anomaly scenarios (REQ-SIM-04)."""

    battery_undervoltage: AnomalyConfig = field(default_factory=AnomalyConfig)
    obc_overtemp: AnomalyConfig = field(default_factory=AnomalyConfig)
    rw_overspeed: AnomalyConfig = field(default_factory=AnomalyConfig)
    mode_to_safe: AnomalyConfig = field(default_factory=AnomalyConfig)


@dataclass(frozen=True)
class SimConfig:
    """Top-level simulator configuration."""

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    tc_host: str = DEFAULT_TC_HOST
    tc_port: int = DEFAULT_TC_PORT
    rate_hz: float = DEFAULT_RATE_HZ
    seed: int = DEFAULT_SEED
    parameters: dict[str, ParameterConfig] = field(default_factory=dict)
    anomalies: AnomaliesConfig = field(default_factory=AnomaliesConfig)

    def with_overrides(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        tc_host: str | None = None,
        tc_port: int | None = None,
        rate_hz: float | None = None,
        seed: int | None = None,
    ) -> SimConfig:
        """Return a copy with CLI overrides applied (None = keep existing)."""
        return replace(
            self,
            host=self.host if host is None else host,
            port=self.port if port is None else port,
            tc_host=self.tc_host if tc_host is None else tc_host,
            tc_port=self.tc_port if tc_port is None else tc_port,
            rate_hz=self.rate_hz if rate_hz is None else rate_hz,
            seed=self.seed if seed is None else seed,
        )


# Required keys for a parameter table (so a typo surfaces, not a silent default).
_PARAM_KEYS = ("nominal", "noise", "drift", "soft_min", "soft_max", "hard_min", "hard_max")


def _parse_parameter(name: str, table: dict[str, Any]) -> ParameterConfig:
    missing = [k for k in _PARAM_KEYS if k not in table]
    if missing:
        raise ValueError(f"parameter '{name}' missing keys: {missing}")
    return ParameterConfig(
        nominal=float(table["nominal"]),
        noise=float(table["noise"]),
        drift=float(table["drift"]),
        soft_min=int(table["soft_min"]),
        soft_max=int(table["soft_max"]),
        hard_min=int(table["hard_min"]),
        hard_max=int(table["hard_max"]),
    )


def _parse_anomaly(table: dict[str, Any] | None) -> AnomalyConfig:
    if table is None:
        return AnomalyConfig()
    return AnomalyConfig(
        enabled=bool(table.get("enabled", False)),
        rate=float(table.get("rate", 0.0)),
    )


def from_dict(raw: dict[str, Any]) -> SimConfig:
    """Build a :class:`SimConfig` from a parsed-TOML dict."""
    udp = raw.get("udp", {})
    sim = raw.get("sim", {})

    params_raw = raw.get("parameters", {})
    parameters = {name: _parse_parameter(name, tbl) for name, tbl in params_raw.items()}

    anomalies_raw = raw.get("anomalies", {})
    anomalies = AnomaliesConfig(
        battery_undervoltage=_parse_anomaly(anomalies_raw.get("battery_undervoltage")),
        obc_overtemp=_parse_anomaly(anomalies_raw.get("obc_overtemp")),
        rw_overspeed=_parse_anomaly(anomalies_raw.get("rw_overspeed")),
        mode_to_safe=_parse_anomaly(anomalies_raw.get("mode_to_safe")),
    )

    tc = raw.get("tc", {})

    return SimConfig(
        host=str(udp.get("host", DEFAULT_HOST)),
        port=int(udp.get("port", DEFAULT_PORT)),
        tc_host=str(tc.get("host", DEFAULT_TC_HOST)),
        tc_port=int(tc.get("port", DEFAULT_TC_PORT)),
        rate_hz=float(sim.get("rate_hz", DEFAULT_RATE_HZ)),
        seed=int(sim.get("seed", DEFAULT_SEED)),
        parameters=parameters,
        anomalies=anomalies,
    )


def load(path: str | Path) -> SimConfig:
    """Load + parse a TOML config file into a :class:`SimConfig`.

    Raises:
        FileNotFoundError: if ``path`` does not exist.
        tomllib.TOMLDecodeError: on malformed TOML.
        ValueError: on a missing required parameter key.
    """
    p = Path(path)
    with p.open("rb") as fh:
        raw = tomllib.load(fh)
    return from_dict(raw)


def default_config_path() -> Path:
    """Return the path to the shipped ``config/default.toml``.

    ``config.py`` is ``control/simulator/src/sgs_sim/config.py``; the config file
    is ``control/simulator/config/default.toml`` (``parents[2]`` = simulator/).
    """
    return Path(__file__).resolve().parents[2] / "config" / "default.toml"
