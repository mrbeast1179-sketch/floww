/**
 * FlowEngine.js — Pure JS module with ALL math for FlowSeeker Pro.
 *
 * Exports:
 *   - flowClassification(legs) → "SWEEP" | "BLOCK" | "SPLIT" | "VWAP_ALGO" | "UNKNOWN"
 *   - tradeDirection(signal) → { side: "BUY"|"SELL", confidence: 0..1 }
 *   - computeGreeks(S, K, T, r, sigma, optionType) → { delta, gamma, theta, vega, vanna, charm }
 *   - flowScore(event) → 0..100
 *   - syntheticDataGenerator() → { events[], startStreaming(callback) }
 *   - normCDF(x), normPDF(x) — standard normal helpers
 */

// ─── Standard normal helpers ────────────────────────────────────────────────

export function normPDF(x) {
  return Math.exp(-0.5 * x * x) / Math.sqrt(2 * Math.PI);
}

export function normCDF(x) {
  // Abramowitz & Stegun approximation (max error < 7.5e-8)
  const a1 = 0.254829592, a2 = -0.284496736, a3 = 1.421413741;
  const a4 = -1.453152027, a5 = 1.061405429, p = 0.3275911;
  const sign = x < 0 ? -1 : 1;
  const ax = Math.abs(x);
  const t = 1.0 / (1.0 + p * ax);
  const y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * Math.exp(-ax * ax);
  return 0.5 * (1.0 + sign * y);
}

// ─── Flow Classification ────────────────────────────────────────────────────

/**
 * Classify a flow event based on its legs.
 * @param {Array} legs — [{ strike, exchange, timestamp, size, price }]
 * @returns {"SWEEP"|"BLOCK"|"SPLIT"|"VWAP_ALGO"|"UNKNOWN"}
 */
export function flowClassification(legs) {
  if (!legs || legs.length === 0) return "UNKNOWN";

  // BLOCK: single print >= 10,000 contracts on single exchange/price
  if (legs.length === 1 && legs[0].size >= 10000) return "BLOCK";

  // SWEEP: single order across 3+ strikes or 3+ exchanges within 100ms
  if (legs.length >= 3) {
    const strikes = new Set(legs.map(l => l.strike));
    const exchanges = new Set(legs.map(l => l.exchange));
    const times = legs.map(l => l.timestamp).sort((a, b) => a - b);
    const timeSpan = times[times.length - 1] - times[0];
    if ((strikes.size >= 3 || exchanges.size >= 3) && timeSpan <= 100) {
      return "SWEEP";
    }
  }

  // SPLIT: same strike/expiry, 2+ exchanges within 500ms, each leg < 10k
  if (legs.length >= 2) {
    const times = legs.map(l => l.timestamp).sort((a, b) => a - b);
    const timeSpan = times[times.length - 1] - times[0];
    const allUnder10k = legs.every(l => l.size < 10000);
    const exchanges = new Set(legs.map(l => l.exchange));
    if (exchanges.size >= 2 && timeSpan <= 500 && allUnder10k) {
      // Check same strike/expiry
      const firstStrike = legs[0].strike;
      const firstExpiry = legs[0].expiry;
      if (legs.every(l => l.strike === firstStrike && l.expiry === firstExpiry)) {
        return "SPLIT";
      }
    }
  }

  // VWAP_ALGO: regular-interval small prints (±5% size, ±50ms) totalling >= 2,000
  if (legs.length >= 3) {
    const times = legs.map(l => l.timestamp).sort((a, b) => a - b);
    const sizes = legs.map(l => l.size);
    const avgSize = sizes.reduce((a, b) => a + b, 0) / sizes.length;
    const totalSize = sizes.reduce((a, b) => a + b, 0);

    if (totalSize >= 2000 && avgSize > 0) {
      // Check size uniformity (±5%)
      const sizeUniform = sizes.every(s => Math.abs(s - avgSize) / avgSize <= 0.05);
      // Check interval regularity (±50ms)
      const intervals = [];
      for (let i = 1; i < times.length; i++) intervals.push(times[i] - times[i - 1]);
      const avgInterval = intervals.reduce((a, b) => a + b, 0) / intervals.length;
      const intervalUniform = intervals.every(iv => Math.abs(iv - avgInterval) <= 50);

      if (sizeUniform && intervalUniform) return "VWAP_ALGO";
    }
  }

  // Also check single-leg BLOCK
  if (legs.length === 1 && legs[0].size >= 10000) return "BLOCK";

  return "UNKNOWN";
}

// ─── Trade Direction (40/30/20/10 weighted) ────────────────────────────────

/**
 * Determine trade direction from multi-signal algorithm.
 * @param {Object} signal — { avgPrice, bid, ask, postBid, postAsk, bidAtExec, askAtExec, oiChange, contracts, dte, otmPct }
 * @returns {{ side: "BUY"|"SELL", confidence: 0..1 }}
 */
export function tradeDirection(signal) {
  const {
    avgPrice, bid, ask, postBid, postAsk,
    bidAtExec, askAtExec, oiChange, contracts, dte, otmPct
  } = signal;

  let score = 0;

  // Signal 1: Price vs mid (40%)
  const mid = (bid + ask) / 2;
  if (avgPrice >= ask) {
    score += 0.4;
  } else if (avgPrice <= bid) {
    score -= 0.4;
  } else {
    const range = ask - bid;
    score += range > 0 ? 0.4 * ((avgPrice - mid) / range) : 0;
  }

  // Signal 2: Post-trade quote movement (30%)
  if (postBid >= askAtExec) {
    score += 0.3;
  } else if (postAsk <= bidAtExec) {
    score -= 0.3;
  }

  // Signal 3: OI change (20%)
  if (oiChange >= contracts * 0.8) {
    score += 0.2 * Math.sign(score || 1);
  } else if (oiChange <= contracts * 0.2) {
    score -= 0.2 * Math.sign(score || 1);
  }

  // Signal 4: Expiry/drift heuristic (10%)
  if (dte <= 5 && Math.abs(otmPct) > 0) {
    score -= 0.05;
  }

  return {
    side: score > 0 ? "BUY" : "SELL",
    confidence: Math.min(1, Math.abs(score))
  };
}

// ─── Greeks (Black-Scholes, European) ───────────────────────────────────────

/**
 * Compute Black-Scholes Greeks for European options.
 * @param {number} S — spot price
 * @param {number} K — strike price
 * @param {number} T — time to expiry in years
 * @param {number} r — risk-free rate (e.g. 0.05)
 * @param {number} sigma — implied volatility (e.g. 0.20 for 20%)
 * @param {string} optionType — "call" or "put"
 * @returns {{ delta, gamma, theta, vega, vanna, charm }}
 */
export function computeGreeks(S, K, T, r, sigma, optionType = "call") {
  if (T <= 0) T = 1 / 365; // avoid division by zero
  if (sigma <= 0) sigma = 0.01;

  const sqrtT = Math.sqrt(T);
  const d1 = (Math.log(S / K) + (r + sigma * sigma / 2) * T) / (sigma * sqrtT);
  const d2 = d1 - sigma * sqrtT;

  const npd1 = normPDF(d1);
  const Nd1 = normCDF(d1);
  const Nd2 = normCDF(d2);

  // Gamma (same for calls and puts)
  const gamma = npd1 / (S * sigma * sqrtT);

  // Vega (same for calls and puts) — per 1% vol
  const vega = S * sqrtT * npd1 / 100;

  // Delta
  const delta = optionType === "call" ? Nd1 : Nd1 - 1;

  // Theta (per day)
  const thetaCall = -(S * npd1 * sigma) / (2 * sqrtT) / 365
    - r * K * Math.exp(-r * T) * Nd2 / 365;
  const thetaPut = -(S * npd1 * sigma) / (2 * sqrtT) / 365
    + r * K * Math.exp(-r * T) * normCDF(-d2) / 365;
  const theta = optionType === "call" ? thetaCall : thetaPut;

  // Vanna: -N'(d1) * d2 / sigma
  const vanna = parseFloat((-npd1 * d2 / sigma).toFixed(6));

  // Charm: -N'(d1) * (2rT - d2*sigma*sqrtT) / (2T*sigma*sqrtT)
  const charm = parseFloat((
    -npd1 * (2 * r * T - d2 * sigma * sqrtT) / (2 * T * sigma * sqrtT)
  ).toFixed(6));

  return { delta, gamma, theta, vega, vanna, charm };
}

// ─── Bjerksund-Stensland (American approximation) ──────────────────────────

/**
 * Bjerksund-Stensland approximation for American option pricing.
 * Returns { price, delta, gamma } — used when DTE is short or for early exercise.
 */
export function bjerksundStensland(S, K, T, r, sigma, optionType = "call") {
  if (T <= 0) T = 1 / 365;
  if (sigma <= 0) sigma = 0.01;

  const b = r; // cost of carry = r for non-dividend
  const beta = (Math.sqrt(Math.pow(b / sigma, 2) + 2 * r / sigma) + b / sigma) / 2;
  const BInfinity = (beta / (beta - 1)) * K;
  const B0 = Math.max(K, (r / (r - b)) * K);
  const ht = -(b * T + 2 * sigma * Math.sqrt(T)) * (K / (BInfinity - B0));
  const i = B0 + (BInfinity - B0) * (1 - Math.exp(ht));

  let alpha, price;
  if (S >= i) {
    alpha = (i - K) * Math.pow(S / i, -beta);
    price = optionType === "call" ? S - K : 0;
  } else {
    const phi = Math.pow(S / i, beta);
    alpha = (1 - Math.exp((b - r) * T)) * phi * (1 - Math.pow(S / i, 1 - beta));
    const euro = computeGreeks(S, K, T, r, sigma, optionType);
    price = alpha * (optionType === "call" ? 1 : -1) + (
      optionType === "call"
        ? S * normCDF((Math.log(S / K) + (b + sigma * sigma / 2) * T) / (sigma * Math.sqrt(T)))
          - K * Math.exp(-r * T) * normCDF((Math.log(S / K) + (b - sigma * sigma / 2) * T) / (sigma * Math.sqrt(T)))
        : K * Math.exp(-r * T) * normCDF(-(Math.log(S / K) + (b - sigma * sigma / 2) * T) / (sigma * Math.sqrt(T)))
          - S * normCDF(-(Math.log(S / K) + (b + sigma * sigma / 2) * T) / (sigma * Math.sqrt(T)))
    );
  }

  // Fallback to BS if approximation gives nonsense
  if (!isFinite(price) || price < 0) {
    const bs = computeGreeks(S, K, T, r, sigma, optionType);
    return { price: bs.delta * S * 0.5, delta: bs.delta, gamma: bs.gamma };
  }

  const bs = computeGreeks(S, K, T, r, sigma, optionType);
  return { price: Math.max(0, price), delta: bs.delta, gamma: bs.gamma };
}

// ─── Flow Score (0-100) ─────────────────────────────────────────────────────

/**
 * Compute a 0-100 flow score from event attributes.
 * @param {Object} event — { contracts, notional, oiShock, flowType, directionConfidence, otmPct, dte }
 * @returns {number} 0..100
 */
export function flowScore(event) {
  const {
    contracts, notional, oiShock, flowType,
    directionConfidence, otmPct, dte
  } = event;

  let score = 0;

  // Size (0-25): >=50k→25, >=10k→20, >=5k→15, >=1k→10, >=500→5
  if (contracts >= 50000) score += 25;
  else if (contracts >= 10000) score += 20;
  else if (contracts >= 5000) score += 15;
  else if (contracts >= 1000) score += 10;
  else if (contracts >= 500) score += 5;

  // Notional (0-25): floor(log10(notional)) * 5, max 25
  if (notional > 0) {
    score += Math.min(25, Math.floor(Math.log10(notional)) * 5);
  }

  // OI shock (0-25): >=1.0→25, >=0.5→20, >=0.2→15, >=0.1→10, >=0.05→5
  if (oiShock >= 1.0) score += 25;
  else if (oiShock >= 0.5) score += 20;
  else if (oiShock >= 0.2) score += 15;
  else if (oiShock >= 0.1) score += 10;
  else if (oiShock >= 0.05) score += 5;

  // Flow type (0-15): SWEEP→15, BLOCK→12, SPLIT→10, VWAP_ALGO→8, else→3
  const ft = String(flowType || "").toUpperCase();
  if (ft === "SWEEP") score += 15;
  else if (ft === "BLOCK") score += 12;
  else if (ft === "SPLIT") score += 10;
  else if (ft === "VWAP_ALGO") score += 8;
  else score += 3;

  // Direction confidence (0-10): confidence * 10
  score += (directionConfidence || 0) * 10;

  // OTM penalty (-10 to 0): >30%→-10, >20%→-7, >10%→-3
  const otm = Math.abs(otmPct || 0);
  if (otm > 0.30) score -= 10;
  else if (otm > 0.20) score -= 7;
  else if (otm > 0.10) score -= 3;

  // DTE bonus (0-5): <=5→5, <=10→3, <=21→1
  if (dte <= 5) score += 5;
  else if (dte <= 10) score += 3;
  else if (dte <= 21) score += 1;

  // Clamp to 0-100
  return Math.max(0, Math.min(100, Math.round(score)));
}

// ─── Synthetic Data Generator ───────────────────────────────────────────────

// Top 200 equities by market cap (hardcoded)
const TOP_200 = [
  "AAPL","MSFT","GOOGL","GOOG","AMZN","NVDA","META","TSLA","BRK-B","LLY",
  "AVGO","V","JPM","WMT","MA","XOM","UNH","JNJ","PG","HD",
  "COST","ABBV","MRK","CRM","BAC","ORCL","NFLX","AMD","PEP","KO",
  "TMO","ADBE","LIN","ACN","WFC","MCD","CSCO","ABT","DHR","GE",
  "AMGN","TXN","PM","INTU","IBM","ISRG","CAT","CMCSA","NOW","QCOM",
  "DIS","PFE","INTC","UBER","AMAT","GS","MS","AXP","LOW","UNP",
  "T","HON","NEE","BKNG","RTX","PLD","SPGI","BLK","SYK","TJX",
  "ELV","MDLZ","LRCX","SCHW","ADI","VRTX","DE","BMY","GILD","MMC",
  "CB","ADP","REGN","CI","SBUX","TMUS","BSX","AMT","FI","KLAC",
  "PANW","SO","DUK","PGR","LULU","CME","MO","ZTS","CL","ICE",
  "SNPS","CDNS","EQIX","SHW","EOG","ITW","NOC","APD","PYPL","MPC",
  "FCX","GD","TT","SLB","ETN","PH","ORLY","CMG","CSX","HUM",
  "CTAS","AJG","PSA","EMR","MCHP","MSI","CCI","MAR","ROP","ADSK",
  "NXPI","OXY","DXCM","TDG","SRE","AFL","CARR","APH","MET","FDX",
  "AIG","PSX","KMB","MNST","D","SPG","TRV","WMB","BK","CTVA",
  "MSCI","GIS","ALL","IQV","WELL","DOW","O","HES","DG","EW",
  "KDP","PPG","BIIB","STZ","IDXX","DHI","KHC","A","ROST","FAST",
  "PAYX","OTIS","TEL","EA","BKR","XEL","CTSH","ODFL","VRSK","BIDU",
  "WBA","LUV","HAL","GEHC","CPRT","TROW","CBRE","ANSS","AVB","WEC",
  "EXC","XYL","IT","CDW","FANG","RMD","MTD","TSCO","LYB","DLR",
  "VICI","ES","APTV","PCG","ALGN","FTNT","EFX","LVS","ULTA","DAL",
  "EBAY","WTW","WST","TAP","K","RIVN","F","LCID","COIN","PLTR"
];

// Market-cap weights (approximate, normalized — top-heavy)
const MARKET_CAP_WEIGHTS = TOP_200.map((_, i) => {
  // Exponential decay: top stock ~30x weight of #200
  return Math.exp(-i * 0.015);
});

// Normalize weights
const WEIGHT_SUM = MARKET_CAP_WEIGHTS.reduce((a, b) => a + b, 0);
const NORMALIZED_WEIGHTS = MARKET_CAP_WEIGHTS.map(w => w / WEIGHT_SUM);

// Cumulative distribution for weighted sampling
const CUMULATIVE = [];
let cumSum = 0;
for (const w of NORMALIZED_WEIGHTS) {
  cumSum += w;
  CUMULATIVE.push(cumSum);
}

function weightedRandomTicker() {
  const r = Math.random();
  for (let i = 0; i < CUMULATIVE.length; i++) {
    if (r <= CUMULATIVE[i]) return TOP_200[i];
  }
  return TOP_200[TOP_200.length - 1];
}

// Log-normal random (Box-Muller)
function logNormalRandom(mu, sigma) {
  const u1 = Math.random();
  const u2 = Math.random();
  const z = Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
  return Math.exp(mu + sigma * z);
}

// Poisson random
function poissonRandom(lambda) {
  const L = Math.exp(-lambda);
  let k = 0, p = 1;
  do { k++; p *= Math.random(); } while (p > L);
  return k - 1;
}

// Random integer in [min, max]
function randInt(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

// Random element from array
function randChoice(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

// Exchanges
const EXCHANGES = ["NYSE", "NASDAQ", "CBOE", "ISE", "MIAX", "BATS", "ARCA", "MEMX"];

// Generate a realistic expiration date
function randomExpiry() {
  const now = new Date();
  const dteRoll = Math.random();
  let days;
  if (dteRoll < 0.40) days = randInt(0, 5);       // 40% 0-5 DTE
  else if (dteRoll < 0.70) days = randInt(6, 21);  // 30% 5-21 DTE
  else if (dteRoll < 0.90) days = randInt(22, 60); // 20% 21-60 DTE
  else days = randInt(61, 180);                     // 10% 60+ DTE

  const exp = new Date(now);
  exp.setDate(exp.getDate() + days);
  // Snap to Friday for standard expiries
  const dow = exp.getDay();
  if (dow !== 5) {
    exp.setDate(exp.getDate() + (5 - dow + 7) % 7);
  }
  return exp.toISOString().slice(0, 10);
}

// Generate a single synthetic flow event
function generateEvent(id, baseTime) {
  const ticker = weightedRandomTicker();
  const spot = 100 + Math.random() * 450; // $100-$550 range
  const strike = Math.round(spot * (0.85 + Math.random() * 0.3) * 100) / 100;
  const expiry = randomExpiry();
  const expDate = new Date(expiry);
  const now = new Date();
  const dte = Math.max(0, Math.round((expDate - now) / 86400000));

  // Contract sizes: log-normal, median ~500, fat tail to 100k+
  const contracts = Math.round(logNormalRandom(Math.log(500), 0.8));
  const clampedContracts = Math.max(1, Math.min(200000, contracts));

  // Option type: 55% calls, 45% puts
  const optionType = Math.random() < 0.55 ? "call" : "put";

  // Side: 55% buy, 45% sell
  const side = Math.random() < 0.55 ? "BUY" : "SELL";

  // Flow type distribution: 45% sweep, 25% block, 20% split, 10% VWAP algo
  const flowRoll = Math.random();
  let flowType;
  if (flowRoll < 0.45) flowType = "SWEEP";
  else if (flowRoll < 0.70) flowType = "BLOCK";
  else if (flowRoll < 0.90) flowType = "SPLIT";
  else flowType = "VWAP_ALGO";

  // IV: realistic range 15%-80%
  const iv = 0.15 + Math.random() * 0.65;

  // OTM percentage
  const otmPct = Math.abs((strike - spot) / spot);

  // Premium estimate
  const premiumPerContract = Math.max(0.05, spot * iv * Math.sqrt(dte / 365) * 0.4);
  const premium = clampedContracts * premiumPerContract;
  const notional = premium; // notional = premium for options

  // OI shock
  const oiShock = clampedContracts / Math.max(1000, clampedContracts * (0.5 + Math.random() * 2));

  // Direction confidence
  const directionConfidence = 0.3 + Math.random() * 0.7;

  // Timestamp with Poisson arrival
  const timeOffset = id === 0 ? 0 : poissonRandom(1) * 500 + Math.random() * 500;
  const timestamp = baseTime + timeOffset;

  // Exchange
  const exchange = randChoice(EXCHANGES);

  // Compute Greeks
  const T = Math.max(1, dte) / 365;
  const greeks = computeGreeks(spot, strike, T, 0.05, iv, optionType);

  // Flow score
  const score = flowScore({
    contracts: clampedContracts,
    notional,
    oiShock,
    flowType,
    directionConfidence,
    otmPct,
    dte
  });

  // Vol/OI ratio
  const volOiRatio = clampedContracts / Math.max(100, clampedContracts * (0.3 + Math.random()));

  // Delta dollar: delta * spot * contracts * 100
  const deltaDollar = greeks.delta * spot * clampedContracts * 100;
  // Gamma dollar: gamma * spot^2 * contracts * 100 / 100
  const gammaDollar = greeks.gamma * spot * spot * clampedContracts * 100 / 100;

  return {
    id,
    timestamp,
    ticker,
    side,
    optionType: optionType.toUpperCase(),
    flowType,
    strike,
    expiry,
    dte,
    otmPct,
    contracts: clampedContracts,
    premium,
    notional,
    volOiRatio,
    delta: greeks.delta,
    gamma: greeks.gamma,
    theta: greeks.theta,
    vega: greeks.vega,
    vanna: greeks.vanna,
    charm: greeks.charm,
    deltaDollar,
    gammaDollar,
    exchange,
    iv: iv * 100,
    spot,
    score,
    directionConfidence,
    oiShock,
  };
}

/**
 * Synthetic data generator.
 * @param {Object} options — { eventCount: 200-500, lambda: 0.5-2 }
 * @returns {{ events: Array, startStreaming: (callback) => void, stopStreaming: () => void }}
 */
export function syntheticDataGenerator(options = {}) {
  const { eventCount = 350, lambda = 1.2 } = options;
  const baseTime = Date.now() - eventCount * 1000 / lambda;

  const events = [];
  for (let i = 0; i < eventCount; i++) {
    events.push(generateEvent(i, baseTime));
  }

  // Sort newest first
  events.sort((a, b) => b.timestamp - a.timestamp);

  let streaming = false;
  let streamId = 0;
  let intervalId = null;

  function startStreaming(callback) {
    if (streaming) return;
    streaming = true;

    function emit() {
      if (!streaming) return;
      const newEvent = generateEvent(streamId++, Date.now());
      // Poisson-like: sometimes emit multiple
      const count = poissonRandom(lambda);
      const newEvents = [newEvent];
      for (let i = 1; i < count + 1; i++) {
        newEvents.push(generateEvent(streamId++, Date.now() + i * 50));
      }
      callback(newEvents);
    }

    // Emit at Poisson intervals
    function scheduleNext() {
      if (!streaming) return;
      const delay = -Math.log(1 - Math.random()) / lambda * 1000;
      intervalId = setTimeout(() => {
        emit();
        scheduleNext();
      }, Math.max(200, delay));
    }
    scheduleNext();
  }

  function stopStreaming() {
    streaming = false;
    if (intervalId) {
      clearTimeout(intervalId);
      intervalId = null;
    }
  }

  return { events, startStreaming, stopStreaming };
}

// ─── Utility formatters ─────────────────────────────────────────────────────

export function formatTime(ts) {
  const d = new Date(ts);
  const h = String(d.getHours()).padStart(2, "0");
  const m = String(d.getMinutes()).padStart(2, "0");
  const s = String(d.getSeconds()).padStart(2, "0");
  const ms = String(d.getMilliseconds()).padStart(3, "0");
  return `${h}:${m}:${s}.${ms}`;
}

export function formatExpiry(dateStr) {
  const d = new Date(dateStr);
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return `${months[d.getMonth()]} ${String(d.getDate()).padStart(2, "0")}`;
}

export function formatMoney(v) {
  const n = Math.abs(Number(v) || 0);
  if (n >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  if (n >= 1e3) return `$${(n / 1e3).toFixed(0)}K`;
  return `$${n.toFixed(0)}`;
}

export function formatNumber(v) {
  return Number(v || 0).toLocaleString("en-US");
}

export function scoreColor(score) {
  if (score >= 80) return "#22c55e"; // green
  if (score >= 60) return "#3b82f6"; // blue
  if (score >= 40) return "#eab308"; // yellow
  return "#ef4444"; // red
}

// v0.8.4 — alias + sentiment helper for FlowseekerPro.jsx
export const fmtMoney = formatMoney;

export function sentimentLabel(score) {
  const s = Number(score) || 0;
  if (s >= 80) return { label: "EXTREME", color: "#ef4444" };
  if (s >= 60) return { label: "HIGH", color: "#f97316" };
  if (s >= 40) return { label: "MODERATE", color: "#eab308" };
  if (s >= 20) return { label: "LOW", color: "#22c55e" };
  return { label: "MINIMAL", color: "#64748b" };
}

// DTE Calculator
export function dteOf(expiry) {
  try { return Math.max(0, Math.round((new Date(expiry) - Date.now()) / 86400000)); }
  catch { return 0; }
}
