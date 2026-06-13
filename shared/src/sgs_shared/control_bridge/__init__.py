"""Read-only Yamcs-REST control bridge for the shared catalogue.

This package polls a running Yamcs server over plain HTTP (REST) and records control
telemetry/alarm **references** into the unified catalogue. It NEVER imports ``control/``
code and NEVER copies a telemetry value — only locator strings and lifecycle state.
"""

from __future__ import annotations

from sgs_shared.control_bridge.yamcs import (
    BridgeError,
    YamcsControlBridge,
    record_references,
)

__all__ = ["BridgeError", "YamcsControlBridge", "record_references"]
