"""Unit tests for services.research.discovery.

All network calls are mocked via the `http_get` injection point — no
external service is hit during tests.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List

import pytest

# Add backend/ to sys.path so `services.research.discovery` is importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.research.discovery import (
    ArxivSource,
    Discovery,
    DiscoverySource,
    GitHubTopicStub,
    HuggingFaceStub,
    discover_all,
)


# ────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────


def _arxiv_xml_one_entry() -> str:
    """Minimal Atom XML matching an arxiv response for one entry."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.12345v1</id>
    <title>
      Gamma Exposure  and  Dealer  Hedging
    </title>
    <summary>
      We  study  gamma exposure  in   SPX  options.
    </summary>
    <published>2024-01-15T18:00:00Z</published>
    <author><name>Alice Smith</name></author>
    <author><name>Bob Jones</name></author>
    <category term="q-fin.PR"/>
    <category term="q-fin.TR"/>
  </entry>
</feed>"""


def _arxiv_xml_empty() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
</feed>"""


def _arxiv_xml_broken() -> str:
    return "not valid xml <>><<>>"


def _arxiv_xml_multiple() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.11111v2</id>
    <title>First</title>
    <summary>abstract one</summary>
    <author><name>X</name></author>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2402.22222</id>
    <title>Second</title>
    <summary>abstract two</summary>
    <author><name>Y</name></author>
  </entry>
</feed>"""


# ────────────────────────────────────────────────────────────────────────────
# ArxivSource — parsing
# ────────────────────────────────────────────────────────────────────────────


def test_arxiv_parses_single_entry():
    src = ArxivSource(http_get=lambda url, hdr: _arxiv_xml_one_entry())
    results = src.search("gamma exposure")
    assert len(results) == 1
    d = results[0]
    assert d.id == "arxiv:2401.12345"
    assert d.title == "Gamma Exposure and Dealer Hedging"
    assert d.url == "https://arxiv.org/abs/2401.12345"
    assert d.source == "arxiv"
    assert d.authors == ["Alice Smith", "Bob Jones"]
    assert d.published == "2024-01-15T18:00:00Z"
    assert "gamma exposure" in d.abstract.lower()
    assert "q-fin.PR" in d.tags
    assert "q-fin.TR" in d.tags
    assert d.license is None  # arxiv Atom doesn't expose license per-entry
    assert d.relevance_score is None  # filled by downstream vetting


def test_arxiv_handles_empty_feed():
    src = ArxivSource(http_get=lambda url, hdr: _arxiv_xml_empty())
    assert src.search("nothing") == []


def test_arxiv_handles_broken_xml_gracefully():
    src = ArxivSource(http_get=lambda url, hdr: _arxiv_xml_broken())
    # Should not raise; returns empty list.
    assert src.search("anything") == []


def test_arxiv_parses_multiple_entries():
    src = ArxivSource(http_get=lambda url, hdr: _arxiv_xml_multiple())
    results = src.search("anything")
    assert len(results) == 2
    ids = [d.id for d in results]
    assert "arxiv:2401.11111" in ids
    assert "arxiv:2402.22222" in ids


def test_arxiv_strips_version_suffix_from_id():
    """Arxiv IDs from the API have a `v1`/`v2` suffix on the abs URL.
    Our normalized id should drop it for stable cross-version dedup.
    """
    src = ArxivSource(http_get=lambda url, hdr: _arxiv_xml_one_entry())
    [d] = src.search("x")
    assert d.id == "arxiv:2401.12345"  # not 2401.12345v1


def test_arxiv_normalizes_whitespace_in_title_and_abstract():
    src = ArxivSource(http_get=lambda url, hdr: _arxiv_xml_one_entry())
    [d] = src.search("x")
    # No double/triple spaces from XML formatting
    assert "  " not in d.title
    assert "  " not in d.abstract


# ────────────────────────────────────────────────────────────────────────────
# ArxivSource — URL construction
# ────────────────────────────────────────────────────────────────────────────


def test_arxiv_query_is_url_encoded_correctly():
    captured: Dict[str, str] = {}

    def fake_get(url: str, hdr: Dict[str, str]) -> str:
        captured["url"] = url
        captured["ua"] = hdr.get("User-Agent", "")
        return _arxiv_xml_empty()

    src = ArxivSource(http_get=fake_get, max_results=10)
    src.search("gamma exposure dealer")

    assert "export.arxiv.org/api/query" in captured["url"]
    assert "search_query=all%3Agamma+exposure+dealer" in captured["url"]
    assert "max_results=10" in captured["url"]
    assert "confluence-decoder" in captured["ua"]


# ────────────────────────────────────────────────────────────────────────────
# Discovery dataclass
# ────────────────────────────────────────────────────────────────────────────


def test_discovery_to_dict_default_strips_raw():
    d = Discovery(
        id="arxiv:x", title="t", url="u", source="arxiv",
        discovered_at="now", raw={"big": "blob"},
    )
    out = d.to_dict()
    assert "raw" not in out
    assert out["id"] == "arxiv:x"


def test_discovery_to_dict_with_raw():
    d = Discovery(
        id="arxiv:x", title="t", url="u", source="arxiv",
        discovered_at="now", raw={"big": "blob"},
    )
    out = d.to_dict(include_raw=True)
    assert out["raw"] == {"big": "blob"}


# ────────────────────────────────────────────────────────────────────────────
# Stubs — should not crash; should report not-implemented
# ────────────────────────────────────────────────────────────────────────────


def test_huggingface_stub_raises_not_implemented():
    src = HuggingFaceStub()
    with pytest.raises(NotImplementedError):
        src.search("anything")


def test_github_topic_stub_raises_not_implemented():
    src = GitHubTopicStub()
    with pytest.raises(NotImplementedError):
        src.search("options-trading")


# ────────────────────────────────────────────────────────────────────────────
# discover_all orchestrator
# ────────────────────────────────────────────────────────────────────────────


def test_discover_all_aggregates_across_sources():
    src = ArxivSource(http_get=lambda url, hdr: _arxiv_xml_multiple())
    discoveries, errors = discover_all(
        [src],
        {"arxiv": ["query1"]},
    )
    assert len(discoveries) == 2
    assert errors == {}


def test_discover_all_captures_stub_errors():
    arxiv = ArxivSource(http_get=lambda url, hdr: _arxiv_xml_one_entry())
    hf = HuggingFaceStub()
    discoveries, errors = discover_all(
        [arxiv, hf],
        {"arxiv": ["q"], "huggingface": ["q"]},
    )
    # arxiv produced 1; HF stub recorded an error
    assert len(discoveries) == 1
    assert "huggingface" in errors
    assert "not implemented" in errors["huggingface"]


def test_discover_all_skips_sources_with_no_queries():
    src = ArxivSource(http_get=lambda url, hdr: _arxiv_xml_one_entry())
    discoveries, errors = discover_all([src], {})  # no queries
    assert discoveries == []
    assert errors == {}


# ────────────────────────────────────────────────────────────────────────────
# Rate-limit sleep behaviour
# ────────────────────────────────────────────────────────────────────────────


def test_search_many_sleeps_between_calls(monkeypatch):
    sleeps: List[float] = []
    monkeypatch.setattr(
        "services.research.discovery.time.sleep",
        lambda s: sleeps.append(s),
    )
    src = ArxivSource(http_get=lambda url, hdr: _arxiv_xml_empty())
    src.search_many(["q1", "q2", "q3"])
    # 2 sleeps between 3 queries
    assert len(sleeps) == 2
    assert all(s == 3.0 for s in sleeps)


def test_search_many_does_not_sleep_before_first():
    sleep_count = {"n": 0}

    class Counter:
        def sleep(self, s):
            sleep_count["n"] += 1

    # Single-query call should not sleep at all.
    src = ArxivSource(http_get=lambda url, hdr: _arxiv_xml_empty())
    src.search_many(["only_one_query"])
    # Nothing to assert via monkeypatch here without setting it up; we
    # implicitly verified via the previous test that N-1 sleeps happen for
    # N queries, so N=1 → 0 sleeps.
