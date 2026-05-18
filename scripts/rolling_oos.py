#!/usr/bin/env python3
"""
scripts/rolling_oos.py

Rolling out-of-sample evaluator for a shipped model.

The walk-forward CV in `scripts/train_spy_model.py` produces a fold-aggregated
Sharpe, which can be high even if one or two folds are outlier-good (e.g. a
single backward-fitted regime). Before trusting a model, we need to see the
per-fold Sharpe distribution over the MOST RECENT N trading days — that's
what tells us whether the edge is current or stale.

Usage:
    python scripts/rolling_oos.py --ticker IWM --days 250 --fold-size 50

Output: reports/rolling_oos_<ticker>_<YYYYMMDDTHHMMSS>.md with:
  - Per-fold metrics (accuracy, F1, Sharpe, n)
  - Aggregate metrics
  - Per-fold Sharpe spread (mean, std, min, max)
  - Verdict: PASS (Sharpe ≥ 1.0 in all folds and overall ≥ 2.0) /
             SUSPECT (overall ≥ 1.0 but some fold < 0.5) /
             FAIL (overall < 1.0 or any fold ≤ 0)

No retraining. Uses the existing model + scaler from `models/` (quarantine-guarded).

Design: pure function `evaluate_rolling_oos(...)` takes a feature DataFrame +
loaded model + scaler, so it's unit-testable with synthetic data. The CLI
wraps it with Mongo loading.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from services.ml.gate import compute_trading_sharpe  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("rolling_oos")

REPORTS_DIR = REPO_ROOT / "reports"
MODELS_DIR = REPO_ROOT / "models"


# ────────────────────────────────────────────────────────────────────────────
# Core: rolling-OOS evaluation (pure function, unit-testable)
# ────────────────────────────────────────────────────────────────────────────


def _build_feature_matrix(
    df: pd.DataFrame,
    feature_names: List[str],
) -> np.ndarray:
    """Project a feature DataFrame into the model's expected feature order."""
    if not feature_names:
        ignore = {
            "_id", "ticker", "date", "feature_version", "_computed_at",
        }
        feature_names = sorted(
            c for c in df.columns
            if c not in ignore
            and not c.startswith("target_")
            and pd.api.types.is_numeric_dtype(df[c])
        )
    missing = [n for n in feature_names if n not in df.columns]
    for n in missing:
        df[n] = 0.0
    X = df[feature_names].fillna(0.0).values.astype(float)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    return X


def _binary_target(df: pd.DataFrame) -> np.ndarray:
    """Construct the same binary target the model was trained on:
    1 if target_directional_move > 0 else 0.
    """
    raw = df["target_directional_move"].fillna(0).values
    return (raw > 0).astype(int)


def _make_folds(
    n: int, fold_size: int, embargo: int = 0
) -> List[Tuple[int, int]]:
    """Slice the last `n` rows into contiguous folds of size `fold_size`.

    Returns list of `(start, end)` index pairs (end-exclusive) over a
    `range(n)` index. If `embargo > 0`, each fold starts `embargo` rows after
    the previous fold's end (gap to suppress leakage when targets overlap).
    """
    folds: List[Tuple[int, int]] = []
    start = 0
    while start + fold_size <= n:
        folds.append((start, start + fold_size))
        start += fold_size + embargo
    return folds


def evaluate_rolling_oos(
    df: pd.DataFrame,
    model: Any,
    scaler: Any,
    feature_names: List[str],
    fold_size: int = 50,
    embargo: int = 0,
) -> Dict[str, Any]:
    """Evaluate `model` on the last `len(df)` rows of `df`, split into folds.

    `df` must be sorted by date ascending and contain both feature columns
    (per `feature_names`) and `target_directional_move`. Caller is
    responsible for selecting "the last N days" before passing.

    Returns:
        {
            "n_total": int,
            "folds": [
                {"start": int, "end": int, "n": int,
                 "accuracy": float, "f1": float, "sharpe": float},
                ...
            ],
            "aggregate": {"accuracy": float, "f1": float, "sharpe": float, "n": int},
            "spread": {"mean_sharpe": float, "std_sharpe": float,
                       "min_sharpe": float, "max_sharpe": float},
            "verdict": "PASS" | "SUSPECT" | "FAIL",
            "verdict_reason": str,
        }
    """
    n_total = len(df)
    X_all = _build_feature_matrix(df, feature_names)
    y_all = _binary_target(df)

    try:
        X_scaled = scaler.transform(X_all)
        X_scaled = np.nan_to_num(X_scaled, nan=0.0)
    except Exception as exc:
        return {
            "n_total": n_total,
            "folds": [],
            "aggregate": {},
            "spread": {},
            "verdict": "FAIL",
            "verdict_reason": f"scaler.transform failed: {exc}",
        }

    fold_results: List[Dict[str, Any]] = []
    all_preds: List[int] = []
    all_actuals: List[int] = []

    for start, end in _make_folds(n_total, fold_size, embargo=embargo):
        Xf = X_scaled[start:end]
        yf = y_all[start:end]
        if len(yf) < 2:
            continue
        try:
            preds = model.predict(Xf).astype(int)
        except Exception as exc:
            fold_results.append({
                "start": start, "end": end, "n": int(len(yf)),
                "accuracy": 0.0, "f1": 0.0, "sharpe": 0.0,
                "error": f"predict failed: {exc}",
            })
            continue

        acc = float(np.mean(preds == yf)) if len(yf) > 0 else 0.0
        f1 = _f1_binary(preds, yf)
        sharpe = compute_trading_sharpe(preds.tolist(), yf.tolist())
        fold_results.append({
            "start": int(start), "end": int(end), "n": int(len(yf)),
            "accuracy": acc, "f1": f1, "sharpe": float(sharpe),
        })
        all_preds.extend(preds.tolist())
        all_actuals.extend(yf.tolist())

    sharpes = [f["sharpe"] for f in fold_results if "error" not in f]
    if not sharpes:
        return {
            "n_total": n_total,
            "folds": fold_results,
            "aggregate": {},
            "spread": {},
            "verdict": "FAIL",
            "verdict_reason": "no valid folds",
        }

    agg_acc = float(np.mean(np.array(all_preds) == np.array(all_actuals))) if all_preds else 0.0
    agg_sharpe = compute_trading_sharpe(all_preds, all_actuals)
    agg_f1 = _f1_binary(np.array(all_preds), np.array(all_actuals))

    spread = {
        "mean_sharpe": float(np.mean(sharpes)),
        "std_sharpe": float(np.std(sharpes)),
        "min_sharpe": float(np.min(sharpes)),
        "max_sharpe": float(np.max(sharpes)),
    }

    verdict, reason = _verdict_from_results(agg_sharpe, sharpes)

    return {
        "n_total": n_total,
        "folds": fold_results,
        "aggregate": {
            "accuracy": agg_acc,
            "f1": agg_f1,
            "sharpe": float(agg_sharpe),
            "n": len(all_preds),
        },
        "spread": spread,
        "verdict": verdict,
        "verdict_reason": reason,
    }


def _verdict_from_results(agg_sharpe: float, fold_sharpes: List[float]) -> Tuple[str, str]:
    """Three-bucket verdict, conservative on the downside."""
    if agg_sharpe < 1.0 or any(s <= 0 for s in fold_sharpes):
        return "FAIL", (
            f"aggregate Sharpe {agg_sharpe:.2f} < 1.0 "
            f"or fold contains non-positive Sharpe (min={min(fold_sharpes):.2f})"
        )
    if any(s < 0.5 for s in fold_sharpes) or (max(fold_sharpes) - min(fold_sharpes)) > 4.0:
        return "SUSPECT", (
            f"per-fold Sharpe spread is wide "
            f"(min={min(fold_sharpes):.2f}, max={max(fold_sharpes):.2f}); "
            f"aggregate {agg_sharpe:.2f} but inconsistent"
        )
    if agg_sharpe >= 2.0 and all(s >= 1.0 for s in fold_sharpes):
        return "PASS", (
            f"aggregate Sharpe {agg_sharpe:.2f} >= 2.0; "
            f"all {len(fold_sharpes)} folds >= 1.0"
        )
    return "SUSPECT", (
        f"aggregate Sharpe {agg_sharpe:.2f} between 1.0 and 2.0; "
        f"per-fold sharpes {fold_sharpes}"
    )


def _f1_binary(preds: np.ndarray, actuals: np.ndarray) -> float:
    """Binary F1 with positive class = 1. Returns 0 on degenerate input."""
    preds = np.asarray(preds, dtype=int)
    actuals = np.asarray(actuals, dtype=int)
    tp = int(np.sum((preds == 1) & (actuals == 1)))
    fp = int(np.sum((preds == 1) & (actuals == 0)))
    fn = int(np.sum((preds == 0) & (actuals == 1)))
    if tp == 0:
        return 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    if precision + recall == 0:
        return 0.0
    return float(2 * precision * recall / (precision + recall))


# ────────────────────────────────────────────────────────────────────────────
# Report rendering
# ────────────────────────────────────────────────────────────────────────────


def render_report(ticker: str, model_path: str, result: Dict[str, Any]) -> str:
    """Render the evaluation result as markdown."""
    lines: List[str] = []
    lines.append(f"# Rolling OOS — {ticker} {Path(model_path).name}")
    lines.append(f"_Generated: {datetime.now(timezone.utc).isoformat()}_")
    lines.append("")
    lines.append(f"**VERDICT: {result['verdict']}** — {result['verdict_reason']}")
    lines.append("")

    if result.get("aggregate"):
        agg = result["aggregate"]
        lines.append("## Aggregate (over all folds)")
        lines.append("")
        lines.append(f"- n: {agg.get('n', 0)}")
        lines.append(f"- accuracy: {agg.get('accuracy', 0):.3f}")
        lines.append(f"- F1: {agg.get('f1', 0):.3f}")
        lines.append(f"- Sharpe: {agg.get('sharpe', 0):.3f}")
        lines.append("")

    if result.get("spread"):
        s = result["spread"]
        lines.append("## Per-fold Sharpe spread")
        lines.append("")
        lines.append(f"- mean: {s.get('mean_sharpe', 0):.3f}")
        lines.append(f"- std:  {s.get('std_sharpe', 0):.3f}")
        lines.append(f"- min:  {s.get('min_sharpe', 0):.3f}")
        lines.append(f"- max:  {s.get('max_sharpe', 0):.3f}")
        lines.append("")

    lines.append("## Per-fold metrics")
    lines.append("")
    lines.append("| Fold | start | end | n | Accuracy | F1 | Sharpe |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for i, f in enumerate(result.get("folds", [])):
        err = f.get("error")
        if err:
            lines.append(f"| {i + 1} | {f.get('start')} | {f.get('end')} | {f.get('n')} | error: {err} | | |")
        else:
            lines.append(
                f"| {i + 1} | {f.get('start')} | {f.get('end')} | {f.get('n')} | "
                f"{f.get('accuracy', 0):.3f} | {f.get('f1', 0):.3f} | "
                f"{f.get('sharpe', 0):.3f} |"
            )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("Methodology: no retraining. The active model + scaler are loaded "
                 "from `models/` (with the `_quarantine` load-guard) and evaluated "
                 "on the last N rows of `ml_features` for the ticker. Folds are "
                 "contiguous windows of `fold_size` rows. Sharpe uses the same "
                 "`compute_trading_sharpe` helper as the training pipeline "
                 "(`services.ml.gate.compute_trading_sharpe`).")
    return "\n".join(lines)


# ────────────────────────────────────────────────────────────────────────────
# CLI / Mongo loader
# ────────────────────────────────────────────────────────────────────────────


def _load_model_and_scaler(ticker: str, version: str = "v1.0"):
    """Load model + scaler from MODELS_DIR with quarantine guard."""
    import joblib

    model_path = MODELS_DIR / f"{ticker}_direction_{version}.joblib"
    scaler_path = MODELS_DIR / f"{ticker}_scaler_{version}.joblib"
    meta_path = MODELS_DIR / f"{ticker}_meta_{version}.json"

    for p in (model_path, scaler_path, meta_path):
        assert "_quarantine" not in str(p), f"refused to load quarantined: {p}"

    if not model_path.exists():
        raise FileNotFoundError(f"model missing: {model_path} (quarantined?)")
    if not scaler_path.exists():
        raise FileNotFoundError(f"scaler missing: {scaler_path}")

    model = joblib.load(model_path)
    scaler = joblib.load(scaler_path)

    feature_names: List[str] = []
    if meta_path.exists():
        with open(meta_path) as fh:
            meta = json.load(fh)
        feature_names = list(meta.get("feature_names") or [])

    return model, scaler, feature_names, model_path


def _load_features_from_mongo(ticker: str, days: int) -> pd.DataFrame:
    """Load the most recent `days` feature rows for `ticker` from Mongo."""
    from pymongo import MongoClient
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / "backend" / ".env")

    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "confluence_decoder")
    client = MongoClient(url, serverSelectionTimeoutMS=10_000)
    db = client[db_name]
    cursor = (
        db["ml_features"]
        .find({"ticker": ticker})
        .sort("date", -1)
        .limit(days)
    )
    docs = list(cursor)
    client.close()
    if not docs:
        raise ValueError(f"No features found for {ticker}")
    df = pd.DataFrame(docs).sort_values("date").reset_index(drop=True)
    return df


def main() -> int:
    parser = argparse.ArgumentParser(description="Rolling-OOS evaluator for a shipped model")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--days", type=int, default=250,
                        help="Number of most recent feature rows to evaluate over")
    parser.add_argument("--fold-size", type=int, default=50,
                        help="Rows per fold; fewer folds = wider per-fold Sharpe")
    parser.add_argument("--version", default="v1.0")
    parser.add_argument("--embargo", type=int, default=0)
    args = parser.parse_args()

    log.info(f"Rolling OOS — {args.ticker} (last {args.days} rows, fold size {args.fold_size})")

    model, scaler, feature_names, model_path = _load_model_and_scaler(args.ticker, args.version)
    log.info(f"Loaded model: {model_path}")

    df = _load_features_from_mongo(args.ticker, args.days)
    log.info(f"Loaded {len(df)} feature rows")

    result = evaluate_rolling_oos(
        df, model, scaler, feature_names,
        fold_size=args.fold_size,
        embargo=args.embargo,
    )
    log.info(f"Verdict: {result['verdict']} — {result['verdict_reason']}")

    REPORTS_DIR.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = REPORTS_DIR / f"rolling_oos_{args.ticker}_{ts}.md"
    report_path.write_text(render_report(args.ticker, str(model_path), result))
    log.info(f"Wrote: {report_path}")

    return 0 if result["verdict"] in ("PASS", "SUSPECT") else 1


if __name__ == "__main__":
    raise SystemExit(main())
