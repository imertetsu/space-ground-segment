"""Threshold-based cloud screening (REQ-PRO-01).

:func:`screen_clouds` is a PURE function: it derives a boolean cloud mask from an
:class:`~pdgs.ingestion.readers.L1Scene` and a
:class:`~pdgs.config.processing.CloudScreeningConfig`, with no cross-import from the
SST retrieval processor — the two processors are independently runnable
(REQ-PRO-04) and composed by the orchestrator.

SIMPLIFICATION (documented, never presented as operational): this is a simple
brightness-temperature threshold, NOT a trained/operational SLSTR cloud mask. A
pixel is screened as cloud when its S8 (~10.8 µm) brightness temperature is below
``bt_cloud_threshold_k`` (cold ⇒ likely cloud over warm sea), OR — when
``use_l1_cloud_flag`` is set — where the L1 ``cloud_flags`` bit-0 is set (the
fixture cloud convention; the real ``cloud_in`` bitmask is richer).
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from pdgs.config.processing import CloudScreeningConfig
from pdgs.ingestion.readers import L1Scene

# Bit set in the L1 ``cloud_flags`` bitmask that marks a cloudy pixel (fixture
# convention; the operational ``cloud_in`` flag set is richer — a simplification).
_L1_CLOUD_BIT = np.int32(1)


def screen_clouds(scene: L1Scene, cfg: CloudScreeningConfig) -> npt.NDArray[np.bool_]:
    """Return a boolean cloud mask (``True`` = cloud) for ``scene`` (REQ-PRO-01).

    Cloud where the S8 (~10.8 µm) brightness temperature is below
    ``cfg.bt_cloud_threshold_k`` (NaN BT pixels are treated as cloud/invalid), OR
    — when ``cfg.use_l1_cloud_flag`` — where the L1 ``cloud_flags`` bit-0 is set.
    The result has the scene's pixel shape.

    SIMPLIFICATION: threshold-based, not an operational cloud mask (see SRD §4).
    """
    s8 = scene.brightness_temperature("S8")
    # Cold-or-invalid pixels: below threshold, or NaN (missing/undecodable BT).
    cold = ~(s8 >= cfg.bt_cloud_threshold_k)
    mask: npt.NDArray[np.bool_] = np.asarray(cold, dtype=np.bool_)

    if cfg.use_l1_cloud_flag:
        flagged = (scene.cloud_flags & _L1_CLOUD_BIT) != 0
        mask = mask | np.asarray(flagged, dtype=np.bool_)

    return mask
