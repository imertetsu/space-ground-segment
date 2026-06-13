"""Unit tests for threshold-based cloud screening (REQ-PRO-01)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from pdgs.config.processing import CloudScreeningConfig
from pdgs.ingestion.readers import read_l1_rbt
from pdgs.processing.cloud_screening.screen import screen_clouds

# The fixture flags 14 cloudy pixels (a blob + two scattered) in flags_in.cloud_in.
_FIXTURE_CLOUDY = 14


def test_screen_flags_known_cloudy_pixels_via_l1_flag(l1_safe_dir: Path) -> None:
    scene = read_l1_rbt(l1_safe_dir)
    # Threshold low enough that the BT path never fires => mask == the L1 flag set.
    cfg = CloudScreeningConfig(bt_cloud_threshold_k=250.0, use_l1_cloud_flag=True)
    mask = screen_clouds(scene, cfg)
    assert mask.dtype == np.bool_
    assert mask.shape == scene.shape
    expected = (scene.cloud_flags & 1) != 0
    assert np.array_equal(mask, expected)
    assert int(mask.sum()) == _FIXTURE_CLOUDY


def test_screen_threshold_path_flags_cold_pixels(l1_safe_dir: Path) -> None:
    scene = read_l1_rbt(l1_safe_dir)
    s8 = scene.brightness_temperature("S8")
    # Threshold above the warmest pixel => every (finite) pixel is "cold" => cloud.
    hot_threshold = float(np.nanmax(s8)) + 1.0
    cfg = CloudScreeningConfig(bt_cloud_threshold_k=hot_threshold, use_l1_cloud_flag=False)
    mask = screen_clouds(scene, cfg)
    assert bool(np.all(mask))


def test_screen_l1_flag_disabled_ignores_flag(l1_safe_dir: Path) -> None:
    scene = read_l1_rbt(l1_safe_dir)
    # Threshold below the coldest pixel AND flag disabled => no cloud at all.
    s8 = scene.brightness_temperature("S8")
    cold_threshold = float(np.nanmin(s8)) - 1.0
    cfg = CloudScreeningConfig(bt_cloud_threshold_k=cold_threshold, use_l1_cloud_flag=False)
    mask = screen_clouds(scene, cfg)
    assert int(mask.sum()) == 0


def test_screen_union_of_threshold_and_flag(l1_safe_dir: Path) -> None:
    scene = read_l1_rbt(l1_safe_dir)
    s8 = scene.brightness_temperature("S8")
    flagged = (scene.cloud_flags & 1) != 0
    # Pick a threshold that catches the warmest ~half so the union strictly exceeds
    # the flag-only set.
    median = float(np.nanmedian(s8))
    cfg = CloudScreeningConfig(bt_cloud_threshold_k=median, use_l1_cloud_flag=True)
    mask = screen_clouds(scene, cfg)
    cold = s8 < median
    assert np.array_equal(mask, cold | flagged)
    assert int(mask.sum()) >= int(flagged.sum())
