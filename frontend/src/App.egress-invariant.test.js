/**
 * frontend/src/App.egress-invariant.test.js
 *
 * Defence-in-depth regression test for the AlphaPod bearer-token egress
 * originally pinned in App.js (line ~335 in branch `const base = token
 * ? ALPHAPOD_API : API;`).  This test reads App.js as source and asserts
 * the offending pattern cannot reappear.  Picking source-text invariants
 * over component export keeps App.js on the Freebuff frozen-path list —
 * an actual leak only re-emerges if a contributor re-introduces the
 * `ALPHAPOD_API` import + the `token ? ALPHAPOD_API : API` branching,
 * both of which this test catches.
 */
const fs = require('fs');
const path = require('path');

const APP_JS_PATH = path.join(__dirname, 'App.js');

describe('App.js AlphaPod egress invariant', () => {
  let source;

  beforeAll(() => {
    source = fs.readFileSync(APP_JS_PATH, 'utf8');
  });

  test('does not import ALPHAPOD_API from config/api at module top', () => {
    // Strip shebang/comments line-by-line, then look at the first 60
    // import-bearing lines for an ALPHAPOD_API import.  Block-scope
    // helpers (FlowAlertsPage etc.) cannot re-import the constant
    // without a top-level import under the CRA module system.
    const head = source.split('\n').slice(0, 60).join('\n');
    expect(head).not.toMatch(/^\s*import\s*\{[^}]*\bALPHAPOD_API\b[^}]*\}/m);
  });

  test('does not contain the token-branched ALPHAPOD_API egress pattern', () => {
    expect(source).not.toMatch(/\?\s*ALPHAPOD_API\s*:/);
    // Defensive: also catch the older form
    expect(source).not.toMatch(/ALPHAPOD_API\s*\?\s*API/);
  });

  test('FlowAlertsPage fetch base URL is the local API constant', () => {
    // Pin the FlowAlertsPage axios GET URL pattern: it must use the
    // local `API` constant for its base.  We allow `${base}/api/alerts`
    // where `base` is now unconditionally `API`.  Asserting the literal
    // `API` reference inside the function body together with the negative
    // assertion above closes the surface.
    const flowAlertsPageMatch = source.match(
      /function\s+FlowAlertsPage[\s\S]*?\n\}\s*\n/
    );
    expect(flowAlertsPageMatch).not.toBeNull();
    const fnBody = flowAlertsPageMatch[0];
    expect(fnBody).toMatch(/const\s+base\s*=\s*API\s*;/);
  });

  test('does not embed api.alphapodtrading.com literal', () => {
    // Last-resort regression net: if a contributor lands a NEW egress
    // path on a different code line, this catches it.
    expect(source).not.toMatch(/api\.alphapodtrading\.com/);
  });
});
