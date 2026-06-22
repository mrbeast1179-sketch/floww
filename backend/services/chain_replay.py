"""
backend/services/chain_replay.py

Chain Replay service — rolling-buffer history of the *Composite Flow
Score* + sub-scores per symbol.

Once a tradable session has been running for any nontrivial window,
the user wants to scrub backwards in time and watch the entire
analytics stack evolve together:

  * Composite Flow Score (0..100)
  * Sub-scores (illiquidity, toxicity, dislocation, direction)
  * Components (Amihud normaliser, Kyle's λ normaliser, VPIN raw,
                 HMM regime string, OFI aggregate)
  * n_obs_min, is_warming

This service is the natural "engineering synthesis" step after the
seven academic-paper services and the Composite synthesiser were
wired into Flowseeker Pro. Pure-Python only — no torch / numba /
scipy (Round-9 freeze rule).

Architecture
------------

* **Push-on-composite-fetch** (Option A from the design proposal):
  the 30-second polling cadence from the UI already calls
  ``/api/flowseeker/composite/{symbol}`` every cycle. We siphon the
  computed output into a per-symbol rolling buffer at that point.
  No background tasks, no desynchronised snapshot states.

* **Rolling buffer**: ``collections.deque(maxlen=240)`` per symbol
  ≈ 2 hours of history at 30-second polling. Memory footprint is
  ~64 symbols × 240 dicts ≈ 15k dicts (negligible).

* **FIFO cap on symbol-pool**: bounded to ``_REPLAY_STATE_MAX`` (64)
  via the same LRU-ish insertion-order evict pattern used by the
  OFI / Regime / VPIN / Kyle / Amihud caches in
  :mod:`backend.routes.flowseeker`.

Snapshot schema
---------------

::

    {
        "ts":            "YYYY-MM-DDTHH:MM:SS.mmmmmm",  # ISO-8601
        "composite":     float,    # 0..100 (or 0 while warming)
        "label":         "HIGH" | "MED" | "WATCH" | "LOW",
        "label_color":   "#...",
        "sub_scores":    dict,     # {illiquidity, toxicity, dislocation, direction}
        "components":    dict,     # {amihud_norm, kyle_norm, vpin, regime, ofi_aggr}
        "n_obs_min":     int,
        "is_warming":    bool,
    }

URL Hack
--------

The snapshot dict that the route layer passes here is the *raw*
output of :func:`CompositeFlowScore.compute` dict + the route
augmentation (``symbol``, ``fetched_at``). We re-key
``fetched_at`` → ``ts`` so the public payload a) is snake_case
keyed, b) doesn't expose our route-internal naming convention.

Usage::

    from services.chain_replay import ChainReplay

    cr = ChainReplay(buffer_size=240)
    cr.push_snapshot(composite_dict)            # idempotent
    out = cr.read_tail(last_n=64)
    tail = cr.read_window(minutes=30)
"""
from __future__ import annotations

import math
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, Iterable, List, Optional


# ─────────────────────────────────────────────────────────────────────
# Constants — sized to match the 30-second polling cadence of the
# Flowseeker Pro UI. Buffer of 240 = 2 hrs of history; default
# ``read_tail(last_n=64)`` = two standard UI windows.
# ─────────────────────────────────────────────────────────────────────

DEFAULT_BUFFER_SIZE = 240        # 2 hours @ 30s polling
DEFAULT_TAIL_N = 64               # Default UI request: 64 most-recent snapshots
DEFAULT_WINDOW_MINUTES = 120      # Default UI request: 2 hours


# ─────────────────────────────────────────────────────────────────────
# Pure helpers
# ─────────────────────────────────────────────────────────────────────

def _validate_snapshot(snap: Dict[str, Any]) -> bool:
    """Basic structural sanity check before pushing into the buffer.

    The route layer calls us with the raw composite output + its own
    ``symbol``/``fetched_at`` augmentations, so we cannot naively use
    ``CompositeFlowScore``'s schema. The minimum invariant is:
    ``composite`` is a finite float and ``label`` is a string.
    """
    if not isinstance(snap, dict):
        return False
    composite = snap.get("composite")
    label = snap.get("label")
    if not isinstance(label, str):
        return False
    if composite is None:
        return False
    try:
        f = float(composite)
    except (TypeError, ValueError):
        return False
    # Reject NaN / ±Inf — both would poison downstream aggregates.
    if math.isnan(f) or math.isinf(f):
        return False
    return True


def _safe_float(v: Any, default: float = 0.0, *, clamp: bool = False) -> float:
    """Coerce ``v`` to ``float`` with three lines of defense:
      1. ``None`` / missing → ``default``
      2. unparseable string / non-numeric → ``default``
      3. NaN / Inf → ``default``

    If ``clamp=True``, negative values are clamped to 0.0 (used for
    sub-scores that are physically bounded at [0, 1]).
    """
    if v is None:
        return float(default)
    try:
        f = float(v)
    except (TypeError, ValueError):
        return float(default)
    if math.isnan(f) or math.isinf(f):
        return float(default)
    if clamp and f < 0.0:
        return 0.0
    return f


def _coerce_snapshot(snap: Dict[str, Any], ts_override: Optional[str] = None) -> Dict[str, Any]:
    """Return a sanitised, snake_case snapshot for the public payload.

    The route calls us with ``Fetched_at`` (camelCase) set by the
    orchestrator. We re-key to ``ts`` so callers see a single,
    consistent timestamp field. All numeric fields are coerced via
    :func:`_safe_float` which guards against ``None``, unparseable
    strings, and NaN/Inf inputs.
    """
    ts = ts_override or snap.get("ts") or snap.get("fetched_at") or datetime.now().isoformat()
    sub = snap.get("sub_scores") or {}
    cmp_ = snap.get("components") or {}
    return {
        "ts":          str(ts),
        "composite":   round(_safe_float(snap.get("composite", 0.0)), 1),
        "label":       str(snap.get("label") or "LOW"),
        "label_color": str(snap.get("label_color") or "#64748b"),
        # Sub-scores are physically bounded at [0, 1] — clamp negatives.
        "sub_scores":  {
            "illiquidity": round(_safe_float(sub.get("illiquidity", 0.0), clamp=True), 3),
            "toxicity":    round(_safe_float(sub.get("toxicity",    0.0), clamp=True), 3),
            "dislocation": round(_safe_float(sub.get("dislocation", 0.0), clamp=True), 3),
            "direction":   round(_safe_float(sub.get("direction",   0.0), clamp=True), 3),
        },
        # Components may legitimately be negative (OFI aggregate can
        # be negative when sell pressure dominates), so do NOT clamp.
        "components":  {
            "amihud_norm": round(_safe_float(cmp_.get("amihud_norm", 0.0)), 3),
            "kyle_norm":   round(_safe_float(cmp_.get("kyle_norm",   0.0)), 3),
            "vpin":        round(_safe_float(cmp_.get("vpin",        0.0)), 3),
            "regime":      str(cmp_.get("regime") or "RANGING"),
            "ofi_aggr":    round(_safe_float(cmp_.get("ofi_aggr",    0.0)), 3),
        },
        "n_obs_min":   int(snap.get("n_obs_min", 0) or 0),
        "is_warming":  bool(snap.get("is_warming", True)),
    }


def _iso_to_dt(s: str) -> datetime:
    """ISO-8601 → datetime. Portable across Python 3.9 → 3.13+.

    Python 3.9 / 3.10 ``datetime.fromisoformat`` does NOT accept a
    fractional-seconds suffix, and 3.9 also won't parse ``Z``. We:
      1. Strip a trailing ``Z`` (-> +00:00 is implicit since the rest
         of our pipeline produces naive timestamps anyway).
      2. Try ``fromisoformat`` as-is (works on 3.11+ incl. fractional).
      3. On ``ValueError`` (3.9 path) **drop** the fractional part
         entirely. Sub-second precision is not needed for window
         filtering — losing it is acceptable.
    """
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1]
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        # Drop the fractional part on 3.9 / 3.10 — rebuilding
        # ``head.123456`` would STILL fail on 3.9 because fromisoformat
        # rejects any fractional-seconds suffix on those versions.
        if "." in s:
            head = s.split(".", 1)[0]
            return datetime.fromisoformat(head)
        raise


# ─────────────────────────────────────────────────────────────────────
# ChainReplay — per-symbol rolling buffer
# ─────────────────────────────────────────────────────────────────────

class ChainReplay:
    """Rolling-buffer snapshot history of the Composite Flow Score."""

    def __init__(self, buffer_size: int = DEFAULT_BUFFER_SIZE):
        if int(buffer_size) < 1:
            raise ValueError("buffer_size must be >= 1")
        self._buffer: Deque[Dict[str, Any]] = deque(maxlen=int(buffer_size))
        self._buffer_size = int(buffer_size)

    # ── State mutators ────────────────────────────────────────────────

    def push_snapshot(self, snap: Dict[str, Any]) -> bool:
        """Append a snapshot IF it passes structural validation.

        Returns ``True`` on append, ``False`` on either invalid input
        OR a still-warming composite (we don't store those — they
        would dominate the buffer with zeros during initialisation).
        """
        if snap is None:
            return False
        if not _validate_snapshot(snap):
            return False
        # Skip warming snapshots so the buffer remains a record of
        # *real* tradable-conviction readings.
        if bool(snap.get("is_warming", True)):
            return False
        coerced = _coerce_snapshot(snap)
        self._buffer.append(coerced)
        return True

    # ── Read-side helpers ─────────────────────────────────────────────

    @property
    def size(self) -> int:
        return len(self._buffer)

    @property
    def capacity(self) -> int:
        return self._buffer_size

    @property
    def is_empty(self) -> bool:
        return len(self._buffer) == 0

    @property
    def latest(self) -> Optional[Dict[str, Any]]:
        if not self._buffer:
            return None
        return self._buffer[-1]

    def __len__(self) -> int:
        return len(self._buffer)

    def __iter__(self):
        return iter(self._buffer)

    def read_all(self) -> List[Dict[str, Any]]:
        """Return the entire buffer in chronological order."""
        return list(self._buffer)

    def read_tail(self, last_n: int = DEFAULT_TAIL_N) -> List[Dict[str, Any]]:
        """Return the LAST ``n`` snapshots in chronological order."""
        n = max(0, int(last_n))
        if n == 0:
            return []
        if n >= len(self._buffer):
            return list(self._buffer)
        # ``deque`` accepts negative startIndex; convert to skip-first.
        return list(self._buffer)[-n:]

    def read_window(self, minutes: int = DEFAULT_WINDOW_MINUTES,
                    now: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Return snapshots within the LAST ``minutes`` minutes.

        ``now`` defaults to ``datetime.now()``; injectable so tests
        can pin a frozen clock.
        """
        if not self._buffer:
            return []
        anchor = now or datetime.now()
        threshold = anchor.timestamp() - float(minutes) * 60.0
        out: List[Dict[str, Any]] = []
        for snap in self._buffer:
            try:
                dt = _iso_to_dt(snap["ts"])
            except (KeyError, ValueError):
                continue
            if dt.timestamp() >= threshold:
                out.append(snap)
        return out

    def read_payload(self,
                     last_n: Optional[int] = None,
                     minutes: Optional[int] = None) -> Dict[str, Any]:
        """Build the public /replay/{symbol} payload.

        ``last_n`` and ``minutes`` are mutually exclusive; pass ``None``
        for whichever one is not in scope. If both are ``None``,
        we return ``read_tail(DEFAULT_TAIL_N)``.
        """
        if minutes is not None:
            snaps = self.read_window(int(minutes))
            window_kind = "minutes"
            window_value = int(minutes)
        elif last_n is not None:
            snaps = self.read_tail(int(last_n))
            window_kind = "tail"
            window_value = int(last_n)
        else:
            snaps = self.read_tail(DEFAULT_TAIL_N)
            window_kind = "tail"
            window_value = DEFAULT_TAIL_N

        return {
            "size":        int(len(self._buffer)),
            "capacity":    int(self._buffer_size),
            "window_kind": window_kind,
            "window_value": int(window_value),
            "snapshots":   snaps,
            "latest":      self.latest,
            "is_empty":    bool(len(self._buffer) == 0),
        }

    def clear(self) -> None:
        """Drop every snapshot (used by ticker-swap if we ever add
        per-ticker re-keying; today we just evict the *whole entry*
        at the route layer on cap overflow)."""
        self._buffer.clear()

    @staticmethod
    def summarise_iterable(snapshots: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        """Return a tiny dict of summary stats over an iterator.

        Useful for the frontend so it doesn't have to re-compute
        min/max itself every render. Pure function. Skips entries
        whose ``composite`` is missing / ``None`` / unparseable, so
        garbage entries don't pollute the aggregates.
        """
        xs: List[float] = []
        labels: List[str] = []
        for s in snapshots:
            raw = s.get("composite", None) if isinstance(s, dict) else None
            if raw is None:
                continue  # missing or explicitly None → don't count
            try:
                f = float(raw)
            except (TypeError, ValueError):
                continue
            if math.isnan(f) or math.isinf(f):
                continue
            xs.append(f)
            labels.append(str(s.get("label") or "LOW") if isinstance(s, dict) else "LOW")
        if not xs:
            return {
                "count": 0, "min": 0.0, "max": 0.0,
                "avg": 0.0, "first_label": None, "last_label": None,
            }
        return {
            "count":       int(len(xs)),
            "min":         float(min(xs)),
            "max":         float(max(xs)),
            "avg":         float(sum(xs) / len(xs)),   # unrounded for math callers
            "first_label": labels[0],
            "last_label":  labels[-1],
        }


__all__ = [
    "ChainReplay",
    "DEFAULT_BUFFER_SIZE",
    "DEFAULT_TAIL_N",
    "DEFAULT_WINDOW_MINUTES",
]
