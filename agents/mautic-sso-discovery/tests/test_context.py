from __future__ import annotations

from mautic_sso_discovery.context import load_moneta_contract


def test_load_moneta_contract_includes_all_sources():
    contract = load_moneta_contract()
    assert "Source: authentication.md" in contract
    assert "Source: apps-overview.md" in contract
    assert "Source: proxy-auth-middleware-spec.md" in contract


def test_load_moneta_contract_sections_are_substantial():
    contract = load_moneta_contract()
    sections = contract.split("\n\n---\n\n")
    assert len(sections) == 3
    assert all(len(section.strip()) > 200 for section in sections)
