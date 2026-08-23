/**
 * convictionAlert.js — Blademap-style instant notify for high-conviction
 * signals. WebAudio two-tone chime (no asset files); fires once per
 * alert key per session. Browser autoplay: the first chime requires a
 * prior user gesture on the page (standard policy) — the desk unlocks
 * audio by clicking anything once.
 */

const firedKeys = new Set();
let ctx = null;

function tone(freq, t0, dur, gain = 0.08) {
  const osc = ctx.createOscillator();
  const g = ctx.createGain();
  osc.type = "sine";
  osc.frequency.value = freq;
  g.gain.setValueAtTime(0, ctx.currentTime + t0);
  g.gain.linearRampToValueAtTime(gain, ctx.currentTime + t0 + 0.02);
  g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + t0 + dur);
  osc.connect(g).connect(ctx.destination);
  osc.start(ctx.currentTime + t0);
  osc.stop(ctx.currentTime + t0 + dur + 0.05);
}

/**
 * Chime for a newly-seen high-conviction alert. No-op when muted, when
 * already fired for this key, or before first user gesture (autoplay).
 */
export function chimeHighConviction(alertKey, { muted = false } = {}) {
  if (muted || !alertKey || firedKeys.has(alertKey)) return false;
  try {
    ctx = ctx || new (window.AudioContext || window.webkitAudioContext)();
    if (ctx.state === "suspended") return false;   // autoplay-locked; retry next poll
    // rising two-tone: E5 → A5 — distinct from any system sound
    tone(659.25, 0.0, 0.12);
    tone(880.0, 0.13, 0.18);
    firedKeys.add(alertKey);
    return true;
  } catch {
    return false;
  }
}

export function resetConvictionAlerts() {
  firedKeys.clear();
}
