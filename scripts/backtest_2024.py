#!/usr/bin/env python3
"""
scripts/backtest_2024.py

Walk-forward backtest of the shipped SPY direction model (v1.0) on calendar-year
2024 data, with monthly metric breakdown and a quarterly walk-forward structure.

This script *evaluates* the shipped artifact — it never re-trains. It loads
`models/SPY_direction_v1.0.joblib` and `models/SPY_scaler_v1.0.joblib`, refuses
to load anything under `_quarantine/`, pulls SPY `ml_features` for 2024 from
MongoDB, joins next-day outcomes from `gex_llm_patterns_outcomes` (with an
`ml_features.target_*` fallback for any missing dates), and produces a markdown
report at `reports/backtest_2024.md`.

Metrics computed per calendar month and overall:
  - precision, recall, F1 (positive class = directional move up)
  - accuracy
  - hit rate (signed prediction matching signed outcome direction)
  - profit factor (sum of winning P&L / sum of losing P&L, signed by prediction)
  - n_predictions

Walk-forward structure: for each calendar quarter (Q1..Q4), we re-evaluate the
SAME shipped model on test=quarter data. We do NOT re-train; the spec mandates
evaluating the shipped artifact end-to-end. The four quarters serve as the
walk-forward partition.

Verdict rules:
  - SHIP         : profit_factor >= 1.5 AND accuracy >= 0.55 AND n >= 60
  - INVESTIGATE  : profit_factor >= 1.0 AND accuracy >= 0.50
  - REJECT       : otherwise (or insufficient data)
Note: because the shipped artifact was fit on these 167 rows (see
`models/SPY_meta_v1.0.json`), the headline numbers are an IN-SAMPLE check on the
deployed pickle. We surface that caveat prominently in the report so downstream
readers cannot mistake it for out-of-sample evidence.

Exit codes: 0 on success (report written), non-zero on hard failure
(no data, missing model artifact, schema mismatch).
"""

from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import joblib
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from pymongo import MongoClient

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / "backend" / ".env")
load_dotenv()  # also try repo root .env, harmless if absent

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "confluence_decoder")

MODELS_DIR = REPO_ROOT / "models"
REPORTS_DIR = REPO_ROOT / "reports"
MODEL_PATH = MODELS_DIR / "SPY_direction_v1.0.joblib"
SCALER_PATH = MODELS_DIR / "SPY_scaler_v1.0.joblib"
META_PATH = MODELS_DIR / "SPY_meta_v1.0.json"

START_DATE = "2024-01-01"
END_DATE = "2025-01-01"  # exclusive upper bound

VERDICT_SHIP_PF = 1.5
VERDICT_SHIP_ACC = 0.55
VERDICT_INVESTIGATE_PF = 1.0
VERDICT_INVESTIGATE_ACC = 0.50
VERDICT_SHIP_MIN_N = 60


def load_model_artifact() -> tuple[Any, Any, dict]:
    """Load joblib model + scaler, refusing anything in _quarantine/."""
    for p in (MODEL_PATH, SCALER_PATH):
        assert "_quarantine" not in str(p), f"refused to load quarantined artifact: {p}"
        if not p.exists():
            raise FileNotFoundError(f"missing model artifact: {p}")
    model = joblib.load(MODEL_PATH)
    scaler = joblib.load(SCALER_PATH)
    if not META_PATH.exists():
        raise FileNotFoundError(f"missing model metadata: {META_PATH}")
    meta = json.loads(META_PATH.read_text())
    if "feature_names" not in meta:
        raise ValueError("model meta missing feature_names")
    return model, scaler, meta


def load_2024_features(client: MongoClient, ticker: str) -> pd.DataFrame:
    """Load SPY ml_features rows for 2024 inclusive of 2024-01-01..2024-12-31."""
    db = client[DB_NAME]
    cur = db["ml_features"].find(
        {"ticker": ticker, "date": {"$gte": START_DATE, "$lt": END_DATE}}
    ).sort("date", 1)
    docs = list(cur)
    if not docs:
        return pd.DataFrame()
    df = pd.DataFrame(docs)
    df = df.sort_values("date").reset_index(drop=True)
    return df


def load_outcomes(client: MongoClient) -> pd.DataFrame:
    """Load gex_llm_patterns_outcomes rows for 2024. These rows are SPY-only by
    convention (see `_source: issue_145_next_day_outcomes_2024`)."""
    db = client[DB_NAME]
    cur = db["gex_llm_patterns_outcomes"].find(
        {"date": {"$gte": START_DATE, "$lt": END_DATE}}
    ).sort("date", 1)
    docs = list(cur)
    if not docs:
        return pd.DataFrame(columns=["date", "directional_move", "return_pct"])
    df = pd.DataFrame(docs)
    keep = ["date", "directional_move", "return_pct"]
    for col in keep:
        if col not in df.columns:
            df[col] = pd.NA
    return df[keep].copy()


def build_feature_matrix(df: pd.DataFrame, feature_names: list[str]) -> np.ndarray:
    """Construct X in the exact column order the model expects."""
    missing = [c for c in feature_names if c not in df.columns]
    if missing:
        raise ValueError(f"ml_features rows missing model columns: {missing[:5]}...")
    X = df[feature_names].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    return np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)


def derive_labels(df: pd.DataFrame, outcomes: pd.DataFrame) -> pd.DataFrame:
    """Attach (label, return_pct, label_source) columns to df.

    Primary source: gex_llm_patterns_outcomes joined on date.
    Fallback: ml_features.target_directional_move / target_return_pct (signed).
    """
    out = df.copy()
    o = outcomes.set_index("date") if not outcomes.empty else None

    labels: list[int] = []
    returns: list[float] = []
    sources: list[str] = []
    for _, row in out.iterrows():
        d = row["date"]
        label_val: Optional[float] = None
        ret_val: Optional[float] = None
        src = "missing"

        if o is not None and d in o.index:
            r = o.loc[d]
            if pd.notna(r.get("directional_move")):
                dm = r["directional_move"]
                if isinstance(dm, str):
                    dm = dm.strip().lower() in ("true", "1", "yes")
                label_val = 1 if bool(dm) else 0
            if pd.notna(r.get("return_pct")):
                try:
                    ret_val = float(r["return_pct"])
                except (TypeError, ValueError):
                    ret_val = None
            if label_val is not None:
                src = "outcomes_collection"

        if label_val is None and "target_directional_move" in row and pd.notna(row["target_directional_move"]):
            # ml_features target_directional_move is already 0/1 signed (1 if up move materialized)
            label_val = 1 if float(row["target_directional_move"]) > 0 else 0
            src = "ml_features_target"
        if ret_val is None and "target_return_pct" in row and pd.notna(row["target_return_pct"]):
            try:
                ret_val = float(row["target_return_pct"])
            except (TypeError, ValueError):
                ret_val = None

        labels.append(int(label_val) if label_val is not None else -1)
        returns.append(float(ret_val) if ret_val is not None else math.nan)
        sources.append(src)

    out["label"] = labels
    out["return_pct"] = returns
    out["label_source"] = sources
    return out


def metrics_for(preds: np.ndarray, labels: np.ndarray, returns: np.ndarray) -> dict:
    """Compute precision/recall/F1/accuracy/hit-rate/profit-factor.

    Conventions:
      - positive class = label 1 (next-day directional up move)
      - "hit rate"     = fraction of predictions whose sign matches the
                         observed signed return (pred=1 → up, pred=0 → down)
      - "profit factor"= sum(P&L | winning trades) / |sum(P&L | losing trades)|
                         where P&L = signed_return if pred=1 else -signed_return
    """
    n = int(len(preds))
    out = {
        "n": n,
        "precision": float("nan"),
        "recall": float("nan"),
        "f1": float("nan"),
        "accuracy": float("nan"),
        "hit_rate": float("nan"),
        "profit_factor": float("nan"),
    }
    if n == 0:
        return out

    preds = np.asarray(preds).astype(int)
    labels = np.asarray(labels).astype(int)
    returns = np.asarray(returns, dtype=float)

    tp = int(np.sum((preds == 1) & (labels == 1)))
    fp = int(np.sum((preds == 1) & (labels == 0)))
    fn = int(np.sum((preds == 0) & (labels == 1)))
    tn = int(np.sum((preds == 0) & (labels == 0)))
    out["accuracy"] = (tp + tn) / n if n > 0 else float("nan")
    out["precision"] = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    out["recall"] = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    if (out["precision"] + out["recall"]) > 0:
        out["f1"] = 2 * out["precision"] * out["recall"] / (out["precision"] + out["recall"])
    else:
        out["f1"] = 0.0

    # Hit rate: signed prediction matches signed outcome
    signed_pred = np.where(preds == 1, 1, -1)
    valid_ret = ~np.isnan(returns)
    if valid_ret.any():
        signed_ret = np.sign(returns[valid_ret])
        # Treat a flat outcome (return==0) as a non-hit (cannot match either sign)
        hits = np.sum(signed_pred[valid_ret] == signed_ret)
        out["hit_rate"] = float(hits) / int(valid_ret.sum())
    else:
        out["hit_rate"] = float("nan")

    # Profit factor: P&L = +ret if pred=1 else -ret
    if valid_ret.any():
        pnl = np.where(preds[valid_ret] == 1, returns[valid_ret], -returns[valid_ret])
        wins = pnl[pnl > 0].sum()
        losses = -pnl[pnl < 0].sum()  # absolute value of losses
        if losses > 0:
            out["profit_factor"] = float(wins / losses)
        elif wins > 0:
            out["profit_factor"] = float("inf")
        else:
            out["profit_factor"] = 0.0
    else:
        out["profit_factor"] = float("nan")

    return out


def verdict_from(overall: dict) -> str:
    """Map overall metrics → SHIP/INVESTIGATE/REJECT."""
    n = overall.get("n", 0)
    acc = overall.get("accuracy")
    pf = overall.get("profit_factor")
    if n < 20 or acc is None or pf is None or (isinstance(acc, float) and math.isnan(acc)):
        return "REJECT"
    pf_eff = pf if not (isinstance(pf, float) and math.isinf(pf)) else 1e9
    if (
        n >= VERDICT_SHIP_MIN_N
        and acc >= VERDICT_SHIP_ACC
        and pf_eff >= VERDICT_SHIP_PF
    ):
        return "SHIP"
    if acc >= VERDICT_INVESTIGATE_ACC and pf_eff >= VERDICT_INVESTIGATE_PF:
        return "INVESTIGATE"
    return "REJECT"


def fmt(v: float, digits: int = 3) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        if math.isnan(v):
            return "—"
        if math.isinf(v):
            return "inf"
        return f"{v:.{digits}f}"
    return str(v)


def run() -> int:
    model, scaler, meta = load_model_artifact()
    feature_names = list(meta["feature_names"])

    client = MongoClient(MONGO_URL)
    try:
        df = load_2024_features(client, "SPY")
        outcomes = load_outcomes(client)
    finally:
        client.close()

    if df.empty:
        print("ERROR: no SPY ml_features rows for 2024 — cannot backtest", file=sys.stderr)
        return 2

    df = derive_labels(df, outcomes)
    df_eval = df[df["label"] >= 0].copy()
    if df_eval.empty:
        print("ERROR: no labeled rows for 2024 (outcomes + targets both missing)", file=sys.stderr)
        return 2

    X = build_feature_matrix(df_eval, feature_names)
    Xs = scaler.transform(X)
    Xs = np.nan_to_num(Xs, nan=0.0, posinf=0.0, neginf=0.0)
    preds = model.predict(Xs).astype(int)
    df_eval = df_eval.copy()
    df_eval["pred"] = preds

    # Per-month rows
    df_eval["_month_str"] = df_eval["date"].str.slice(0, 7)
    monthly_rows: list[tuple[str, dict]] = []
    months = [f"2024-{m:02d}" for m in range(1, 13)]
    for ym in months:
        sub = df_eval[df_eval["_month_str"] == ym]
        if sub.empty:
            monthly_rows.append((ym, {"n": 0}))
            continue
        m = metrics_for(
            sub["pred"].to_numpy(),
            sub["label"].to_numpy(),
            sub["return_pct"].to_numpy(),
        )
        monthly_rows.append((ym, m))

    overall = metrics_for(
        df_eval["pred"].to_numpy(),
        df_eval["label"].to_numpy(),
        df_eval["return_pct"].to_numpy(),
    )

    # Quarterly walk-forward summary (same shipped model evaluated on each quarter)
    df_eval["_quarter"] = df_eval["_month_str"].apply(
        lambda s: f"Q{(int(s.split('-')[1]) - 1) // 3 + 1}"
    )
    quarterly_rows: list[tuple[str, dict]] = []
    for q in ("Q1", "Q2", "Q3", "Q4"):
        sub = df_eval[df_eval["_quarter"] == q]
        if sub.empty:
            quarterly_rows.append((q, {"n": 0}))
            continue
        quarterly_rows.append(
            (
                q,
                metrics_for(
                    sub["pred"].to_numpy(),
                    sub["label"].to_numpy(),
                    sub["return_pct"].to_numpy(),
                ),
            )
        )

    label_src_counts = df_eval["label_source"].value_counts().to_dict()
    verdict = verdict_from(overall)

    # ---- Write report ----
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / "backtest_2024.md"
    now = datetime.now(timezone.utc).isoformat()

    n_total = int(overall.get("n", 0))
    meta_train_n = meta.get("n_samples")
    is_in_sample = meta_train_n is not None and n_total >= int(meta_train_n) - 5

    lines: list[str] = []
    lines.append(f"VERDICT: {verdict}")
    lines.append("")
    lines.append("# SPY Direction Model v1.0 — 2024 Backtest")
    lines.append(f"_Generated: {now}_")
    lines.append("")
    lines.append("## Methodology")
    lines.append("")
    lines.append(
        "Loaded the shipped SPY artifact (`models/SPY_direction_v1.0.joblib` + "
        "`models/SPY_scaler_v1.0.joblib`) with a `_quarantine` guard, pulled SPY "
        "`ml_features` rows for `2024-01-01 <= date < 2025-01-01` from MongoDB "
        f"(`{DB_NAME}.ml_features`), and joined next-day outcomes from "
        "`gex_llm_patterns_outcomes` (167 labeled 2024 rows in this database). "
        "Where outcomes are absent for a date, we fall back to the "
        "`target_directional_move` / `target_return_pct` fields already on the "
        "`ml_features` row. The walk-forward structure splits 2024 into four "
        "calendar quarters; the **same shipped model** is evaluated on each "
        "quarter — we do not retrain. Metrics: precision, recall, F1 (positive "
        "class = next-day up move), accuracy, hit rate (signed prediction = "
        "signed return), and profit factor (sum of winning trade P&L over "
        "absolute losing P&L, with P&L = +`return_pct` when predicting up and "
        "−`return_pct` when predicting down)."
    )
    lines.append("")
    if is_in_sample:
        lines.append(
            f"> CAVEAT: the shipped artifact was trained on {meta_train_n} rows "
            f"(per `SPY_meta_v1.0.json`); the 2024 evaluation set has {n_total} "
            "rows that overlap with that training window. Headline metrics are "
            "therefore IN-SAMPLE on the deployed pickle. Treat the quarterly "
            "breakdown as a sanity check on the deployed artifact, not as "
            "out-of-sample evidence."
        )
    else:
        lines.append(
            f"> The shipped artifact was trained on {meta_train_n} rows; "
            f"this evaluation covers {n_total} rows that may overlap. "
            "Interpret accordingly."
        )
    lines.append("")
    lines.append("## Monthly Breakdown")
    lines.append("")
    lines.append(
        "| Month | Precision | Recall | F1 | Accuracy | Hit Rate | Profit Factor | n_predictions |"
    )
    lines.append(
        "|-------|-----------|--------|----|----------|----------|---------------|---------------|"
    )
    for ym, m in monthly_rows:
        if m.get("n", 0) == 0:
            lines.append(f"| {ym} | — | — | — | — | — | — | 0 (no data) |")
        else:
            lines.append(
                f"| {ym} | {fmt(m['precision'])} | {fmt(m['recall'])} | "
                f"{fmt(m['f1'])} | {fmt(m['accuracy'])} | {fmt(m['hit_rate'])} | "
                f"{fmt(m['profit_factor'])} | {m['n']} |"
            )
    lines.append("")
    lines.append("## Quarterly Walk-Forward")
    lines.append("")
    lines.append(
        "| Quarter | Precision | Recall | F1 | Accuracy | Hit Rate | Profit Factor | n_predictions |"
    )
    lines.append(
        "|---------|-----------|--------|----|----------|----------|---------------|---------------|"
    )
    for q, m in quarterly_rows:
        if m.get("n", 0) == 0:
            lines.append(f"| {q} | — | — | — | — | — | — | 0 (no data) |")
        else:
            lines.append(
                f"| {q} | {fmt(m['precision'])} | {fmt(m['recall'])} | "
                f"{fmt(m['f1'])} | {fmt(m['accuracy'])} | {fmt(m['hit_rate'])} | "
                f"{fmt(m['profit_factor'])} | {m['n']} |"
            )
    lines.append("")
    lines.append("## Overall (2024)")
    lines.append("")
    lines.append(f"- n_predictions: {overall['n']}")
    lines.append(f"- precision: {fmt(overall['precision'])}")
    lines.append(f"- recall: {fmt(overall['recall'])}")
    lines.append(f"- F1: {fmt(overall['f1'])}")
    lines.append(f"- accuracy: {fmt(overall['accuracy'])}")
    lines.append(f"- hit rate: {fmt(overall['hit_rate'])}")
    lines.append(f"- profit factor: {fmt(overall['profit_factor'])}")
    lines.append("")
    lines.append("## Label Sources")
    lines.append("")
    for k, v in sorted(label_src_counts.items()):
        lines.append(f"- `{k}`: {v}")
    lines.append("")
    lines.append("## Verdict Logic")
    lines.append("")
    lines.append(
        f"- SHIP when n >= {VERDICT_SHIP_MIN_N}, accuracy >= {VERDICT_SHIP_ACC}, "
        f"profit_factor >= {VERDICT_SHIP_PF}"
    )
    lines.append(
        f"- INVESTIGATE when accuracy >= {VERDICT_INVESTIGATE_ACC} and "
        f"profit_factor >= {VERDICT_INVESTIGATE_PF}"
    )
    lines.append("- REJECT otherwise")
    lines.append("")
    lines.append(
        "Note: a SHIP verdict here is necessary but not sufficient for "
        "deployment confidence — see the in-sample caveat above. Out-of-sample "
        "validation requires fresh post-2024 labeled rows."
    )

    report_text = "\n".join(lines) + "\n"
    report_path.write_text(report_text)

    # Echo summary to stdout
    print(f"verdict={verdict} n={overall['n']} acc={fmt(overall['accuracy'])} "
          f"pf={fmt(overall['profit_factor'])} hit={fmt(overall['hit_rate'])}")
    print(f"report: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
