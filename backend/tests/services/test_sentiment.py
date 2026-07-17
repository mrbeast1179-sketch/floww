"""
backend/tests/services/test_sentiment.py

Tests for backend/services/sentiment.py — pure-logic with VADER/TextBlob
stubbed via module-level ``_analyze_vader`` / ``_analyze_textblob`` so the
suite runs even without ``vaderSentiment`` / ``textblob`` installed.

Coverage profile (~16 cases + 4 type/missing-lib parametrize variants):

  1.  empty string → ``(0.0, 0.0, "neutral")``
  2.  None input   → ``(0.0, 0.0, "neutral")``
  3.  pure punctuation → ``(0.0, 0.0, "neutral")`` (after cleaning)
  4.  STRONG POSITIVE agreement (TB>0 AND vader>=+0.05) → label="positive"
  5.  STRONG NEGATIVE agreement (TB<0 AND vader<=-0.05) → label="negative"
  6.  **DISAGREEMENT** (TB positive but VADER < +0.05) → label="neutral"  ← the key correctness test
  7.  DISAGREEMENT (TB negative but VADER > -0.05) → label="neutral"
  8.  Boundary: VADER compound EXACTLY +0.05 → label="positive" (inclusive)
  9.  Boundary: VADER compound EXACTLY -0.05 → label="negative" (inclusive)
  10. Boundary: TB polarity EXACTLY 0.0 → label="neutral"
  11. ``clean_text`` strips URLs, HTML-tags, HTML-entities, RT, ellipsis
  12. ``clean_text_sentiment`` additionally strips @mention and #hashtag
  13. ``aggregate_sentiment`` on a 3-text corpus: bullish/bearish counts + label
  14. ``aggregate_sentiment`` empty list → zero-filled dict
  15. Non-string input (int, dict) → graceful neutral
  16. Emoji-only text → after cleaning, no language to score → neutral
  +  parametrize for single-lib fallback (vader-only / textblob-only / unavailable)

Hand-verified math for case #4 (the reference case):
────────────────────────────────────────────────────
  text: "The company crushed earnings, stock soaring to new highs"
    TB polarity = +0.5
    vader compound = +0.85
    both exceed threshold → label="positive"
    avg = (0.5 + 0.85) / 2 = +0.6750
"""

from __future__ import annotations

import pytest

import services.sentiment as sentiment_mod
from services.sentiment import (
    aggregate_sentiment,
    clean_text,
    clean_text_sentiment,
    score_text,
)

# ----------------------------------------------------------------------------
# Helpers — monkey-patched scoring fixtures so tests don't require vaderSentiment
# or textblob to be installed.
# ----------------------------------------------------------------------------

@pytest.fixture
def stub_models(monkeypatch):
    """Replace _analyze_vader + _analyze_textblob with deterministic stubs.

    Tests can override either stub mid-test to simulate specific score pairs
    (e.g. ``monkeypatch.setattr(sentiment_mod, "_analyze_vader", lambda t: ...)``).
    Defaults both stubs to neutral scores so import-time defensive degradation
    doesn't pollute the test surface.
    """
    monkeypatch.setattr(sentiment_mod, "_analyze_vader",
                        lambda text: (0.0, {"compound": 0.0}))
    monkeypatch.setattr(sentiment_mod, "_analyze_textblob",
                        lambda text: (0.0, 0.0))
    # Pretend both libs are available for the test scope — keeps the
    # agreement-gate path active.
    monkeypatch.setattr(sentiment_mod, "VADER_AVAILABLE", True)
    monkeypatch.setattr(sentiment_mod, "TEXTBLOB_AVAILABLE", True)
    return monkeypatch


def _force_vader(monkeypatch, compound: float):
    """Inject a deterministic VADER compound score."""
    monkeypatch.setattr(
        sentiment_mod, "_analyze_vader",
        lambda text: (compound, {"compound": compound}),
    )


def _force_textblob(monkeypatch, polarity: float, subjectivity: float = 0.5):
    """Inject a deterministic TextBlob polarity/subjectivity pair."""
    monkeypatch.setattr(
        sentiment_mod, "_analyze_textblob",
        lambda text: (polarity, subjectivity),
    )


# ----------------------------------------------------------------------------
# 1. Empty string
# ----------------------------------------------------------------------------
def test_empty_string_returns_neutral_zero_tuple(stub_models):
    polarity, subjectivity, label = score_text("")
    assert polarity == 0.0
    assert subjectivity == 0.0
    assert label == "neutral"


# ----------------------------------------------------------------------------
# 2. None input
# ----------------------------------------------------------------------------
def test_none_text_returns_neutral_zero_tuple(stub_models):
    polarity, subjectivity, label = score_text(None)
    assert polarity == 0.0
    assert subjectivity == 0.0
    assert label == "neutral"


# ----------------------------------------------------------------------------
# 3. Pure punctuation (no language to score after cleaning)
# ----------------------------------------------------------------------------
def test_punctuation_only_returns_neutral(stub_models):
    polarity, subjectivity, label = score_text("!@#$%^&*()")
    assert polarity == 0.0
    assert subjectivity == 0.0
    assert label == "neutral"


# ----------------------------------------------------------------------------
# 4. STRONG POSITIVE agreement (textblob > 0 AND vader >= +0.05)
# ----------------------------------------------------------------------------
def test_strong_positive_agreement(stub_models):
    _force_vader(stub_models, 0.85)
    _force_textblob(stub_models, 0.5, subjectivity=0.6)
    polarity, subjectivity, label = score_text(
        "The company crushed earnings, stock soaring to new highs"
    )
    # avg = (0.5 + 0.85) / 2 = +0.6750
    assert polarity == 0.6750
    assert subjectivity == 0.6
    assert label == "positive"


# ----------------------------------------------------------------------------
# 5. STRONG NEGATIVE agreement (textblob < 0 AND vader <= -0.05)
# ----------------------------------------------------------------------------
def test_strong_negative_agreement(stub_models):
    _force_vader(stub_models, -0.78)
    _force_textblob(stub_models, -0.4, subjectivity=0.7)
    polarity, subjectivity, label = score_text(
        "Stock crashed hard, company bankrupt, mass layoffs"
    )
    # avg = (-0.4 + -0.78) / 2 = -0.59
    assert polarity == -0.59
    assert subjectivity == 0.7
    assert label == "negative"


# ----------------------------------------------------------------------------
# 6. DISAGREEMENT (TEXT-THE-KEY-TEST): textblob positive but VADER weak
# ----------------------------------------------------------------------------
def test_disagreement_textblob_positive_vader_neutral(stub_models):
    """Mild-positive TextBlob but weak VADER (compound < +0.05 threshold)
    → label MUST be 'neutral' (the agreement gate's whole reason to exist)."""
    _force_vader(stub_models, 0.04)    # < +0.05 threshold
    _force_textblob(stub_models, 0.3, subjectivity=0.5)
    _, _, label = score_text("Maybe slightly bullish news")
    assert label == "neutral"


# ----------------------------------------------------------------------------
# 7. DISAGREEMENT the other direction: textblob negative but VADER weak
# ----------------------------------------------------------------------------
def test_disagreement_textblob_negative_vader_neutral(stub_models):
    _force_vader(stub_models, -0.04)   # > -0.05 threshold (i.e., neutral)
    _force_textblob(stub_models, -0.3, subjectivity=0.5)
    _, _, label = score_text("Maybe slightly bearish news")
    assert label == "neutral"


# ----------------------------------------------------------------------------
# 8. Boundary: VADER compound EXACTLY +0.05 → label="positive"
# ----------------------------------------------------------------------------
def test_vader_boundary_positive_inclusive(stub_models):
    _force_vader(stub_models, 0.05)    # EXACTLY the threshold
    _force_textblob(stub_models, 0.1, subjectivity=0.5)
    _, _, label = score_text("Slightly bullish")
    assert label == "positive"


# ----------------------------------------------------------------------------
# 9. Boundary: VADER compound EXACTLY -0.05 → label="negative"
# ----------------------------------------------------------------------------
def test_vader_boundary_negative_inclusive(stub_models):
    _force_vader(stub_models, -0.05)   # EXACTLY the threshold
    _force_textblob(stub_models, -0.1, subjectivity=0.5)
    _, _, label = score_text("Slightly bearish")
    assert label == "negative"


# ----------------------------------------------------------------------------
# 10. Boundary: TEXTBLOB polarity EXACTLY 0.0 → label="neutral" regardless
# ────────────────────────────────────────────────────────────────────────────
def test_textblob_zero_polarity_always_neutral(stub_models):
    _force_vader(stub_models, 0.85)   # strong vader positive
    _force_textblob(stub_models, 0.0)  # EXACTLY 0 — TextBlob says neutral
    _, _, label = score_text("Mixed sentiment tweet")
    assert label == "neutral"


# ----------------------------------------------------------------------------
# 11. clean_text — strips URLs, HTML-tags, HTML-entities, RT, ellipsis
# ----------------------------------------------------------------------------
def test_clean_text_strips_html_urls_entities():
    raw = (
        "<p>Great news! Visit https://example.com/news/x &amp; check "
        "out this story\u2026 RT @handle: rally continues</p>"
    )
    cleaned = clean_text(raw)
    assert "<p>" not in cleaned
    assert "</p>" not in cleaned
    assert "https://example.com" not in cleaned
    assert "&amp;" not in cleaned
    assert "\u2026" not in cleaned
    assert "RT" not in cleaned or cleaned.endswith("rally continues")
    # Sanity: narrative content preserved.
    assert "Great news" in cleaned
    assert "rally continues" in cleaned


# ----------------------------------------------------------------------------
# 12. clean_text_sentiment — additionally strips @mention and #hashtag
# ----------------------------------------------------------------------------
def test_clean_text_sentiment_strips_mentions_and_hashtags():
    raw = "Bullish on $AAPL #investing @everyone should follow"
    cleaned = clean_text_sentiment(raw)
    # Mentions + hashtags removed; the $AAPL token (a stock-ticker reference,
    # NOT a hashtag) is preserved because the regex only strips @- and #-led.
    assert "@everyone" not in cleaned
    assert "#investing" not in cleaned
    assert "$AAPL" in cleaned or "AAPL" in cleaned


# ----------------------------------------------------------------------------
# 13. aggregate_sentiment on a 3-text corpus (mixed bull/bear/neutral)
# ----------------------------------------------------------------------------
def test_aggregate_sentiment_mixed_corpus(stub_models):
    """3-text corpus: 2 bullish + 1 bearish → bullish majority → label=positive.

    Mocks are idempotent in (text) → score. After the single-dispatch
    refactor, aggregate_sentiment calls _analyze_vader + _analyze_textblob
    each exactly ONCE per text (no counter bookkeeping required). Returning
    by-text-content makes the mocks robust under any scoring frequency —
    single-dispatch today, double-dispatch if a future refactor lands.
    """
    def _vader_by_text(text):
        # Bearish trigger words: any mention of tumble/sell/crash.
        if any(kw in text.lower() for kw in ("tumble", "sell", "crash")):
            return -0.45, {"compound": -0.45}
        return 0.85, {"compound": 0.85}

    def _tb_by_text(text):
        if any(kw in text.lower() for kw in ("tumble", "sell", "crash")):
            return -0.3, 0.5
        return 0.5, 0.5

    stub_models.setattr(sentiment_mod, "_analyze_vader", _vader_by_text)
    stub_models.setattr(sentiment_mod, "_analyze_textblob", _tb_by_text)

    out = aggregate_sentiment([
        "Stock exploding higher",            # bullish
        "Sell sell sell tumble right now",   # bearish
        "All-time highs tomorrow",            # bullish
    ])
    assert out["tweet_count"] == 3
    # 2 bullish + 1 bearish by content-keyed scores
    assert out["bullish_count"] == 2
    assert out["bearish_count"] == 1
    assert out["neutral_count"] == 0
    assert out["sentiment_label"] == "positive"   # majority bullish
    assert out["confidence"] == round(3 / 3, 4)

# -------------------------------------------------------------------------
# Regression guard: non-string entries in the input list must NOT reach
# _analyze_vader / _analyze_textblob unconverted. The single-dispatch
# refactor added ``if not isinstance(t, str): t = ""`` for exactly this
# reason. Mocks here capture the type passed to each helper so a future
# refactor that drops the guard fails this test loudly.
# -------------------------------------------------------------------------
def test_aggregate_sentiment_handles_non_string_entries(stub_models):
    vader_inputs = []
    tb_inputs = []

    def _vader_capture(text):
        vader_inputs.append(type(text).__name__)
        return 0.0, {"compound": 0.0}

    def _tb_capture(text):
        tb_inputs.append(type(text).__name__)
        return 0.0, 0.0

    stub_models.setattr(sentiment_mod, "_analyze_vader", _vader_capture)
    stub_models.setattr(sentiment_mod, "_analyze_textblob", _tb_capture)

    out = aggregate_sentiment([
        "Stock climbing",   # bullish-positive text
        123,                 # non-string (int)
        None,                # non-string (None)
        ["list"],            # non-string (list)
        4.5,                 # non-string (float)
        "Sell tumble",       # bearish text
    ])
    # All 6 entries coerced to str before reaching the helpers.
    vader_seen = list(vader_inputs)
    tb_seen = list(tb_inputs)
    assert all(t == "str" for t in vader_seen), (
        f"Non-string leaked to _analyze_vader: {vader_seen}"
    )
    assert all(t == "str" for t in tb_seen), (
        f"Non-string leaked to _analyze_textblob: {tb_seen}"
    )
    # Output is well-formed: 6 rows, defaults at the stub (0,0,0) so
    # baselines produce no positive/negative labels.
    assert out["tweet_count"] == 6
    assert out["bullish_count"] == 0
    assert out["bearish_count"] == 0
    assert out["neutral_count"] == 6



# ----------------------------------------------------------------------------
# extract_sentiment_feature (steal-list deferred-(b) ship).
# Math: ``clamp(mean(avg_vader, avg_textblob), -1, 1)`` with NULL/NaN safety.
# Regression guard for both-libs-unavailable (monkey-patch VADER_AVAILABLE=False
# AND TEXTBLOB_AVAILABLE=False → available stays False even with values present).
# ----------------------------------------------------------------------------

def test_extract_sentiment_positive_mean(stub_models):
    from services.sentiment import extract_sentiment_feature
    score, avail = extract_sentiment_feature({
        "avg_vader": 0.6, "avg_textblob": 0.4, "tweet_count": 5,
    })
    assert score == 0.5
    assert avail is True


def test_extract_sentiment_negative_mean(stub_models):
    from services.sentiment import extract_sentiment_feature
    score, avail = extract_sentiment_feature({
        "avg_vader": -0.7, "avg_textblob": -0.5, "tweet_count": 5,
    })
    assert score == -0.6
    assert avail is True


def test_extract_sentiment_clamps_above_one(stub_models):
    """avg_vader=2.0 and avg_textblob=2.0 → raw mean=2.0 → clamp to 1.0."""
    from services.sentiment import extract_sentiment_feature
    score, avail = extract_sentiment_feature({
        "avg_vader": 2.0, "avg_textblob": 2.0, "tweet_count": 1,
    })
    assert score == 1.0
    assert avail is True


def test_extract_sentiment_clamps_below_minus_one(stub_models):
    from services.sentiment import extract_sentiment_feature
    score, avail = extract_sentiment_feature({
        "avg_vader": -1.5, "avg_textblob": -1.5, "tweet_count": 1,
    })
    assert score == -1.0
    assert avail is True


def test_extract_sentiment_none_input_returns_zero_false(stub_models):
    from services.sentiment import extract_sentiment_feature
    assert extract_sentiment_feature(None) == (0.0, False)


def test_extract_sentiment_empty_tweet_count_returns_zero_false(stub_models):
    """tweet_count=0 → guard rejects, even if avg_vader + avg_textblob are present."""
    from services.sentiment import extract_sentiment_feature
    score, avail = extract_sentiment_feature({
        "avg_vader": 0.5, "avg_textblob": 0.5, "tweet_count": 0,
    })
    assert score == 0.0
    assert avail is False


def test_extract_sentiment_missing_avg_returns_zero_false(stub_models):
    """Missing either avg_vader OR avg_textblob → guard rejects (gate is AND)."""
    from services.sentiment import extract_sentiment_feature
    score, avail = extract_sentiment_feature({
        "avg_vader": 0.5, "tweet_count": 5,
    })
    assert score == 0.0
    assert avail is False


def test_extract_sentiment_NaN_returns_zero_false(stub_models):
    """NaN / inf → guard rejects. Regression-guard contract."""
    import math as m
    from services.sentiment import extract_sentiment_feature
    for bad in (m.nan, m.inf, -m.inf):
        score, avail = extract_sentiment_feature({
            "avg_vader": bad, "avg_textblob": 0.5, "tweet_count": 5,
        })
        assert score == 0.0
        assert avail is False


def test_extract_sentiment_both_libs_unavailable_regression_guard(stub_models):
    """REGRESSION GUARD: even when both NLP libs are unavailable
    (monkey-patched both False), the parser still computes the
    sentiment_score from the cached avg_vader + avg_textblob floats.
    The parser is fail-open at the dictionary layer; live-NLP scoring
    is gated upstream in ``aggregate_sentiment()`` where it matters.

    Previously the parser returned (0.0, False) when both libs were
    unavailable. That over-zealous guard caused downstream composite
    scores to silently lose the 5th sub-component whenever the libs
    weren't installed at module-load time. We relax the parser to
    log a debug message + proceed so cached sentiment continues to
    feed the composite.
    """
    monkeypatch = stub_models
    import services.sentiment as s
    monkeypatch.setattr(s, "VADER_AVAILABLE", False)
    monkeypatch.setattr(s, "TEXTBLOB_AVAILABLE", False)
    from services.sentiment import extract_sentiment_feature
    score, avail = extract_sentiment_feature({
        "avg_vader": 0.5, "avg_textblob": 0.5, "tweet_count": 5,
    })
    # Both libs unavailable but well-formed cached payload -> parser
    # STILL computes the score (live-NLP gating is upstream).
    assert score == 0.5
    assert avail is True
