"""Per-parameter spacecraft dynamics (deterministic given a seed).

SIMULATED telemetry. Produces realistic raw-count HK values per tick: each
continuous parameter drifts slowly and carries bounded gaussian noise around its
configured nominal; behaviour is mode-dependent (the reaction wheel spins faster
in PAYLOAD, the battery slowly drains). Anomaly injection (:mod:`sgs_sim.anomalies`)
is layered on top of this baseline.

Determinism: all randomness comes from a single :class:`random.Random` seeded
from the config — **no wall-clock randomness in the model**. Same seed + same
config + same anomaly toggles => identical raw-value sequences.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from sgs_sim.config import ParameterConfig, SimConfig
from sgs_sim.hk import HkParameters, SpacecraftMode

# Parameter names (must match the keys in config ``[parameters]``).
P_BATTERY_VOLTAGE = "battery_voltage"
P_BATTERY_CURRENT = "battery_current"
P_OBC_TEMP = "obc_temp"
P_BATTERY_TEMP = "battery_temp"
P_RW_SPEED = "reaction_wheel_speed"

#: Extra reaction-wheel speed (raw RPM) added while in PAYLOAD mode.
PAYLOAD_RW_BOOST = 1500.0

#: Slow battery drain (raw mV/tick) — battery voltage trends down over a run.
BATTERY_DRAIN_PER_TICK = 0.5

#: Extra battery current (raw mA) drawn while in PAYLOAD mode.
PAYLOAD_CURRENT_BOOST = 800.0


@dataclass
class _Channel:
    """Mutable running state for one continuous parameter."""

    cfg: ParameterConfig
    value: float

    def step(self, rng: random.Random, drift_bias: float = 0.0) -> float:
        """Advance one tick: apply drift + noise; return the new continuous value.

        ``drift_bias`` is an extra additive drift this tick (e.g. anomaly push or
        mode-dependent trend). The value is NOT clamped here — callers clamp at
        encode time so the underlying trajectory can keep moving past a limit.
        """
        self.value += self.cfg.drift + drift_bias + rng.gauss(0.0, self.cfg.noise)
        return self.value


class Dynamics:
    """Stateful, deterministic dynamics model for the HK parameter set."""

    def __init__(self, config: SimConfig) -> None:
        self._config = config
        self._rng = random.Random(config.seed)
        self._tick = 0
        self.mode: SpacecraftMode = SpacecraftMode.NOMINAL

        def chan(name: str) -> _Channel:
            cfg = config.parameters[name]
            return _Channel(cfg=cfg, value=cfg.nominal)

        self._voltage = chan(P_BATTERY_VOLTAGE)
        self._current = chan(P_BATTERY_CURRENT)
        self._obc_temp = chan(P_OBC_TEMP)
        self._battery_temp = chan(P_BATTERY_TEMP)
        self._rw_speed = chan(P_RW_SPEED)

    @property
    def rng(self) -> random.Random:
        """The single seeded RNG (shared with anomaly injection for determinism)."""
        return self._rng

    @property
    def tick(self) -> int:
        """Number of completed ticks."""
        return self._tick

    def set_mode(self, mode: SpacecraftMode) -> None:
        """Set the current spacecraft mode (affects mode-dependent dynamics)."""
        self.mode = mode

    def step(
        self,
        *,
        voltage_bias: float = 0.0,
        obc_temp_bias: float = 0.0,
        rw_speed_bias: float = 0.0,
    ) -> HkParameters:
        """Advance the model one tick and return clamped raw HK parameters.

        The ``*_bias`` arguments are anomaly pushes (raw counts/tick) injected by
        :mod:`sgs_sim.anomalies`. Mode-dependent trends are applied here.
        """
        payload = self.mode == SpacecraftMode.PAYLOAD

        # Battery slowly drains every tick (mode-independent baseline trend).
        voltage = self._voltage.step(self._rng, drift_bias=-BATTERY_DRAIN_PER_TICK + voltage_bias)
        # Continuous channels drift + noise around their nominal; PAYLOAD adds an
        # offset on top (more current drawn, reaction wheel spun up faster).
        current = self._current.step(self._rng) + (PAYLOAD_CURRENT_BOOST if payload else 0.0)
        obc_temp = self._obc_temp.step(self._rng, drift_bias=obc_temp_bias)
        battery_temp = self._battery_temp.step(self._rng)
        rw_speed = self._rw_speed.step(self._rng, drift_bias=rw_speed_bias) + (
            PAYLOAD_RW_BOOST if payload else 0.0
        )

        self._tick += 1

        return HkParameters(
            battery_voltage=self._voltage.cfg.clamp_raw(voltage),
            battery_current=self._current.cfg.clamp_raw(current),
            obc_temp=self._obc_temp.cfg.clamp_raw(obc_temp),
            battery_temp=self._battery_temp.cfg.clamp_raw(battery_temp),
            reaction_wheel_speed=self._rw_speed.cfg.clamp_raw(rw_speed),
            spacecraft_mode=self.mode,
        )
