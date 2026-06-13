"""Configurable anomaly injection + per-tick model orchestration.

SIMULATED telemetry. Implements the four configurable anomaly scenarios
(REQ-SIM-04) and ties the dynamics model (:mod:`sgs_sim.dynamics`), anomaly
pushes, and event detection (:mod:`sgs_sim.events`) together into a single
deterministic per-tick step.

Scenarios (each on/off + a per-tick magnitude/rate, from config):

    battery_undervoltage  pushes battery_voltage down past its hard_min
    obc_overtemp          pushes obc_temp up past its hard_max
    rw_overspeed          pushes reaction_wheel_speed up past its hard_max
    mode_to_safe          forces spacecraft_mode -> SAFE

When a scenario is active its push is applied as a per-tick bias, so the raw
value crosses its soft limit and then its hard limit within a few ticks. Crossing
a soft limit (or a mode change) emits the corresponding PUS-5 event exactly once
per crossing (re-armed when the value returns inside the soft band).
"""

from __future__ import annotations

from dataclasses import dataclass

from sgs_sim import dynamics as dyn
from sgs_sim.config import SimConfig
from sgs_sim.dynamics import Dynamics
from sgs_sim.events import Event, EventId
from sgs_sim.hk import HkParameters, SpacecraftMode


@dataclass
class TickResult:
    """The output of one model tick: the HK parameters + any events to emit."""

    params: HkParameters
    events: list[Event]


class Model:
    """Deterministic spacecraft model: dynamics + anomalies + event detection.

    Same config (incl. seed) + same tick count => identical output sequence.
    """

    def __init__(self, config: SimConfig) -> None:
        self._config = config
        self._dyn = Dynamics(config)
        # Latches so each soft-limit crossing emits its event only once until the
        # value returns inside the soft band (edge-triggered, not level).
        self._undervoltage_armed = True
        self._overtemp_armed = True
        self._overspeed_armed = True
        self._prev_mode: SpacecraftMode = self._dyn.mode

    @property
    def dynamics(self) -> Dynamics:
        """The underlying (deterministic) dynamics model."""
        return self._dyn

    def step(self) -> TickResult:
        """Advance the model one tick; return HK params + triggered events."""
        anomalies = self._config.anomalies

        # mode_to_safe: force SAFE mode while active (applied before dynamics so
        # mode-dependent dynamics reflect it this tick).
        if anomalies.mode_to_safe.enabled:
            self._dyn.set_mode(SpacecraftMode.SAFE)

        # Anomaly pushes (raw counts/tick) applied as biases into the dynamics.
        voltage_bias = (
            -anomalies.battery_undervoltage.rate if anomalies.battery_undervoltage.enabled else 0.0
        )
        obc_temp_bias = anomalies.obc_overtemp.rate if anomalies.obc_overtemp.enabled else 0.0
        rw_speed_bias = anomalies.rw_overspeed.rate if anomalies.rw_overspeed.enabled else 0.0

        params = self._dyn.step(
            voltage_bias=voltage_bias,
            obc_temp_bias=obc_temp_bias,
            rw_speed_bias=rw_speed_bias,
        )

        events = self._detect_events(params)
        return TickResult(params=params, events=events)

    def _detect_events(self, params: HkParameters) -> list[Event]:
        """Edge-triggered event detection on soft-limit crossings + mode change."""
        events: list[Event] = []
        cfg = self._config.parameters

        # Battery under-voltage (soft_min crossing on battery_voltage).
        v_cfg = cfg[dyn.P_BATTERY_VOLTAGE]
        if params.battery_voltage < v_cfg.soft_min:
            if self._undervoltage_armed:
                events.append(Event(EventId.BATTERY_UNDERVOLTAGE, context=params.battery_voltage))
                self._undervoltage_armed = False
        else:
            self._undervoltage_armed = True

        # OBC over-temperature (soft_max crossing on obc_temp).
        t_cfg = cfg[dyn.P_OBC_TEMP]
        if params.obc_temp > t_cfg.soft_max:
            if self._overtemp_armed:
                events.append(Event(EventId.OBC_OVERTEMP, context=params.obc_temp))
                self._overtemp_armed = False
        else:
            self._overtemp_armed = True

        # Reaction-wheel over-speed (soft_max crossing on reaction_wheel_speed).
        rw_cfg = cfg[dyn.P_RW_SPEED]
        if params.reaction_wheel_speed > rw_cfg.soft_max:
            if self._overspeed_armed:
                events.append(Event(EventId.RW_OVERSPEED, context=params.reaction_wheel_speed))
                self._overspeed_armed = False
        else:
            self._overspeed_armed = True

        # Mode change (and the dedicated entered-SAFE event).
        if params.spacecraft_mode != self._prev_mode:
            events.append(Event(EventId.MODE_CHANGE, context=int(params.spacecraft_mode)))
            if params.spacecraft_mode == SpacecraftMode.SAFE:
                events.append(Event(EventId.MODE_SAFE, context=0))
            self._prev_mode = params.spacecraft_mode

        return events
