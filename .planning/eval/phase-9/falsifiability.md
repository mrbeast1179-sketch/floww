# Falsifiability — what would invalidate our score spec

Purpose: not to defend the spec, to state what would prove it wrong. If none of these are checkable,
the spec is decoration.

## 1. The sign matrix is wrong

Our D2 matrix says put-ASK with rising OI is bullish (HEDGE?).
Falsifiable test: track put-ASK prints with rising OI over a sample, mark them bullish, and compare
next-session underlying drift against a same-volatility control. If put-ASK-rising-OI prints are
neutral or bearish on average, the matrix is wrong and the HEDGE? tag should be removed or inverted.

Concrete observable: if the next-session return distribution conditional on put-ASK+rising-OI is
statistically indistinguishable from zero, our sign on that branch has no edge.

## 2. The magnitude weights are overfit to the snapshot format

Our weights (spread 25 / sizeOI 30 / premium 20 / IV 15 / DTE 10) are calibrated on snapshot proxies.
Falsifiable test: hold out the most recent N sessions, score with the current weights, and compare hit
rate to a no-weight baseline (e.g. volume-only or OI-only). If the weighted score does no better than
a single-component proxy on out-of-sample sessions, the weighting is decorative.

Also falsifiable internally: if removing one component (say IV, 15%) does not change the rank order
of top-decile rows on a real sample, that component is contributing noise, not signal.

## 3. DTE weighting is doing work it shouldn't

We give 0DTE volOI≥2 full DTE weight (10%) because of alert-gate parity, not because P&P supports a
DTE band.
Falsifiable test: on a same-volatility sample, compare a DTE-weighted score to a DTE-flat score. If
the DTE term moves the top decile composition materially, check whether that movement survives a
moneyness control. If it does not, the DTE term is laundering tenor into score where the literature
says moneyness is the real driver, and the weight should be deflated or removed.

This is direct head-to-head against the Brogaard-Han-Won 0DTE abstract (context-grade only, not
peer-reviewed full text): if 0DTE's vol impact survives gamma controls and we still give it a
full-weight DTE term, we should at least be able to show the term is not just recreating the volOI
signal in a different unit.

## 4. The missing-IV rescale or omission is hiding weak rows

R1 removed the 100/85 rescale; missing IV now omits the 15% component with ceiling 85 and DEGRADED.
Falsifiable internal test: take rows with IV present and compute score with IV included vs IV omitted.
If the rank order of the top N is unchanged by dropping IV, then IV confirmation is not contributing
and we are carrying a component for narrative not effect. If rows that are "perfect without IV" become
"weaker with IV contradicts," that is the intended behavior and should be visible in the distribution.

## 5. Spread-position aggression proxy is laundering wide-spread noise

spread_position = (last - bid)/(ask - bid), 25% weight.
Falsifiable test: on a sample with wide vs tight spreads, check whether high spread_position rows
actually correspond to actionable aggression or are just wide-quote noise. If the top spread_position
rows are systematically the wide-spread illiquid ones with no follow-through, the 25% weight is
laundering illiquidity as conviction and should be capped more aggressively than it is.

## 6. The live-chain blindness is structural, not cosmetic

The signed overlay is fixture-grade on live chains because the chain payload has no last/premium/dte.
Falsifiable test: if we ship the overlay and every live row renders UNAVAILABLE or a fake side via
quote proxy, then users are either seeing nothing or seeing laundered quote noise. If the team ships
a quote proxy to "fix" the UNAVAILABLE state, that is falsifiable by CONTRACTS C1 immediately: a proxy
cannot evidence aggression, so any side derived from it is dishonest by construction. The honest fix is
either to add last to the chain or to leave live rows unavailable and move on.

## Bottom line

The spec is falsifiable if and only if we actually run these against a real sample with outcomes.
Without outcomes (F20 still broken), every one of these is an assertion about a score that has never
been measured against realized behavior. That is the real weakness, not the formula.
