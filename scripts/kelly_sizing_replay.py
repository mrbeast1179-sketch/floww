#!/usr/bin/env python3
"""scripts/kelly_sizing_replay.py — Standalone entry point for the Kelly
sizing replay.

Loads ``/Users/nav/dvt_backtest_v2.json``, replays each record's P&L
under five sizing policies (naive 2%, naive 1%, theoretical
quarter/half-Kelly at p=0.55/b=1.65, empirical half/quarter-Kelly
per record), and writes:

  * ``reports/kelly_sizing_replay_results.json`` — machine-readable
  * ``reports/kelly_sizing_replay_report.md`` — human-readable summary

This complements ``kelly_calibration_report.py``: the calibration
report documents the static numbers (f*, breakeven), this report
documents the **dollar P&L impact** of switching from naive to Kelly.

Reference: Vince (1992) Optimal f; Tharp (1998) Ch. 7.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from domain.kelly_replay import (  # noqa: E402
    DEFAULT_EQUITY,
    replay_all,
)

DVT_RESULTS_PATH = Path("/Users/nav/dvt_backtest_v2.json")
REPORTS_DIR = REPO_ROOT / "reports"
RESULTS_PATH = REPORTS_DIR / "kelly_sizing_replay_results.json"
REPORT_PATH = REPORTS_DIR / "kelly_sizing_replay_report.md"


# ----------------------------------------------------------------------- #
# Markdown rendering                                                       #
# ----------------------------------------------------------------------- #


POLICY_LABELS = {
    "pnl_naive_2pct": "naive 2% (baseline)",
    "pnl_naive_1pct": "naive 1% (signal_translator default)",
    "pnl_theoretical_quarter_kelly": "quarter-Kelly @ p=0.55, b=1.65",
    "pnl_theoretical_half_kelly": "half-Kelly @ p=0.55, b=1.65",
    "pnl_empirical_quarter_kelly": "empirical quarter-Kelly (per-record)",
    "pnl_empirical_half_kelly": "empirical half-Kelly (per-record)",
}


def _render_markdown(payload: dict) -> str:
    lines: list[str] = []
    lines.append("# Kelly Sizing Replay Report\n\n")
    lines.append(
        "Linear-scaling replay sourced from "
        f"`{payload.get('baseline_pct', 0.02):.4f}`-of-equity baseline "
        "(the current paper_trading.py default). Each record's realised "
        "`total_pnl` is uniformly scaled by `policy_pct / baseline_pct`.\n\n"
    )
    lines.append(
        "**Caveat**: this replay is a *first-order* approximation. The "
        "source JSON provides aggregates only — it lacks trade-by-trade "
        "sequencing, so compounding dynamics from a Kelly-sized equity "
        "curve are NOT modelled. Use this section as a sizing-policy "
        "comparison, not a walk-forward simulation.\n\n"
    )

    # Summary table
    lines.append("## Per-Policy Aggregate\n\n")
    lines.append(
        "| Policy | % of equity | Total P&L | Mean Final Equity | Win count | "
        "Sharpe-proxy | MDD proxy |\n"
    )
    lines.append(
        "|---|---:|---:|---:|---:|---:|---:|\n"
    )
    for col, label in POLICY_LABELS.items():
        agg = payload["aggregates"][col]
        lines.append(
            f"| {label} | {agg['policy_pct']:.4f} | ${agg['total_pnl']:+,.2f} | "
            f"${agg['mean_final_equity']:,.2f} | {agg['win_count']}/"
            f"{agg['n_records']} | "
            f"{agg['sharpe_proxy']:+.4f} | ${agg['mdd_proxy']:,.2f} |\n"
        )

    # No-Trade filter callout
    lines.append("\n## Kelly No-Trade Filter\n\n")
    lines.append(
        f"The empirical Kelly filter skipped "
        f"**{payload['avoided_loss_count']} of "
        f"{len(payload['per_record'])}** records (records where empirical "
        f"win-rate < breakeven `1/(avg_rr+1)`). For those records, "
        f"replayed P&L is **$0.00** under empirical half/quarter-Kelly "
        f"— those strategies would NOT have been traded at all under "
        f"Kelly-aware discipline. The raw naive-2% loss for those "
        f"strategies was **${payload['avoided_loss_pnl']:+,.2f}** — "
        f"capital the empirical Kelly filter prevented from being risked.\n"
    )
    if payload["avoided_loss_count"] > 0:
        lines.append("\nFiltered records:\n\n")
        lines.append("| Symbol | Strategy | Win-rate | Avg R:R | Naive P&L |\n")
        lines.append("|---|---|---:|---:|---:|\n")
        for r in payload["per_record"]:
            if r["empirical_filtered"]:
                lines.append(
                    f"| {r['symbol']} | {r['strategy']} | "
                    f"{r['win_rate']:.4f} | {r['avg_rr']:+.4f} | "
                    f"${r['pnl_naive_2pct']:+,.2f} |\n"
                )

    # Capital risked proxy
    lines.append("\n## Capital Risked Proxy\n\n")
    lines.append(
        "Total dollar exposure across all 21 records under each policy "
        "(sum of trades × $"
        f"{DEFAULT_EQUITY:.0f} equity × policy fraction).\n\n"
    )
    lines.append("| Policy | Dollars risked |\n|---|---:|\n")
    for col, label in POLICY_LABELS.items():
        dollars = payload["capital_risked_proxy"][col]
        lines.append(f"| {label} | ${dollars:,.2f} |\n")

    # Per-record top half-Kelly table (where filter didn't kick in)
    lines.append("\n## Per-Record Replay (empirical half-Kelly)\n\n")
    lines.append(
        "All 21 records with empirical full-Kelly computed from THIS "
        "record's win-rate and avg-rr. Records with `empirical_filtered=true` "
        "would NOT have been traded at all under Kelly-aware discipline "
        "(replayed P&L = $0).\n\n"
    )
    lines.append(
        "| Symbol | Strategy | WR | R:R | Naive P&L | Emp. f* | "
        "Emp. half | Emp. quarter |\n"
    )
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|\n")
    # Sort by naive PNL descending (highlight winners first).
    sorted_recs = sorted(
        payload["per_record"], key=lambda r: -r["pnl_naive_2pct"]
    )
    for r in sorted_recs[:15]:  # top 15 to keep the table readable.
        lines.append(
            f"| {r['symbol']} | {r['strategy']} | {r['win_rate']:.3f} | "
            f"{r['avg_rr']:.3f} | ${r['pnl_naive_2pct']:+,.2f} | "
            f"{r['empirical_full_kelly']:.4f} | "
            f"${r['pnl_empirical_half_kelly']:+,.2f} | "
            f"${r['pnl_empirical_quarter_kelly']:+,.2f} |\n"
        )
    lines.append(
        f"\n*(Showing top 15 of {len(payload['per_record'])} records "
        "sorted by naive P&L descending.)*\n"
    )
    return "".join(lines)


# ----------------------------------------------------------------------- #
# Main                                                                    #
# ----------------------------------------------------------------------- #


def main() -> None:
    if not DVT_RESULTS_PATH.exists():
        print(f"[kelly_sizing_replay] source not found: {DVT_RESULTS_PATH}")
        sys.exit(1)

    with DVT_RESULTS_PATH.open("r") as fh:
        raw = json.load(fh)
    records = raw if isinstance(raw, list) else raw.get("results", [])

    payload = replay_all(records)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with RESULTS_PATH.open("w") as fh:
        json.dump(payload, fh, indent=2)

    with REPORT_PATH.open("w") as fh:
        fh.write(_render_markdown(payload))

    # Console summary
    print(f"[kelly_sizing_replay] source records: {len(records)}")
    print(
        f"[kelly_sizing_replay] avoided-loss filter: "
        f"{payload['avoided_loss_count']} of {len(records)} records "
        f"(${payload['avoided_loss_pnl']:+,.2f} raw loss prevented)"
    )
    print()
    for col, label in POLICY_LABELS.items():
        agg = payload["aggregates"][col]
        print(
            f"[kelly_sizing_replay] {col:>36}: total=${agg['total_pnl']:+,.2f} "
            f" meanEq=${agg['mean_final_equity']:,.2f} "
            f" wins={agg['win_count']}/{agg['n_records']} "
            f" sharpe={agg['sharpe_proxy']:+.4f}"
        )
    print()
    print(f"[kelly_sizing_replay] JSON     → {RESULTS_PATH}")
    print(f"[kelly_sizing_replay] Markdown → {REPORT_PATH}")


if __name__ == "__main__":
    main()
