/**
 * exposureBadges — badge descriptors for backend exposure rules.
 *
 * Backend producers (main): RULE_TOXIC_FLOW, RULE_VEX_WALL,
 * RULE_CHARM_PIN, RULE_LIQUIDITY_STRESS in backend/services/
 * exposure_alerts.py; RULE_GAMMA_FLIP also fires from
 * backend/alert_engine.py (GAMMA_FLIP regime-change alert).
 * The Blademap v3 feed (/api/flowseeker/alerts/feed) carries these
 * rows with a `rule` field; this module maps rule → badge. Unknown
 * rules map to null: never invent a badge for a rule with no wired
 * producer.
 *
 * Copy rule: heuristic labels only, no invented precision (F5/F6/F11/F19
 * style). Do NOT conflate CHARM_PIN (exposure) with CHARM_PINNING
 * (alert_engine 0DTE), or GAMMA_FLIP (exposure approach) with
 * GAMMA_FLIP_PROXIMITY (alert_engine).
 *
 * Kind-aware copy (E4-48 D2/D3): the feed persists the backend event kind
 * per row — `key` is `exposure:{kind}:{ticker}:{expiry}:{strike}` and
 * `context_json` carries `{magnitude, kind}` (see events_to_alerts in
 * backend/services/exposure_alerts.py, persisted via context_json in
 * flow_alerts.py). vex_wall_broken and gamma_flip_approach rows MUST NOT
 * render formed/regime copy: their titles use the backend's own _WHY
 * language for that kind. Pass the feed row (or kind string) as the
 * second arg; rule-only calls keep the formed/regime default.
 */

const BADGES = {
  TOXIC_FLOW: {
    rule: "TOXIC_FLOW",
    label: "TOXIC FLOW",
    title:
      "Toxic flow — VPIN in the high regime: makers adversely selected, spreads/vol may widen (heuristic, not a direction call)",
  },
  GAMMA_FLIP: {
    rule: "GAMMA_FLIP",
    label: "GAMMA FLIP",
    title:
      "Gamma regime change — dealer gamma flipped from positive to negative (heuristic, not a direction call)",
  },
  VEX_WALL: {
    rule: "VEX_WALL",
    label: "VEX WALL",
    title:
      "VEX wall — dealers defending this vol level, vol suppression (heuristic, not a direction call)",
  },
  CHARM_PIN: {
    rule: "CHARM_PIN",
    label: "CHARM PIN",
    title:
      "Charm pin — delta-hedging concentration into expiry, price magnet (heuristic)",
  },
  LIQUIDITY_STRESS: {
    rule: "LIQUIDITY_STRESS",
    label: "LIQUIDITY STRESS",
    title:
      "Liquidity stress — Kyle/Amihud impact regime elevated, wider effective spreads likely (heuristic)",
  },
};

export const EXPOSURE_RULES = Object.freeze(Object.keys(BADGES));

/**
 * Kind-specific title overrides, keyed `${RULE}:${kind}`. Copy is the
 * backend's own _WHY language for that kind (exposure_alerts.py), not
 * paraphrase: broken walls release suppression; approach rows press the
 * flip level without flipping it.
 */
const KIND_TITLES = {
  "VEX_WALL:vex_wall_broken":
    "VEX wall broken — vol suppression released, regime may shift (heuristic, not a direction call)",
  "GAMMA_FLIP:gamma_flip_approach":
    "Gamma flip proximity — price pressing dealer flip level (support above / resistance below) (heuristic, not a direction call)",
};

/**
 * Resolve the backend event kind from a feed row or a bare kind string.
 * Prefer context.kind / context_json.kind; fall back to the `key`
 * segment (`exposure:{kind}:...`). Returns "" when unknown — callers
 * keep the rule default.
 */
export function exposureKindOf(rowOrKind) {
  if (rowOrKind == null) return "";
  if (typeof rowOrKind === "string") return rowOrKind.trim().toLowerCase();
  const row = rowOrKind;
  const ctx = row.context;
  if (ctx && typeof ctx.kind === "string" && ctx.kind.trim()) {
    return ctx.kind.trim().toLowerCase();
  }
  const cj = row.context_json;
  if (typeof cj === "string" && cj.trim()) {
    try {
      const parsed = JSON.parse(cj);
      if (parsed && typeof parsed.kind === "string" && parsed.kind.trim()) {
        return parsed.kind.trim().toLowerCase();
      }
    } catch {
      /* not JSON — fall through to key */
    }
  } else if (cj && typeof cj.kind === "string" && cj.kind.trim()) {
    return cj.kind.trim().toLowerCase();
  }
  if (typeof row.key === "string") {
    const seg = row.key.split(":");
    if (seg.length >= 2 && seg[0] === "exposure" && seg[1].trim()) {
      return seg[1].trim().toLowerCase();
    }
  }
  return "";
}

export function exposureBadgeFor(rule, rowOrKind) {
  if (rule == null) return null;
  const key = String(rule).trim().toUpperCase();
  if (!key) return null;
  const b = BADGES[key];
  if (!b) return null;
  const out = { ...b };
  const kindTitle = KIND_TITLES[`${key}:${exposureKindOf(rowOrKind)}`];
  if (kindTitle) out.title = kindTitle;
  return out;
}
