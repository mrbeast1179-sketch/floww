"""Static educational content for the Heatseeker glossary panel.

Sourced from the user's article corpus. Keep concise summaries; the UI
renders these as collapsible cards. Full body text included so users can
expand and study without leaving the terminal.
"""

GLOSSARY = [
    {
        "id": "overview",
        "title": "The Options Greeks",
        "tag": "Overview",
        "summary": "Risk measures describing how option prices move with underlying, time, and volatility.",
        "eli5": "An options position is a ship at sea. Delta is heading, Gamma is rudder sensitivity, Vega is the sail, Theta is the tide.",
        "body": "The options Greeks describe how an option's price changes with shifts in market conditions: price, time, and volatility. Together they form a complete map of what drives option premiums beyond simple directional bets. Dealers (market makers) act as the casino — they write contracts and hedge to stay risk-neutral. Each Greek represents a channel through which positioning influences the underlying.",
    },
    {
        "id": "delta",
        "title": "Delta (Δ)",
        "tag": "Primary",
        "summary": "Change in option price per $1 move in the underlying. Calls 0→1, puts -1→0.",
        "eli5": "Delta is the steering wheel position right now — how connected your option is to the underlying.",
        "body": "ATM options sit near ±0.50. Deep ITM approach ±1. Dealers hedge delta neutrally by trading the underlying — these continuous hedges are a direct source of intraday equity flow. When dealers are short calls (negative delta from customer demand), they must buy stock as price rises, fuelling short-squeeze accelerations.",
    },
    {
        "id": "gamma",
        "title": "Gamma (Γ) / GEX",
        "tag": "Primary",
        "summary": "Rate of change of delta. Positive GEX stabilises; negative GEX amplifies.",
        "eli5": "Gamma is a car's suspension — smooth in calm, unstable on ice.",
        "body": "When dealers are long gamma (+GEX, yellow Pika nodes), hedges are contrarian — buy dips, sell rips. When short gamma (−GEX, purple Barney nodes), hedges chase the move — sell dips, buy rips. The King Node is the strike with the largest |GEX|; it acts as gravity. The Gamma Flip is where cumulative GEX changes sign.",
    },
    {
        "id": "vega",
        "title": "Vega (ν)",
        "tag": "Primary",
        "summary": "Sensitivity to a 1pt change in implied volatility. Dominant in 7–180 DTE.",
        "eli5": "Vega is the market's breathing — fear inhales (IV up), calm exhales (IV down).",
        "body": "Long options are long vega; short options are short vega. Vega scales with √T and is highest ATM. IV crush after earnings is pure vega mechanics — uncertainty resolves, premiums collapse even if the stock moves significantly.",
    },
    {
        "id": "theta",
        "title": "Theta (Θ)",
        "tag": "Primary",
        "summary": "Per-day decay of option value. Buyers pay it, sellers harvest it.",
        "eli5": "Theta is a parking meter — every hour costs you another quarter.",
        "body": "Theta is largest near ATM short-dated options. In the final days before expiry, especially 0DTE, theta is the most powerful force on premiums. Dealers short gamma earn theta as compensation for amplifying hedges.",
    },
    {
        "id": "vanna",
        "title": "Vanna / VEX",
        "tag": "Cross",
        "summary": "Change in delta as IV changes. Bridges price and volatility dimensions.",
        "eli5": "Vanna is a tailwind you only notice when it stops blowing.",
        "body": "+VEX below spot is supportive in calm regimes (vol compresses → dealers buy). −VEX below spot is a fragile floor that evaporates when vol settles. Vanna dominates the 1–30 DTE window. Back-end vanna can override front-month GEX support during vol spikes.",
    },
    {
        "id": "charm",
        "title": "Charm",
        "tag": "Cross",
        "summary": "Decay of delta as time passes. Creates systematic intraday rebalancing.",
        "eli5": "Charm is cruise control adding slow throttle — silent rebalancing with no price move.",
        "body": "Charm is strongest near ATM and close to expiry. Combines with vanna in low-vol sessions to produce afternoon drift — slow, grindy, hard to short. On weekly expiry Fridays, charm flows are a meaningful tailwind/headwind for high-OI tickers.",
    },
    {
        "id": "vomma",
        "title": "Vomma (Volga)",
        "tag": "Cross",
        "summary": "Sensitivity of vega to IV. The volatility convexity of an options position.",
        "eli5": "Vomma is a turbocharger for volatility — kicks in during vol shocks.",
        "body": "High positive vomma means vega grows faster as IV rises. Concentrated in ATM-to-slightly-OTM, medium/long-dated options. Tail hedges need vomma because vol shocks gap rather than drift; long vomma converts a linear vol position into one that compounds through the shock.",
    },
    {
        "id": "rules",
        "title": "Three Golden Rules",
        "tag": "Framework",
        "summary": "GEX defines potential. VIX defines reality. Charts first.",
        "eli5": "Greeks tell you the balance of forces, not the exact price.",
        "body": "1) GEX defines potential; VIX defines reality — both must agree. 2) 0–5 DTE = Gamma world. 7–180 DTE = Vanna world. Calibrate analysis to the dominant Greek. 3) Trade where Greeks and vol regime agree. 4) Charts first — form the thesis from price, then use Heatseeker to confirm.",
    },
]
