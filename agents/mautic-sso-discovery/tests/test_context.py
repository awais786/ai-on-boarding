from __future__ import annotations

from mautic_sso_discovery.context import load_moneta_contract


def test_load_moneta_contract_includes_all_sources():
    contract = load_moneta_contract()
    assert "Source: authentication.md" in contract
    assert "Source: apps-overview.md" in contract
    assert "Source: proxy-auth-middleware-spec.md" in contract


def test_load_moneta_contract_sections_are_substantial():
    contract = load_moneta_contract()
    # Verify each source section is present and substantial by checking
    # for source markers and verifying content exists between them
    sources = ["authentication.md", "apps-overview.md", "proxy-auth-middleware-spec.md"]
    for source in sources:
        marker = f"## Source: {source}"
        assert marker in contract, f"Missing source marker for {source}"
        # Verify content after marker is substantial
        marker_idx = contract.index(marker)
        # Content after this marker until next marker (or end) should be > 200 chars
        next_marker_idx = len(contract)
        for other_source in sources:
            if other_source != source:
                other_marker = f"## Source: {other_source}"
                idx = contract.find(other_marker, marker_idx + 1)
                if idx != -1 and idx < next_marker_idx:
                    next_marker_idx = idx
        section_content = contract[marker_idx + len(marker):next_marker_idx].strip()
        assert len(section_content) > 200, f"Section {source} is not substantial"
