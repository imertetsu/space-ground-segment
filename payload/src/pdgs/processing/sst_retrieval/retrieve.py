"""Simplified split-window SST retrieval (REQ-PRO-02, REQ-PRO-05).

:func:`retrieve_sst` is a PURE function: it computes a derived Sea Surface
Temperature field from an :class:`~pdgs.ingestion.readers.L1Scene`, a cloud mask,
and an :class:`~pdgs.config.processing.SstConfig`, with no cross-import from the
cloud-screening processor — the two processors are independently runnable
(REQ-PRO-04) and composed by the orchestrator.

SCIENCE (cited, see :mod:`pdgs.config.processing`): the N2 nadir-only dual-channel
(11/12 µm) split-window SST type of the SLSTR SST ATBD (EUMETSAT), in the
SIMPLIFIED constant-coefficient MCSST form (McClain/Pichel/Walton 1985):

    SST_K = a0 + a1*S8 + a2*(S8 - S9) + output_offset_k

with S8 (~10.8 µm) ≈ T11 and S9 (~12 µm) ≈ T12. This is a documented
simplification (incl. a cross-sensor coefficient substitution), NOT operational.

Cloudy pixels are set to NaN (not computed). Pixels whose retrieved SST falls
outside ``[valid_min_k, valid_max_k]`` are FLAGGED, never clamped or discarded
(REQ-PRO-05).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import numpy as np
import numpy.typing as npt

from pdgs.config.processing import SstConfig
from pdgs.ingestion.readers import L1Scene


@dataclass(frozen=True)
class SstResult:
    """Output of :func:`retrieve_sst` (FROZEN — consumed by the product writer).

    ``sst_k`` is the derived SST in Kelvin (NaN over cloudy / non-computed
    pixels). ``out_of_range`` flags clear-sky pixels whose SST fell outside the
    configured valid range (REQ-PRO-05) — these are flagged, not clamped.
    """

    sst_k: npt.NDArray[np.float32]
    out_of_range: npt.NDArray[np.bool_]


def retrieve_sst(
    scene: L1Scene,
    cloud_mask: npt.NDArray[np.bool_],
    cfg: SstConfig,
) -> SstResult:
    """Retrieve simplified split-window SST (K) over clear-sky pixels (REQ-PRO-02).

    Computes ``sst = a0 + a1*S8 + a2*(S8-S9) + output_offset_k`` everywhere, then
    sets cloudy pixels (``cloud_mask`` True) to NaN. Pixels whose SST lies outside
    ``[cfg.valid_min_k, cfg.valid_max_k]`` are flagged in ``out_of_range`` (clear
    sky only — cloudy NaN pixels are never flagged) and left as computed, not
    clamped (REQ-PRO-05).

    ``cloud_mask`` must match the scene's pixel shape.
    """
    if cloud_mask.shape != scene.shape:
        raise ValueError(
            f"cloud_mask shape {cloud_mask.shape} does not match scene shape {scene.shape}"
        )

    s8 = scene.brightness_temperature("S8")
    s9 = scene.brightness_temperature("S9")

    raw = cfg.a0 + cfg.a1 * s8 + cfg.a2 * (s8 - s9) + cfg.output_offset_k

    cloud = np.asarray(cloud_mask, dtype=np.bool_)
    # Cloudy pixels are not computed: surface them as NaN (not clamped/discarded).
    sst: npt.NDArray[np.float32] = cast(
        "npt.NDArray[np.float32]",
        np.where(cloud, np.float32(np.nan), raw).astype(np.float32),
    )

    # Flag (do not clamp) clear-sky pixels outside the configured valid range.
    clear = ~cloud
    below = sst < np.float32(cfg.valid_min_k)
    above = sst > np.float32(cfg.valid_max_k)
    out_of_range: npt.NDArray[np.bool_] = np.asarray((below | above) & clear, dtype=np.bool_)

    return SstResult(sst_k=sst, out_of_range=out_of_range)
