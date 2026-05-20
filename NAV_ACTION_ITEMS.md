# Nav's Action Items — Things Only You Can Do

These are signups, approvals, and 2FA setup that **only Nav** can do. Agents can't sign up for accounts in your name or fill out educational verification forms. Everything below is free.

---

## Tier 1 — Unblocks Agent 7 Round 3 deployment (do this week)

### 1. GitHub Student Pack ⏱ 15 min · $0 ([Free with .edu email])
- URL: https://education.github.com/pack
- Verify with Jefferson `.edu` email (you have this)
- Unlocks: Azure $100, AWS $100, DigitalOcean $200, Namecheap free domain (1y), Sentry (free), Datadog free, JetBrains Pro, MongoDB Atlas free tier, Heroku, Travis CI
- **Why critical:** Required for everything below in Tier 1

### 2. Azure for Students ⏱ 5 min · $0 ($100 credit)
- URL: https://azure.microsoft.com/en-us/free/students/
- Uses GitHub Student Pack credential
- **Why critical:** Agent 7 R3 Task 1 deploys here. ~$13/mo App Service B1 = ~7 months on $100.

### 3. Authy on iPhone ⏱ 5 min · $0
- App Store → "Authy" or "Google Authenticator" (either works)
- **Why critical:** Required for Agent 7 R3 Task 4 (live-trading switch 2FA).
- When Agent 7 wires this in, you'll scan a QR code and Authy generates 6-digit rotating codes.

### 4. Gmail App Password ⏱ 5 min · $0
- URL: https://myaccount.google.com/apppasswords (requires 2FA enabled on the Gmail account)
- Create a password labeled "Hermes 2FA"
- **Why critical:** Email leg of 2FA + outbound alert emails. SMTP via Gmail is free unlimited for personal use.

### 5. Twilio trial ⏱ 10 min · $0 ($15 free credit)
- URL: https://www.twilio.com/try-twilio
- Buy a trial phone number (uses ~$1 of credit; the rest covers ~500 SMS or 200 voice min)
- **Why critical:** Agent 10's CRITICAL phone alerts. ~$0.0079 per SMS, ~$0.013/min voice — $15 lasts months.
- Cheaper alternative: skip Twilio, use Discord webhook (free unlimited).

---

## Tier 2 — Significant uplift (next week)

### 6. Cloudflare ⏱ 15 min · $0
- URL: https://dash.cloudflare.com/sign-up
- Add your domain (from #13) or use a free `*.workers.dev` subdomain
- **What you get:** Free DNS + automatic SSL + DDoS protection + 100k requests/day Workers + 10GB R2 storage
- **Why care:** Sits in front of Azure App Service; HSTS preload eligibility; protects from script-kiddies.

### 7. Sentry ⏱ 10 min · $0 (via Student Pack)
- URL: https://sentry.io/welcome/ (sign in with GitHub, claim Student Pack benefit)
- Create project "floww-backend" (Python) + "floww-frontend" (React)
- **Why care:** Agent 10 R3 wires `sentry_sdk` into every uncaught exception. Production error tracking with stack traces, release tracking, performance traces.

### 8. Discord bot ⏱ 15 min · $0
- URL: https://discord.com/developers/applications → New Application → Create Bot → copy webhook URL
- **Why care:** Free alternative/backup to Twilio. Install Discord on iPhone, get push notifications. Webhook accepts unlimited POSTs.

### 9. Weights & Biases (W&B) ⏱ 10 min · $0 (academic free)
- URL: https://wandb.ai/site (sign up with Jefferson .edu email for academic tier)
- **Why care:** Agent 2 R3 logs every PPO training run — loss curves, hyperparameter sweeps, model artifacts. Free for academic accounts.

### 10. FRED API key ⏱ 5 min · $0
- URL: https://fred.stlouisfed.org/docs/api/api_key.html
- **Why care:** Free macro data (VIX, yield curve, FOMC dates, unemployment, CPI). Agent 6 will use for feature engineering and Agent 2 for RL state observations.

### 11. Hugging Face write token ⏱ 5 min · $0
- URL: https://huggingface.co/settings/tokens (after creating an account)
- Create token with `write` scope, label it "hermes"
- **Why care:** Agent 2 R3 downloads PatchTST/Autoformer pretrained weights (some are gated) and pushes its own trained models for sharing.

---

## Tier 3 — Long-tail high-leverage asks (when you have an hour)

### 12. WRDS academic access (via Jefferson library) ⏱ 1 hr to apply, 1-2 weeks to approve · $0
- Email your Jefferson library: "Does Jefferson have a WRDS subscription? I'm researching options market microstructure and need access to OptionMetrics + CRSP + Compustat for an academic project."
- WRDS = Wharton Research Data Services — gold standard for academic finance data
- **Why care HUGE:** OptionMetrics has every options trade since 1996 with implied vol surfaces. **This is what Renaissance buys for $millions.** If Jefferson has access, you get it free.

### 13. Bloomberg / Refinitiv terminal at Jefferson library ⏱ 1 hr to find out · $0
- Many university libraries have a Bloomberg Terminal in the business library
- Ask: "Does Jefferson have a Bloomberg Terminal on campus? I want to use it for thesis research."
- **Why care:** Even 1 hr/week of Terminal access = professional-grade data export for backtesting.

### 14. Namecheap free domain (Student Pack) ⏱ 10 min · $0 (year 1)
- URL: https://nc.me/ (Student Pack benefit)
- Options: `hermes-trading.me`, `floww.dev`, `nav-trades.me`, etc.
- **Why care:** Production deploy needs HTTPS, HTTPS needs a domain. 1 year free via Pack.

### 15. Groq free tier ⏱ 10 min · $0
- URL: https://console.groq.com (sign up with GitHub)
- **Why care:** Sub-100ms LLM inference. Agent 6's research Q&A engine could use this for ~10x faster responses than OpenRouter. Free tier covers 14,400 requests/day for some models.

---

## Tier 4 — Worth knowing about (sign up if/when needed)

| Service | URL | Free tier | Best for |
|---|---|---|---|
| **IEX Cloud** | iexcloud.io | 50k msgs/day | Backup market data |
| **Tradier sandbox** | tradier.com/products/api | Unlimited paper | Alternative broker if Schwab slow |
| **Quiver Quant** | quiverquant.com | Free tier (Congress trades, lobbying, government contracts) | Alt-data for Agent 6 |
| **SEC EDGAR** | sec.gov/edgar/searchedgar/companysearch | Unlimited | 13F holdings, insider trades, fundamentals |
| **Tastytrade Open API** | developer.tastytrade.com | Paper free | Another broker option |
| **Google Colab** | colab.research.google.com | Free T4 GPU ~12h/day | Agent 2 RL training when local is slow |
| **Kaggle** | kaggle.com | 30h/week free GPU + datasets | Backup compute + benchmark datasets |
| **Together.ai** | together.ai | $25 free credits | Open-source LLM hosting |
| **Lambda Labs** | lambdalabs.com | Sometimes student credits via Pack | Real H100 access |
| **Fly.io** | fly.io | 3 shared-CPU VMs free | $0 deploy alternative to Azure |
| **Supabase** | supabase.com | Free Postgres + auth + 1GB storage | Could replace Cosmos DB entirely |
| **Upstash** | upstash.com | Free Redis 10k cmds/day | Rate limiter backend |
| **Grafana Cloud** | grafana.com/auth/sign-up/create-user | 10k metrics + 50GB logs/mo | Cloud Prometheus alternative |
| **Better Stack** | betterstack.com | Free uptime monitoring | Pings every 1min, alerts on down |
| **ntfy.sh** | ntfy.sh | Unlimited free push notifications | Alternative to Twilio |
| **Pushover** | pushover.net | $5 one-time | Best phone-alert UX (worth $5) |

---

## What I'd do this Saturday (90 minutes total)

```
[ ]  15 min — Activate GitHub Student Pack (#1)
[ ]  10 min — Sign up Azure for Students (#2)
[ ]  10 min — Install Authy + create Gmail app password (#3, #4)
[ ]  15 min — Sign up Cloudflare + claim Twilio trial (#6, #5)
[ ]  10 min — Sign up FRED + W&B + Hugging Face write token (#10, #9, #11)
[ ]  30 min — Email Jefferson library re: WRDS / Bloomberg access (#12, #13)
```

After this Saturday, Agent 7 R3 has every credential it needs to deploy to production. The Jefferson library email is the highest-leverage long-tail ask — WRDS access would be a generational data unlock.

---

## What you're NOT waiting on

These you've already done — don't re-do:
- ✅ MongoDB Atlas (`hermesterminal`)
- ✅ Databento ($125 credits remaining)
- ✅ Polygon, FlashAlpha, Alpha Vantage, Finnhub API keys
- ✅ Alpaca paper trading ($100k account, options level 3)
- ✅ Gemini API key
- ✅ Mem0 + Obsidian set up (Agent 9 syncs them)
- ✅ JetBrains Pro (Student Pack)
- ✅ GitHub Pro (Student Pack — unlimited private repos)

---

## What Schwab specifically needs (when they approve you)

When Schwab activates your account:
1. **Check entitlement page** for "Level 2 Options" — most retail accounts get Level 1 only
2. If Level 2 not granted: contact Schwab support, ask for Options Level 2 streaming entitlement
3. Generate API credentials at https://developer.schwab.com → Apps → Create app
4. Add to backend/.env:
   ```
   SCHWAB_APP_KEY=...
   SCHWAB_APP_SECRET=...
   SCHWAB_REDIRECT_URI=https://localhost
   SCHWAB_ACCOUNT_NUMBER=...
   ```
5. Run `python scripts/schwab_oauth_init.py` (Agent 1 wrote this) — opens browser for one-time OAuth consent
6. The streamer takes over from there; tokens auto-refresh

If Schwab denies Level 2 indefinitely: Agent 1 has a fallback to LEVEL_ONE which gives us bid/ask but not depth. ~80% of features still work.

---

## What 2FA actually looks like end-to-end

Agent 7 R3 Task 4 will build this. When you want to flip `PAPER_ONLY → LIVE_TINY`:

1. You call `POST /api/admin/live-trading/transition` with your JWT
2. System emails you a click-link (Gmail SMTP)
3. You click the link from your phone — opens a page asking for a TOTP code
4. You open Authy, find the "Hermes" entry, type the 6-digit code
5. System verifies both factors, writes audit-trail entry, transitions state
6. State is now `LIVE_TINY` (max $1000 notional per trade until you escalate)

Total time per state transition: ~30 seconds. Auditable. Reversible if you cool-down (circuit breakers demote on -2% daily drawdown).

---

End of action items. None of these block agents from RUNNING — they only block the live-trading switch from flipping. Agents will happily build everything in paper-trade mode regardless.
