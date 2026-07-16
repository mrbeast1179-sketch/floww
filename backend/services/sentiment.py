"""
backend/services/sentiment.py

Multi-model sentiment reconciliation engine (steal-list rank "Multi-model
sentiment reconciliation engine" — VADER + TextBlob agreement gate)
==============================================================================

For a text string, computes a tuple ``(avg_polarity, subjectivity, label)``
where:

  * ``avg_polarity`` is the arithmetic mean of TextBlob's polarity and
    VADER's compound score (the same convention as the upstream
    ``shirosaidev/stocksight`` ``sentiment_analysis()`` function).
  * ``subjectivity`` is TextBlob's subjectivity.
  * ``label`` is one of ``"positive"``, ``"negative"``, ``"neutral"``,
    ``"unavailable"``. The agreement gate is an AND: BOTH must exceed their
    threshold for a positive/negative label, otherwise ``"neutral"``.

This is the GENUINELY-IMPLEMENTING counterpart to the stub
``backend/social_flow_pipeline.py::TickerSentiment`` dataclass: that class
declares the shape but ships no scoring code. This module is the missing
implementation. Wiring into the social-flow pipeline + the
``composite_flow_score`` feature column is a focused followup (out of scope
this turn; called out in the .md).

Steal from:   ``shirosaidev/stocksight`` ``stocksight/sentiment.py::sentiment_analysis``
              + ``clean_text`` + ``clean_text_sentiment`` (port verbatim).
Lands in floww: ``GET /api/sentiment?text=...`` mounted on
                ``backend/routes/steal_three.py`` (canonical :8000).
Audit:        ``docs/reports/2026-07-11-steal-list-integration-roadmap.md``
              (sentiment subsection).
              ``backend/tests/services/test_sentiment.py`` (~16 cases).

This module is PURE-LOGIC aside from the VADER/TextBlob imports at module
top (defensive try/except — failure modes are exposed as
``VADER_AVAILABLE`` / ``TEXTBLOB_AVAILABLE`` flags and the ``"unavailable"``
string label so the route layer can degrade gracefully).
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------------
# Defensive library imports — fail closed with sentinel flags so callers
# can detect "we scored this but at least one model is offline" rather
# than crashing on a missing-dependency at request time.
# ----------------------------------------------------------------------------

VADER_AVAILABLE: bool = True
TEXTBLOB_AVAILABLE: bool = True
_VADER_IMPORT_ERROR: str | None = None
_TEXTBLOB_IMPORT_ERROR: str | None = None

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer  # noqa: F401
except Exception as exc:  # noqa: BLE001 — vaderSentiment optional in dev
    VADER_AVAILABLE = False
    _VADER_IMPORT_ERROR = f"{exc.__class__.__name__}: {exc}"
    logger.warning("sentiment: vaderSentiment unavailable — %s", _VADER_IMPORT_ERROR)

try:
    from textblob import TextBlob  # noqa: F401
except Exception as exc:  # noqa: BLE001 — textblob optional in dev
    TEXTBLOB_AVAILABLE = False
    _TEXTBLOB_IMPORT_ERROR = f"{exc.__class__.__name__}: {exc}"
    logger.warning("sentiment: textblob unavailable — %s", _TEXTBLOB_IMPORT_ERROR)


# ----------------------------------------------------------------------------
# Agreement-gate thresholds (kept as module constants so a future tweak to
# the threshold lives in ONE place).
# ----------------------------------------------------------------------------

# VADER compound ≥ +0.05 / ≤ −0.05 is the standard "non-neutral" range
# (matches the shirosaidev/stocksight reference). Anything below this
# magnitude is treated as neutral.
_VADER_POS_THRESHOLD: float = 0.05
_VADER_NEG_THRESHOLD: float = -0.05

# TextBlob uses the natural sign: polarity > 0 ⇒ positive, < 0 ⇒ negative,
# == 0 ⇒ neutral. No threshold magnitude is applied because polarity is
# already scaled to [-1, 1] with the boundary at 0.
_TEXTBLOB_POS_THRESHOLD: float = 0.0
_TEXTBLOB_NEG_THRESHOLD: float = 0.0


# ----------------------------------------------------------------------------
# Text cleaning helpers — ported verbatim from shirosaidev/stocksight so the
# scoring output matches the reference exactly.
# ----------------------------------------------------------------------------

def clean_text(text: str) -> str:
    """Strip noise from a text body before sentiment scoring.

    Replaces newlines with spaces; removes URLs, HTML entities, HTML tags,
    ``RT`` retweet markers, and trailing/leading whitespace.
    """
    if not isinstance(text, str):
        return ""
    text = text.replace("\n", " ")
    text = re.sub(r"https?\S+", "", text)        # URLs
    text = re.sub(r"&.*?;", "", text)            # HTML entities
    text = re.sub(r"<.*?>", "", text)            # HTML tags
    text = text.replace("RT", "").replace("\u2026", "")  # RT marker + ellipsis
    return text.strip()


def clean_text_sentiment(text: str) -> str:
    """Strip mentions/hashtags AFTER clean_text() — pure sentiment step.

    Goes a step further than ``clean_text`` by removing ``@mention`` and
    ``#hashtag`` tokens alongside the general noise.
    """
    if not isinstance(text, str):
        return ""
    text = re.sub(r"[#|@]\S+", "", text)
    return text.strip()


# ----------------------------------------------------------------------------
# Plug-point helpers (tests monkey-patch these two functions to inject
# deterministic scores, so the test suite doesn't require real VADER +
# TextBlob installs).
# ----------------------------------------------------------------------------

def _analyze_vader(text: str) -> tuple[float, dict[str, float]]:
    """Score ``text`` via VADER. Returns ``(compound, full_scores_dict)``.

    When vaderSentiment isn't installed, returns ``(0.0, {})`` and
    ``VADER_AVAILABLE is False``. Tests monkey-patch this to inject
    deterministic scores.
    """
    if not VADER_AVAILABLE:
        return 0.0, {"neg": 0.0, "neu": 1.0, "pos": 0.0, "compound": 0.0}
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    scores = SentimentIntensityAnalyzer().polarity_scores(text)
    return float(scores["compound"]), scores


def _analyze_textblob(text: str) -> tuple[float, float]:
    """Score ``text`` via TextBlob. Returns ``(polarity, subjectivity)``.

    When textblob isn't installed, returns ``(0.0, 0.0)`` and
    ``TEXTBLOB_AVAILABLE is False``. Tests monkey-patch this to inject
    deterministic scores.
    """
    if not TEXTBLOB_AVAILABLE:
        return 0.0, 0.0
    from textblob import TextBlob
    blob = TextBlob(text).sentiment
    return float(blob.polarity), float(blob.subjectivity)


# ----------------------------------------------------------------------------
# Public API — score_text + aggregate_sentiment.
# ----------------------------------------------------------------------------

def _label_from_agreement(
    vader_compound: float,
    textblob_polarity: float,
    vader_available: bool,
    textblob_available: bool,
) -> str:
    """Apply the agreement gate (or single-source fallback) to a score pair.

    Both-libraries path:
      * Negative iff ``textblob < 0 AND vader <= -0.05``
      * Positive iff ``textblob > 0 AND vader >= +0.05``
      * Else neutral.

    Single-library fallbacks:
      * vader only: ``positive if vader >= +0.05; negative if <= -0.05; else neutral``
      * textblob only: ``positive if polarity > 0; negative if < 0; else neutral``

    Both libraries missing: ``"unavailable"``.
    """
    if not vader_available and not textblob_available:
        return "unavailable"
    if not vader_available:
        if textblob_polarity > _TEXTBLOB_POS_THRESHOLD:
            return "positive"
        if textblob_polarity < _TEXTBLOB_NEG_THRESHOLD:
            return "negative"
        return "neutral"
    if not textblob_available:
        if vader_compound >= _VADER_POS_THRESHOLD:
            return "positive"
        if vader_compound <= _VADER_NEG_THRESHOLD:
            return "negative"
        return "neutral"
    # Both available — apply AND-gate.
    if textblob_polarity < _TEXTBLOB_NEG_THRESHOLD and vader_compound <= _VADER_NEG_THRESHOLD:
        return "negative"
    if textblob_polarity > _TEXTBLOB_POS_THRESHOLD and vader_compound >= _VADER_POS_THRESHOLD:
        return "positive"
    return "neutral"


def score_text(text: Any) -> tuple[float, float, str]:
    """Score a single text string.

    Returns ``(avg_polarity, subjectivity, label)`` where:

      * ``avg_polarity`` is the arithmetic mean of TextBlob's polarity
        AND VADER's compound, rounded to 4dp. When only one library is
        available, returns that library's score (rounded).
      * ``subjectivity`` is TextBlob's subjectivity (0 if textblob is
        unavailable), rounded to 4dp.
      * ``label`` is one of ``"positive"``, ``"negative"``, ``"neutral"``,
        ``"unavailable"``.

    Edge cases:
      * ``text`` is ``None``, empty after cleaning, or non-string → returns
        ``(0.0, 0.0, "neutral")``. Single-library miss also returns the
        same primary signal of ``"neutral"`` when there's no language to score.
      * Both libraries unavailable → label is ``"unavailable"`` so callers
        can render an explicit "offline" state rather than fabricate a
        sentiment call.
    """
    if not isinstance(text, str) or not text.strip():
        return (0.0, 0.0, "neutral")

    cleaned = clean_text_sentiment(clean_text(text))

    vader_compound, _ = _analyze_vader(cleaned)
    textblob_polarity, textblob_subjectivity = _analyze_textblob(cleaned)

    label = _label_from_agreement(
        vader_compound, textblob_polarity,
        VADER_AVAILABLE, TEXTBLOB_AVAILABLE,
    )

    # avg_polarity always combines BOTH when both are available (matches
    # the upstream reference). Falls back to whichever singleton is alive.
    if VADER_AVAILABLE and TEXTBLOB_AVAILABLE:
        avg = (textblob_polarity + vader_compound) / 2.0
    elif VADER_AVAILABLE:
        avg = vader_compound
    elif TEXTBLOB_AVAILABLE:
        avg = textblob_polarity
    else:
        avg = 0.0

    return (round(float(avg), 4), round(float(textblob_subjectivity), 4), label)


def aggregate_sentiment(texts: list[str]) -> dict[str, Any]:
    """Aggregate per-text ``score_text`` results into the TickerSentiment shape.

    Returns a dict mirroring the field layout declared in
    ``backend/social_flow_pipeline.py::TickerSentiment`` (lines 145-160):

        ticker: str
        tweet_count: int
        avg_vader: float             (mean VADER compound across texts)
        avg_textblob: float          (mean TextBlob polarity across texts)
        bullish_count: int           (count where label='positive')
        bearish_count: int           (count where label='negative')
        neutral_count: int           (count where label='neutral')
        sentiment_label: str         ('positive' if bullish>bearish, etc.)
        confidence: float            (fraction of non-neutral out of total)
        top_tweets: list[dict]       (3 highest-magnitude-polarity payloads)

    Edge cases:
      * Empty list / non-list input → zero-filled dict with
        ``sentiment_label='neutral'``.
      * Mixed (positive/negative/neutral/unavailable) labels aggregate
        via simple counts — the agreement gate is per-text and does not
        escalate to a stronger ticker-level filter.
    """
    empty: dict[str, Any] = {
        "ticker": "",
        "tweet_count": 0,
        "avg_vader": 0.0,
        "avg_textblob": 0.0,
        "bullish_count": 0,
        "bearish_count": 0,
        "neutral_count": 0,
        "sentiment_label": "neutral",
        "confidence": 0.0,
        "top_tweets": [],
    }
    if not isinstance(texts, list) or not texts:
        return empty

    scored: list[dict[str, Any]] = []
    vader_scores: list[float] = []
    textblob_scores: list[float] = []
    bullish_count = bearish_count = neutral_count = 0

    # Single-dispatch path: each text triggers EXACTLY ONE call to
    # _analyze_vader and EXACTLY ONE call to _analyze_textblob (previously 2x each
    # via score_text + supplemental extract). The label and avg_polarity are
    # derived inline from the per-model scores so callers paying the cost get
    # both the per-model means AND the agreement-gate label in one pass.
    for i, t in enumerate(texts):
        cleaned = clean_text_sentiment(clean_text(t))
        vader_compound, _ = _analyze_vader(cleaned)
        tb_polarity, tb_subjectivity = _analyze_textblob(cleaned)
        label = _label_from_agreement(
            vader_compound, tb_polarity,
            VADER_AVAILABLE, TEXTBLOB_AVAILABLE,
        )
        if VADER_AVAILABLE and TEXTBLOB_AVAILABLE:
            avg = (tb_polarity + vader_compound) / 2.0
        elif VADER_AVAILABLE:
            avg = vader_compound
        elif TEXTBLOB_AVAILABLE:
            avg = tb_polarity
        else:
            avg = 0.0
        scored.append({
            "index": i,
            "text": t,
            "polarity": round(float(avg), 4),
            "subjectivity": round(float(tb_subjectivity), 4),
            "label": label,
        })
        if VADER_AVAILABLE:
            vader_scores.append(vader_compound)
        if TEXTBLOB_AVAILABLE:
            textblob_scores.append(tb_polarity)
        if label == "positive":
            bullish_count += 1
        elif label == "negative":
            bearish_count += 1
        elif label == "neutral":
            neutral_count += 1
        # "unavailable" doesn't increment any count bucket.

    avg_vader = round(sum(vader_scores) / len(vader_scores), 4) if vader_scores else 0.0
    avg_textblob = round(sum(textblob_scores) / len(textblob_scores), 4) if textblob_scores else 0.0

    # Dominant-label rule: majority of non-neutral votes
    # (matches upstream intuition — bullish count > bearish count → bullish).
    if bullish_count > bearish_count:
        sentiment_label = "positive"
    elif bearish_count > bullish_count:
        sentiment_label = "negative"
    else:
        sentiment_label = "neutral"

    # Confidence fraction = (bullish + bearish) / total (i.e., how much of
    # the corpus express a directional view, not "neutral").
    scored_total = bullish_count + bearish_count
    confidence = round(scored_total / len(texts), 4) if texts else 0.0

    # Top-tweets by absolute polarity (most-polarized first; ties broken
    # by original index).
    def _abs_polarity(s: dict[str, Any]) -> float:
        return abs(s["polarity"])

    top_tweets = sorted(scored, key=_abs_polarity, reverse=True)[:3]

    return {
        "ticker": "",
        "tweet_count": len(texts),
        "avg_vader": avg_vader,
        "avg_textblob": avg_textblob,
        "bullish_count": bullish_count,
        "bearish_count": bearish_count,
        "neutral_count": neutral_count,
        "sentiment_label": sentiment_label,
        "confidence": confidence,
        "top_tweets": top_tweets,
    }
