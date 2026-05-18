"""Research-discovery core.

Defines:
- `Discovery` — the common normalized record format
- `DiscoverySource` — abstract base for any external research service
- `ArxivSource` — concrete implementation hitting arxiv's public API
- `discover_all(sources, queries)` — orchestrator that runs all sources

Concrete implementations should:
1. Accept a query string in their constructor or `search(query)` method.
2. Return a list of raw vendor responses from `_fetch(query)`.
3. Normalize each raw response into a `Discovery` via `_parse(raw)`.
4. Respect rate limits (sleep between requests; default 3s between arxiv calls).
5. Never call sources that require auth without the auth being present in env.

License/vetting: discoveries are SUSPECT by default — the `Discovery.license`
field tracks what's known. Anything ambiguous → manual review before
ingestion into training data. See ADR-0003.
"""

from __future__ import annotations

import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple


# ────────────────────────────────────────────────────────────────────────────
# Normalized record
# ────────────────────────────────────────────────────────────────────────────


@dataclass
class Discovery:
    """Common schema for any discovered research artifact.

    `id` is `<source>:<source_id>` (e.g. `arxiv:2401.12345`).
    `relevance_score` starts at None; downstream vetting fills it.
    `license` is what the source claims; None if unknown.
    """
    id: str
    title: str
    url: str
    source: str
    discovered_at: str
    authors: List[str] = field(default_factory=list)
    published: Optional[str] = None
    abstract: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    license: Optional[str] = None
    relevance_score: Optional[float] = None
    raw: Optional[Dict[str, Any]] = None  # provenance, not serialized by default

    def to_dict(self, include_raw: bool = False) -> Dict[str, Any]:
        d = asdict(self)
        if not include_raw:
            d.pop("raw", None)
        return d


# ────────────────────────────────────────────────────────────────────────────
# Abstract source
# ────────────────────────────────────────────────────────────────────────────


class DiscoverySource(ABC):
    """A single external research service. Subclasses implement `_fetch` and `_parse`."""

    name: str = "abstract"
    rate_limit_seconds: float = 3.0

    def __init__(self, http_get: Optional[Callable[[str, Dict[str, str]], str]] = None):
        """`http_get` is injected for testability — defaults to urllib."""
        self._http_get = http_get or self._default_http_get

    @abstractmethod
    def _fetch(self, query: str) -> Any:
        """Return the raw vendor response (may be parsed XML/JSON or plain text)."""

    @abstractmethod
    def _parse(self, raw: Any) -> List[Discovery]:
        """Convert vendor-specific response into normalized Discoveries."""

    def search(self, query: str) -> List[Discovery]:
        raw = self._fetch(query)
        return self._parse(raw)

    def search_many(self, queries: Iterable[str]) -> List[Discovery]:
        out: List[Discovery] = []
        first = True
        for q in queries:
            if not first:
                time.sleep(self.rate_limit_seconds)
            first = False
            out.extend(self.search(q))
        return out

    @staticmethod
    def _default_http_get(url: str, headers: Dict[str, str]) -> str:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8", errors="replace")


# ────────────────────────────────────────────────────────────────────────────
# arxiv source
# ────────────────────────────────────────────────────────────────────────────


_ARXIV_NS = {"a": "http://www.w3.org/2005/Atom"}


class ArxivSource(DiscoverySource):
    """arxiv.org API. No auth required. Public, well-documented.

    Docs: https://info.arxiv.org/help/api/user-manual.html

    The API returns Atom XML. We use stdlib ElementTree to avoid adding a
    dependency.

    Query construction (bug-fix 2026-05-18): unquoted multi-token queries
    against `all:` returned wildly off-topic results (e.g. "gamma exposure
    dealer hedging" returned Gaussian-splatting and gamma-ray-astronomy
    papers). We now wrap the query as a phrase AND restrict to the
    quantitative-finance category set by default. Pass `categories=None` to
    disable the category filter, or a custom tuple to override.
    """

    name = "arxiv"
    base_url = "http://export.arxiv.org/api/query"
    rate_limit_seconds = 3.0  # arxiv asks for ≥ 3s between requests

    DEFAULT_CATEGORIES = (
        "q-fin.PR",  # pricing of securities
        "q-fin.TR",  # trading and market microstructure
        "q-fin.RM",  # risk management
        "q-fin.MF",  # mathematical finance
        "q-fin.ST",  # statistical finance
        "q-fin.PM",  # portfolio management
        "q-fin.CP",  # computational finance
        "q-fin.GN",  # general finance
        "stat.AP",   # applied statistics (overlaps with finance ML)
    )

    def __init__(
        self,
        max_results: int = 25,
        categories=DEFAULT_CATEGORIES,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.max_results = max_results
        self.categories = categories

    def _fetch(self, query: str) -> str:
        # Build a precise query: ALL terms must appear in the doc, but not
        # necessarily as a consecutive phrase. Phrase-quoting (`all:"a b c"`)
        # is too strict — 4-word phrases rarely match. Bare `all:a b c` is
        # too loose — arxiv stems / fuzz-matches and returns unrelated papers.
        # AND-ing each term wrapped in `all:` is the sweet spot.
        tokens = [t for t in query.split() if t]
        if tokens:
            term_clause = " AND ".join(f"all:{t}" for t in tokens)
        else:
            term_clause = ""
        if self.categories:
            cat_clause = " OR ".join(f"cat:{c}" for c in self.categories)
            search_query = (
                f"({cat_clause}) AND ({term_clause})" if term_clause else f"({cat_clause})"
            )
        else:
            search_query = term_clause or "all:*"
        params = {
            "search_query": search_query,
            "start": "0",
            "max_results": str(self.max_results),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        url = f"{self.base_url}?{urllib.parse.urlencode(params)}"
        return self._http_get(url, {"User-Agent": "confluence-decoder-research/0.1"})

    def _parse(self, raw: str) -> List[Discovery]:
        results: List[Discovery] = []
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            return results

        for entry in root.findall("a:entry", _ARXIV_NS):
            arxiv_id = self._strip_arxiv_id(self._text(entry, "a:id"))
            if not arxiv_id:
                continue
            authors = [
                self._text(a, "a:name")
                for a in entry.findall("a:author", _ARXIV_NS)
                if self._text(a, "a:name")
            ]
            categories = [
                c.get("term", "") for c in entry.findall("a:category", _ARXIV_NS)
                if c.get("term")
            ]
            results.append(
                Discovery(
                    id=f"arxiv:{arxiv_id}",
                    title=self._normalize_whitespace(self._text(entry, "a:title")),
                    url=f"https://arxiv.org/abs/{arxiv_id}",
                    source=self.name,
                    discovered_at=datetime.now(timezone.utc).isoformat(),
                    authors=authors,
                    published=self._text(entry, "a:published") or None,
                    abstract=self._normalize_whitespace(self._text(entry, "a:summary")),
                    tags=categories,
                    # arxiv preprints don't have a single license field in Atom;
                    # default to None — most are CC-BY or similar but verify
                    # case-by-case via the abs page.
                    license=None,
                )
            )
        return results

    @staticmethod
    def _text(node: Optional[ET.Element], path: str) -> str:
        if node is None:
            return ""
        found = node.find(path, _ARXIV_NS)
        if found is None or found.text is None:
            return ""
        return found.text

    @staticmethod
    def _strip_arxiv_id(url_or_id: str) -> str:
        """Extract '2401.12345' from 'http://arxiv.org/abs/2401.12345v1' etc."""
        if not url_or_id:
            return ""
        m = re.search(r"(\d{4}\.\d{4,5})(v\d+)?$", url_or_id.strip())
        return m.group(1) if m else url_or_id.strip().split("/")[-1]

    @staticmethod
    def _normalize_whitespace(s: str) -> str:
        return re.sub(r"\s+", " ", (s or "").strip())


# ────────────────────────────────────────────────────────────────────────────
# Stub sources (to be implemented in follow-up PRs)
# ────────────────────────────────────────────────────────────────────────────


class HuggingFaceStub(DiscoverySource):
    """STUB. Will hit `https://huggingface.co/api/datasets?search=...` (no auth).
    Not yet implemented — opening it as a stub so the orchestrator can list
    it as TODO and not crash if invoked.
    """
    name = "huggingface"

    def _fetch(self, query: str) -> str:
        raise NotImplementedError("HuggingFaceStub not implemented yet")

    def _parse(self, raw: str) -> List[Discovery]:
        raise NotImplementedError("HuggingFaceStub not implemented yet")


class GitHubTopicStub(DiscoverySource):
    """STUB. Will use the `gh` CLI to search github topics like `gamma-exposure`,
    `options-trading`, `quantitative-finance`. Not yet implemented.
    """
    name = "github_topic"

    def _fetch(self, query: str) -> str:
        raise NotImplementedError("GitHubTopicStub not implemented yet")

    def _parse(self, raw: str) -> List[Discovery]:
        raise NotImplementedError("GitHubTopicStub not implemented yet")


# ────────────────────────────────────────────────────────────────────────────
# Orchestrator
# ────────────────────────────────────────────────────────────────────────────


def discover_all(
    sources: List[DiscoverySource],
    queries_per_source: Dict[str, List[str]],
) -> Tuple[List[Discovery], Dict[str, str]]:
    """Run each source over its assigned queries.

    Returns:
        (all_discoveries, errors_by_source_name)
    """
    out: List[Discovery] = []
    errors: Dict[str, str] = {}
    for source in sources:
        qs = queries_per_source.get(source.name) or []
        if not qs:
            continue
        try:
            out.extend(source.search_many(qs))
        except NotImplementedError as exc:
            errors[source.name] = f"not implemented: {exc}"
        except Exception as exc:  # noqa: BLE001 — best-effort multi-source
            errors[source.name] = f"{type(exc).__name__}: {exc}"
    return out, errors
