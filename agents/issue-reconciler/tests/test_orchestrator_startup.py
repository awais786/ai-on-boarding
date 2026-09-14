from __future__ import annotations

import pytest
from support import make_routed_client

from issue_reconciler.orchestrator import validate_board_config


def test_resolves_quietly_when_the_configured_project_still_exists():
    client, _ = make_routed_client([("ValidateProject", {"node": {"id": "PVT_kwHOA4V_f84AGZiK"}})])
    validate_board_config(client)  # does not raise


def test_fails_loudly_when_the_configured_project_no_longer_resolves():
    client, _ = make_routed_client([("ValidateProject", {"node": None})])
    with pytest.raises(RuntimeError, match="no longer resolves"):
        validate_board_config(client)
