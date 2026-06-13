"""IV&V verification-suite placeholder (Phase 0).

The real IV&V suite — asserting every REQ-* is exercised and gating CI — is wired
in Phase 3 (validation). This placeholder keeps the `ivv` marker and the
`ivv-verification` CI stage exercised and green.
"""

import pytest


@pytest.mark.ivv
def test_ivv_suite_is_wired() -> None:
    assert True
