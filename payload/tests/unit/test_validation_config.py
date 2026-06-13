"""Unit tests for the ValidationConfig schema + TOML loading (REQ-CFG-01)."""

from __future__ import annotations

from pathlib import Path

from pdgs.config.processing import ValidationConfig, default_config, load_config

_CONFIG_ROOT = Path(__file__).resolve().parents[2] / "config"


def test_validation_config_defaults_match_spec_thresholds() -> None:
    cfg = ValidationConfig()
    assert cfg.tolerance_k == 2.0
    assert cfg.max_abs_bias_k == 1.0
    assert cfg.max_rmse_k == 1.5
    assert cfg.min_pct_within_tol == 90.0
    assert cfg.min_match_count == 100
    assert cfg.min_quality_level == 3


def test_default_config_carries_validation_thresholds() -> None:
    cfg = default_config()
    assert cfg.validation.min_match_count == 100
    assert cfg.validation.max_rmse_k == 1.5


def test_default_toml_loads_validation_section() -> None:
    cfg = load_config(_CONFIG_ROOT / "default.toml")
    assert cfg.validation.tolerance_k == 2.0
    assert cfg.validation.max_abs_bias_k == 1.0
    assert cfg.validation.max_rmse_k == 1.5
    assert cfg.validation.min_pct_within_tol == 90.0
    assert cfg.validation.min_match_count == 100
    assert cfg.validation.min_quality_level == 3


def test_fixture_toml_loads_validation_section() -> None:
    cfg = load_config(_CONFIG_ROOT / "fixture.toml")
    assert cfg.validation.min_match_count == 100
    assert cfg.validation.min_quality_level == 3


def test_validation_section_is_optional(tmp_path: Path) -> None:
    # A config with no [validation] table falls back to the spec defaults.
    toml = tmp_path / "no_val.toml"
    toml.write_text(
        'config_version = "x"\n'
        "[sst]\n"
        'coefficient_set_id = "c"\n'
        "a0 = 0.0\na1 = 1.0\na2 = 0.0\noutput_offset_k = 0.0\n"
        'source = "s"\n'
        "valid_min_k = 200.0\nvalid_max_k = 350.0\n"
        "[cloud]\n"
        "bt_cloud_threshold_k = 270.0\nuse_l1_cloud_flag = true\n",
        encoding="utf-8",
    )
    cfg = load_config(toml)
    assert cfg.validation == ValidationConfig()


def test_validation_section_overrides(tmp_path: Path) -> None:
    toml = tmp_path / "override.toml"
    toml.write_text(
        'config_version = "x"\n'
        "[sst]\n"
        'coefficient_set_id = "c"\n'
        "a0 = 0.0\na1 = 1.0\na2 = 0.0\noutput_offset_k = 0.0\n"
        'source = "s"\n'
        "valid_min_k = 200.0\nvalid_max_k = 350.0\n"
        "[cloud]\n"
        "bt_cloud_threshold_k = 270.0\nuse_l1_cloud_flag = true\n"
        "[validation]\n"
        "max_rmse_k = 0.5\nmin_match_count = 10\nmin_quality_level = 4\n",
        encoding="utf-8",
    )
    cfg = load_config(toml)
    assert cfg.validation.max_rmse_k == 0.5
    assert cfg.validation.min_match_count == 10
    assert cfg.validation.min_quality_level == 4
    # Untouched keys keep the defaults.
    assert cfg.validation.tolerance_k == 2.0
