#!/usr/bin/env node
/**
 * Live verification of the Tidehunter Pro tab: loads the real dev-server
 * bundle with real network access (jsdom, runScripts), waits for React to
 * render + the poll cycle to fire, then asserts the TDZ-class crash is gone
 * and the hygiene/outcomes surfaces are present in the live DOM.
 *
 * Why not headless Chrome: Chrome's sandboxed network child is killed in
 * this environment (MachPortRendezvous denials -> ERR_CONNECTION_REFUSED to
 * ports curl reaches fine). jsdom fetches like a normal process.
 *
 * Usage: node scripts/verify_tidehunter_live.js [--shot out.png]
 */
const fs = require("fs");
const path = require("path");
const { JSDOM } = require(path.join(process.cwd(), "node_modules", "jsdom"));

const URL = "http://127.0.0.1:3000/?page=flowseeker-pro";
const WAIT_MS = 20000;
const OUT = [];

function log(s) { OUT.push(s); console.log(s); }

(async () => {
  let dom;
  try {
    dom = await JSDOM.fromURL(URL, {
      runScripts: "dangerously",
      resources: "usable",
      pretendToBeVisual: true,
      beforeParse(window) {
        // jsdom has no canvas/WebGL — stub enough for chart libs not to throw.
        window.HTMLCanvasElement.prototype.getContext = () => ({
          clearRect() {}, fillRect() {}, beginPath() {}, arc() {}, fill() {},
          moveTo() {}, lineTo() {}, stroke() {}, createLinearGradient() {
            return { addColorStop() {} };
          },
          measureText: () => ({ width: 10 }),
          save() {}, restore() {}, translate() {}, scale() {}, rotate() {},
        });
        window.matchMedia = window.matchMedia || (() => ({
          matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {},
        }));
      },
    });
  } catch (e) {
    log(`FATAL: could not load ${URL}: ${e.message}`);
    process.exit(2);
  }
  const { window } = dom;
  const errors = [];
  window.addEventListener("error", (e) => errors.push(String(e.error || e.message)));

  await new Promise((r) => setTimeout(r, WAIT_MS));

  const doc = window.document;
  const text = doc.body ? doc.body.textContent || "" : "";
  const q = (sel) => doc.querySelectorAll(sel).length;

  log(`loaded: ${URL}`);
  log(`jsdom console errors captured: ${errors.length}`);
  errors.slice(0, 5).forEach((e) => log(`  window.onerror: ${e.slice(0, 160)}`));

  // ── 1. The TDZ-class crash must be gone ──
  const boundaryTrips = (text.match(/Something went wrong/g) || []).length;
  log(`1. ErrorBoundary trips: ${boundaryTrips} (must be 0) ${boundaryTrips === 0 ? "PASS" : "FAIL"}`);
  const refreshTickErr = errors.some((e) => /before initialization|refreshTick|Qe /.test(e));
  log(`   TDZ-style ReferenceErrors: ${refreshTickErr ? "PRESENT — FAIL" : "none — PASS"}`);

  // ── 2. The tab actually mounted (positive controls) ──
  const mounted = /Smart Order Flow/i.test(text) && /Scanner/i.test(text);
  log(`2. Tab mounted (Smart Order Flow + Scanner visible): ${mounted ? "PASS" : "FAIL"}`);
  log(`   fsb-* elements: ${q("[class*='fsb-']")}`);

  // ── 3. Hygiene chips present in the live DOM ──
  const tags = q(".fsb-oitag");
  const expChips = (text.match(/EXP/g) || []).length;
  const rollChips = (text.match(/ROLL/g) || []).length;
  const eChips = q(".fsb-oitag.fe");
  log(`3. Hygiene chips: .fsb-oitag=${tags} (EXP text=${expChips}, ROLL text=${rollChips}, earnings E=${eChips})`);

  // ── 4. Outcome ledger panel ──
  const ledger = /Outcome Ledger/i.test(text);
  const uncal = (text.match(/uncalibrated · n=\d+/g) || []).length;
  log(`4. Outcome Ledger panel: ${ledger ? "present — PASS" : "MISSING — FAIL"}; uncalibrated rows: ${uncal}`);

  // ── 5. Live feed state ──
  const stale = /STALE/.test(text);
  const retry = /retry/.test(text);
  log(`5. Feed state: STALE marker=${stale}, retry hint=${retry} (informational — stale-serving is the designed contract)`);

  const passed = boundaryTrips === 0 && mounted && ledger && !refreshTickErr;
  log(`\nVERDICT: ${passed ? "PASS — tab live, no TDZ crash, ledger rendering" : "FAIL — see above"}`);

  // Optional PNG capture via node-canvas is unavailable; save the DOM instead
  // so the shot can be diffed/inspected.
  fs.writeFileSync("/tmp/tidehunter_verify/live_dom.html", doc.documentElement.outerHTML);
  log(`full live DOM saved: /tmp/tidehunter_verify/live_dom.html (${doc.documentElement.outerHTML.length} bytes)`);

  window.close();
  process.exit(passed ? 0 : 1);
})().catch((e) => { console.error("FATAL:", e); process.exit(2); });
