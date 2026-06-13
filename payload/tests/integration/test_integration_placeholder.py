"""Integration-test placeholder (Phase 0).

Real integration tests run each chain on small committed fixtures (a tiny clipped
EO scene; later, a short recorded packet stream). This placeholder keeps the
`integration` marker and the `integration` CI stage exercised and green.
"""

import pytest


@pytest.mark.integration
def test_integration_stage_is_wired() -> None:
    assert True
