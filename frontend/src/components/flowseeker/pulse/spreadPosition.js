// Pure — no React, no backend. Single source for spread math truth.
export function spreadPosition(last, bid, ask) {
  const b = Number(bid);
  const a = Number(ask);
  const l = Number(last);
  if (!Number.isFinite(b) || !Number.isFinite(a) || !Number.isFinite(l) || b <= 0 || a <= 0 || a <= b) {
    return { position: null, side: 'NO_QUOTE', label: 'NO_QUOTE' };
  }
  const raw = (l - b) / (a - b);
  const pos = Math.max(0, Math.min(1, raw));
  let side;
  if (pos <= 0.33) side = 'BID';
  else if (pos < 0.67) side = 'MID';
  else side = 'ASK';
  return { position: pos, side, label: side };
}

export function spreadPositionLabel(pos) {
  if (pos == null || !Number.isFinite(pos)) return 'NO_QUOTE';
  if (pos <= 0.33) return 'BID';
  if (pos < 0.67) return 'MID';
  return 'ASK';
}
