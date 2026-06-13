"""Shared cross-cutting layers for the Mini Space Ground Segment (Epic 3).

Three contracts unify the two segments without coupling them:
``time_service`` (OBT↔UTC), ``catalogue`` (shared PostgreSQL archive of payload
products + control telemetry references), and ``anomaly`` (one model for payload
processing failures + control OOL alarms).

**Dependency rule:** this package depends on NEITHER segment (`pdgs`/`sgs_sim`);
the segments depend on these contracts. The operator surface is a read-only
consumer (shared catalogue + the Yamcs REST API). Control telemetry remains
SIMULATED and labelled everywhere it surfaces.
"""

__version__ = "0.0.0"
