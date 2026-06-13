"""Tests for the deterministic dynamics model."""

from __future__ import annotations

import dataclasses

from sgs_sim.config import SimConfig
from sgs_sim.dynamics import Dynamics
from sgs_sim.hk import HkParameters, SpacecraftMode


def _run(config: SimConfig, ticks: int) -> list[HkParameters]:
    dyn = Dynamics(config)
    return [dyn.step() for _ in range(ticks)]


def test_same_seed_identical_sequences(default_config: SimConfig) -> None:
    seq_a = _run(default_config, 50)
    seq_b = _run(default_config, 50)
    assert seq_a == seq_b


def test_different_seed_diverges(default_config: SimConfig) -> None:
    other = dataclasses.replace(default_config, seed=default_config.seed + 1)
    seq_a = _run(default_config, 50)
    seq_b = _run(other, 50)
    assert seq_a != seq_b


def test_values_stay_near_nominal_without_anomalies(default_config: SimConfig) -> None:
    seq = _run(default_config, 100)
    cfg = default_config.parameters
    for params in seq:
        # Battery drains slowly, so only check it does not blow through soft_min
        # over 100 ticks (drain is ~0.5/tick → ~50 counts).
        assert cfg["obc_temp"].soft_min <= params.obc_temp <= cfg["obc_temp"].soft_max
        assert cfg["battery_temp"].soft_min <= params.battery_temp <= cfg["battery_temp"].soft_max
        assert (
            cfg["reaction_wheel_speed"].soft_min
            <= params.reaction_wheel_speed
            <= cfg["reaction_wheel_speed"].soft_max
        )
        # voltage stays within hard limits and well above soft_min over 100 ticks.
        assert (
            cfg["battery_voltage"].hard_min
            <= params.battery_voltage
            <= cfg["battery_voltage"].hard_max
        )
        assert params.battery_voltage > cfg["battery_voltage"].soft_min


def test_payload_mode_spins_reaction_wheel_faster(default_config: SimConfig) -> None:
    nominal = Dynamics(default_config)
    nominal.set_mode(SpacecraftMode.NOMINAL)
    nominal_speed = nominal.step().reaction_wheel_speed

    payload = Dynamics(default_config)
    payload.set_mode(SpacecraftMode.PAYLOAD)
    payload_speed = payload.step().reaction_wheel_speed

    # Same seed/tick → only the PAYLOAD boost differs.
    assert payload_speed > nominal_speed


def test_battery_drains_over_time(default_config: SimConfig) -> None:
    seq = _run(default_config, 200)
    # Average of the first 10 vs the last 10 ticks should trend downward.
    early = sum(p.battery_voltage for p in seq[:10]) / 10
    late = sum(p.battery_voltage for p in seq[-10:]) / 10
    assert late < early
