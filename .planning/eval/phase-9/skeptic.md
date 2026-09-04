# Skeptic review of the dark-pool Top-N methodology

Purpose: three strongest arguments a serious skeptic would make that this spec misleads, plus
whether we patch the spec or concede the limitation in writing. Rule: prints are levels and size
evidence only — no side, no direction, no bull/bear labels. If an objection can be met by tightening
the spec, tighten it. If it cannot, concede it as a documented limitation and do not paper over it
with UI language.

## Objection 1 — "Top-N by notional is just big prints, not meaningful levels"

Strongest version: a single large off-exchange print at a price does not make that price a reference
level. A block can leave at any price for reasons unrelated to where the market will respect that level
going forward — crossing a spread, hitting a mental round number, printing against a standing limit the
counterparty already had. If we rank by notional and surface the top N, the user sees "biggest prints"
and may infer those are the most important levels. That inference is not supported by the data.

Honest verdict: partially valid. Ranking by notional is a defensible heuristic for "where the most money
changed hands off-exchange," but it is not equivalent to "where the market will reference that level."
The spec should not let the Top-N label itself become a gravity claim.

Fix, not concession: tighten the spec language. The level card must make explicit that rank is by
notional transacted, not by market significance. The allowed copy already restricts this somewhat
("large size transacted at this price," "level may act as reference") but "may act as reference" is
still soft. Better: state plainly that Top-N ranks transacted size, and any inference that the level
is supportive/resistant is a user interpretation, not a product claim. Add a one-line note under the
Top-N header: "Ranked by off-exchange notional transacted. Rank is not a measure of market support."

This is a spec clarification, not a retreat. Keep Top-N, sharpen what it claims to be.

## Objection 2 — "Clustering tolerance is arbitrary and can manufacture levels that are not real"

Strongest version: the tolerance max(0.25%, 10 ticks) is tunable, and any tunable clustering knob can
be turned until the output looks good. A skeptic can reasonably ask: if you widen tolerance enough, a
bunch of unrelated prints collapse into one big cluster and the user sees a false "level." If you
narrow it enough, nothing clusters and the feature looks empty. Either way the user may trust the
cluster as a real thing when it is partly an artifact of the tolerance choice.

Honest verdict: valid, and this is the hardest one to fully answer from snapshot data alone.

Partially fixable: make the default tolerance defensible and fixed-until-calibrated, and show the
tolerance value on the UI so the user can see what clustering radius was used. Do not let the UI
present a cluster without showing the tolerance that produced it. That converts a hidden knob into an
auditable parameter.

Remaining concession: the cluster itself is still an aggregation of prints with no side and no
direction. Two prints at the same price one week apart are not the same phenomenon as two prints at the
same price one minute apart, and the spec must not imply otherwise. The cluster strength formula
(notional + count + recency) already includes recency, which is good. What we should also concede in
writing: a cluster is "prints that occurred near this price within this tolerance and lookback," not
"a level the market has validated." The honest label is closer to "prints have transacted here," with
recency as the only freshness signal we have.

Net: fix by exposing tolerance + tightening the claim; concede the level-validation interpretation.

## Objection 3 — "Without side or venue, Top-N cannot distinguish accumulation from distribution, so it is mostly cosmetic for flow users"

Strongest version: the users who care about dark prints want to know whether institutions are buying or
selling into a level. Our spec deliberately refuses to say side or direction — correctly, because the
data does not support it. But then the skeptic asks: what is the feature actually good for if it cannot
answer the question users are asking? If the honest answer is "it shows where large off-exchange size
has transacted, with no side," some users will experience that as a downgrade from whatever myth they
had before, and the feature may disappoint relative to expectations set by competitor marketing.

Honest verdict: valid, and this is the one to concede most directly.

Where the spec is strong: it is honest. No side, no direction, no bull/bear. That is the correct
position given the data. The honest value proposition is real but narrower than a side-answering feature:
it is "price levels where notable size transacted off-exchange, useful as a reference map, not a
direction signal." That is a legitimate surface, not a fake one.

Concession to make explicit in the spec and in UI copy:
- This feature does not tell you who was buying or selling.
- This feature does not tell you whether the level is currently supported or resisted.
- This feature does not tell you whether the prints are buildup, distribution, gamma-driven, or
  thematic.
- It tells you where notable off-exchange size has transacted, ranked by notional, with freshness as the
  only recency signal we have.

If the prior UI/marketing copy implied more than that, the fix is to bring the copy down to the spec's
honest scope, not to inflate the spec to match the myth.

## What the skeptic would also ask that we should not bend to

- Do not add side inference to dark prints to make the feature feel more useful. That would be a direct
  violation of the honesty rule and would make the feature worse, not better.
- Do not present Top-N as if it answers "institutions are long/short here." It does not.
- Do not let "cluster" language drift into "support/resistance" language without the caveats above.

## Net disposition

Objection 1: fix spec language, keep feature.
Objection 2: fix by exposing tolerance + tighten cluster claims; concede the level-validation inference.
Objection 3: concede openly — the honest value is narrower than the myth, and the copy should say so.

The spec survives all three, but only if the copy is brought down to what the data supports. The risk
is not the spec; it is any residual UI/marketing language that implies more than "notable off-exchange
size transacted at these levels, no side known."
