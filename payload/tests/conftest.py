"""Shared pytest fixtures for the PDGS test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

# tests/ -> payload/ ; fixtures live at payload/fixtures.
_FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """Path to the committed synthetic fixtures directory."""
    assert _FIXTURES_ROOT.is_dir(), f"fixtures dir missing: {_FIXTURES_ROOT}"
    return _FIXTURES_ROOT


@pytest.fixture(scope="session")
def l1_safe_dir(fixtures_dir: Path) -> Path:
    """Path to the synthetic SL_1_RBT SAFE folder."""
    return fixtures_dir / "l1_rbt_synthetic"


@pytest.fixture(scope="session")
def l2_safe_dir(fixtures_dir: Path) -> Path:
    """Path to the synthetic SL_2_WST SAFE folder."""
    return fixtures_dir / "l2_wst_synthetic"
