"""Shared pytest fixtures for the SIMULATED simulator tests."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable

import pytest

from sgs_sim import config
from sgs_sim.config import AnomalyConfig, SimConfig


@pytest.fixture
def default_config() -> SimConfig:
    """The shipped default config (all anomalies off)."""
    return config.load(config.default_config_path())


@pytest.fixture
def with_anomaly() -> Callable[..., SimConfig]:
    """Factory: return a copy of a config with anomaly scenarios replaced.

    Usage: ``cfg = with_anomaly(base, obc_overtemp=AnomalyConfig(enabled=True, rate=200))``.
    """

    def _make(cfg: SimConfig, **scenarios: AnomalyConfig) -> SimConfig:
        anomalies = dataclasses.replace(cfg.anomalies, **scenarios)
        return dataclasses.replace(cfg, anomalies=anomalies)

    return _make
