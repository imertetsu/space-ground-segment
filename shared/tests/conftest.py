"""Shared test fixtures.

The ``postgres``-marked tests need a live PostgreSQL via ``PDGS_PG_DSN``; the
``pg_dsn`` fixture skips them cleanly when it is unset (so the default ``pytest``
run — no DB — passes on the non-DB tests alone).
"""

from __future__ import annotations

import os

import pytest

from sgs_shared.catalogue.repository import PG_DSN_ENV


@pytest.fixture
def pg_dsn() -> str:
    """Return the live PostgreSQL DSN, or skip the test if it is unset."""
    dsn = os.environ.get(PG_DSN_ENV)
    if not dsn:
        pytest.skip(f"{PG_DSN_ENV} not set; skipping live-PostgreSQL test")
    return dsn
