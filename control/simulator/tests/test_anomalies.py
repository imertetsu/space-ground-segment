"""Tests for configurable anomaly injection (REQ-SIM-04)."""

from __future__ import annotations

from collections.abc import Callable

from sgs_sim.anomalies import Model
from sgs_sim.config import AnomalyConfig, SimConfig
from sgs_sim.hk import SpacecraftMode

MAX_TICKS = 50

WithAnomaly = Callable[..., SimConfig]


def test_battery_undervoltage_drives_past_hard_min(
    default_config: SimConfig, with_anomaly: WithAnomaly
) -> None:
    cfg = with_anomaly(default_config, battery_undervoltage=AnomalyConfig(enabled=True, rate=80))
    hard_min = default_config.parameters["battery_voltage"].hard_min
    model = Model(cfg)
    crossed = False
    for _ in range(MAX_TICKS):
        params = model.step().params
        if params.battery_voltage <= hard_min:
            crossed = True
            break
    assert crossed, "battery_voltage never reached hard_min"


def test_obc_overtemp_drives_past_hard_max(
    default_config: SimConfig, with_anomaly: WithAnomaly
) -> None:
    cfg = with_anomaly(default_config, obc_overtemp=AnomalyConfig(enabled=True, rate=200))
    hard_max = default_config.parameters["obc_temp"].hard_max
    model = Model(cfg)
    crossed = any(model.step().params.obc_temp >= hard_max for _ in range(MAX_TICKS))
    assert crossed, "obc_temp never reached hard_max"


def test_rw_overspeed_drives_past_hard_max(
    default_config: SimConfig, with_anomaly: WithAnomaly
) -> None:
    cfg = with_anomaly(default_config, rw_overspeed=AnomalyConfig(enabled=True, rate=250))
    hard_max = default_config.parameters["reaction_wheel_speed"].hard_max
    model = Model(cfg)
    crossed = any(model.step().params.reaction_wheel_speed >= hard_max for _ in range(MAX_TICKS))
    assert crossed, "reaction_wheel_speed never reached hard_max"


def test_mode_to_safe_forces_safe(default_config: SimConfig, with_anomaly: WithAnomaly) -> None:
    cfg = with_anomaly(default_config, mode_to_safe=AnomalyConfig(enabled=True, rate=0))
    model = Model(cfg)
    params = model.step().params
    assert params.spacecraft_mode == SpacecraftMode.SAFE


def test_no_anomaly_stays_within_hard_limits(default_config: SimConfig) -> None:
    model = Model(default_config)
    cfg = default_config.parameters
    for _ in range(MAX_TICKS):
        params = model.step().params
        assert (
            cfg["battery_voltage"].hard_min
            <= params.battery_voltage
            <= cfg["battery_voltage"].hard_max
        )
        assert cfg["obc_temp"].hard_min <= params.obc_temp <= cfg["obc_temp"].hard_max
        assert (
            cfg["reaction_wheel_speed"].hard_min
            <= params.reaction_wheel_speed
            <= cfg["reaction_wheel_speed"].hard_max
        )
