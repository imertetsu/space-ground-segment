"""Unit tests for the versioned processing config schema (REQ-CFG-01/02)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pdgs.config.processing import (
    ConfigError,
    ProcessingConfig,
    default_config,
    load_config,
)

# config/ lives at payload/config; tests/ -> payload/.
_CONFIG_ROOT = Path(__file__).resolve().parents[2] / "config"


def test_load_default_toml_exposes_config_version() -> None:
    cfg = load_config(_CONFIG_ROOT / "default.toml")
    assert isinstance(cfg, ProcessingConfig)
    assert cfg.config_version
    # CITED MCSST coefficient set (real-data config).
    assert cfg.sst.coefficient_set_id == "mcsst-noaa19-day-split"
    assert cfg.sst.a0 == pytest.approx(-278.74596)
    assert cfg.sst.a1 == pytest.approx(1.01922)
    assert cfg.sst.a2 == pytest.approx(1.72270)
    assert cfg.sst.output_offset_k == pytest.approx(273.15)
    assert cfg.sst.valid_min_k < cfg.sst.valid_max_k
    # The source string cites the coefficient origin and the simplification.
    assert "MCSST" in cfg.sst.source
    assert "SIMPLIFICATION" in cfg.sst.source.upper()


def test_load_fixture_toml_uses_synthetic_coefficients() -> None:
    cfg = load_config(_CONFIG_ROOT / "fixture.toml")
    assert cfg.config_version
    # FIXTURE-ONLY synthetic coefficients matching how the fixtures were generated.
    assert cfg.sst.a0 == pytest.approx(1.0)
    assert cfg.sst.a1 == pytest.approx(1.0)
    assert cfg.sst.a2 == pytest.approx(2.0)
    assert cfg.sst.output_offset_k == pytest.approx(0.0)
    assert "SYNTHETIC" in cfg.sst.source.upper()


def test_default_config_matches_default_toml() -> None:
    builtin = default_config()
    on_disk = load_config(_CONFIG_ROOT / "default.toml")
    assert builtin.config_version == on_disk.config_version
    assert builtin.sst.coefficient_set_id == on_disk.sst.coefficient_set_id
    assert builtin.sst.a0 == pytest.approx(on_disk.sst.a0)
    assert builtin.sst.a1 == pytest.approx(on_disk.sst.a1)
    assert builtin.sst.a2 == pytest.approx(on_disk.sst.a2)
    assert builtin.sst.output_offset_k == pytest.approx(on_disk.sst.output_offset_k)
    assert builtin.sst.valid_min_k == pytest.approx(on_disk.sst.valid_min_k)
    assert builtin.sst.valid_max_k == pytest.approx(on_disk.sst.valid_max_k)
    assert builtin.cloud.bt_cloud_threshold_k == pytest.approx(on_disk.cloud.bt_cloud_threshold_k)
    assert builtin.cloud.use_l1_cloud_flag == on_disk.cloud.use_l1_cloud_flag


def test_load_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.toml")


def test_load_malformed_missing_section_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.toml"
    bad.write_text('config_version = "x"\n[sst]\na0 = 1.0\n', encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(bad)


def test_load_wrong_type_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.toml"
    bad.write_text(
        "config_version = 1\n"  # must be a string
        "[sst]\n"
        'coefficient_set_id = "x"\n'
        "a0 = 1.0\na1 = 1.0\na2 = 2.0\noutput_offset_k = 0.0\n"
        'source = "s"\nvalid_min_k = 271.0\nvalid_max_k = 310.0\n'
        "[cloud]\nbt_cloud_threshold_k = 270.0\nuse_l1_cloud_flag = true\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load_config(bad)
