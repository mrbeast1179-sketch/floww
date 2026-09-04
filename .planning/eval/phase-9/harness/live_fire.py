"""Agent-4 live-fire harness: score REAL chain payloads with the REAL scan_score.

Inputs: /tmp/chain_{SPY,QQQ}.json from GET /api/public/chain/{ticker} (live, same shell run).
Method: map chain contracts -> norm_rows-style dicts (same field semantics as
  backend/services/flow_alerts.norm_rows), then call the IMPORTED scan_score /
  est_entry / biz_dte (no reimplementation).
Output: fire-rate table for SCORE>=92, WHALE premium>=$25M, 0DTE volOI>=2.
  SIGMA>=6s is NOT measurable snapshot-only (needs B1 baselines) — reported, not faked.
Run: backend/.venv/bin/python .planning/eval/phase-9/harness/live_fire.py
"""
import json, math, sys, os

sys.path.insert(0, os.path.expanduser("~/Documents/GitHub/floww/backend"))
sys.path.insert(0, os.path.expanduser("~/Documents/GitHub/floww/backend/services"))
from services.flow_alerts import scan_score, biz_dte, est_entry  # real code path

def to_row(c, ticker, spot):
    vol = float(c.get("volume") or 0); oi = float(c.get("oi") or 0)
    strike = float(c.get("strike")); exp = str(c.get("expiry"))[:10]
    dte = biz_dte(exp)
    r = {"under": ticker, "type": str(c.get("type")), "strike": strike, "exp": exp,
         "dte": dte, "vol": vol, "oi": oi, "iv": c.get("iv"),
         "delta": c.get("delta"), "spot": spot,
         "vol_oi": vol / oi if oi > 0 else vol,
         "notional": vol * 100 * strike}
    r["premium"] = (vol * 100 * est_entry(r)) if est_entry(r) is not None else None
    return r

def run(path, ticker):
    d = json.load(open(path))
    spot = d.get("spot"); rows = [to_row(c, ticker, spot) for c in d["contracts"]]
    rows = [r for r in rows if r["vol"] > 0]
    n = len(rows)
    s92 = sum(1 for r in rows if scan_score(r) >= 92)
    whale = sum(1 for r in rows if (r["premium"] or 0) >= 25e6)
    dte0 = [r for r in rows if r["dte"] == 0]
    dte0_hit = sum(1 for r in dte0 if r["vol_oi"] >= 2)
    import statistics
    scores = [scan_score(r) for r in rows]
    dist = {b: sum(1 for s in scores if s >= b) for b in (50, 70, 80, 90, 92, 95)}
    top = sorted(rows, key=lambda r: scan_score(r), reverse=True)[:5]
    return {"ticker": ticker, "spot": spot, "stale": d.get("stale"),
            "n_contracts": d.get("n_contracts"), "n_vol": n,
            "score_ge92": s92, "score_ge92_rate": round(s92 / max(n, 1), 5),
            "whale": whale, "dte0_n": len(dte0), "dte0_volOI2": dte0_hit,
            "score_dist": dist,
            "top": [(t["under"], t["type"], t["strike"], t["exp"], scan_score(t),
                     round(t["vol_oi"], 2), t["premium"] and round(t["premium"])) for t in top],
            "score_mean": round(statistics.mean(scores), 2),
            "score_max": max(scores)}

if __name__ == "__main__":
    out = []
    for t in ("SPY", "QQQ"):
        out.append(run(f"/tmp/chain_{t.lower()}.json", t))
    print(json.dumps(out, indent=1))
