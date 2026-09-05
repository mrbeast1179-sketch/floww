# Discord Ops Setup — Tidehunter paper trading from your server

Alert posts + `!buy/!sell/!approve/!holdings` run against **Alpaca paper only**
(`paper-api.alpaca.markets` is hardcoded — no live-trading code path exists).

## 1. Create the bot (5 min, Discord side)

1. Go to https://discord.com/developers/applications → **New Application** → name it (e.g. `Tidehunter`).
2. **Bot** → **Reset Token** → copy it → this is `DISCORD_BOT_TOKEN` (never commit it).
3. **Bot** → enable **Message Content Intent** (required for `!` commands).
4. **OAuth2 → URL Generator** → scopes `bot` (+ `applications.commands` if you add slash commands later) → bot permissions: **Send Messages**, **Embed Links**, **Read Message History** → open the URL → invite to your server.
5. Right-click your server name → **Server Settings → Widget** or enable **Developer Mode** (User Settings → Advanced), then right-click your own username → **Copy User ID** → this is `DISCORD_ALLOWED_USER_IDS`.

## 2. Alert webhook (alerts-out)

1. Server Settings → **Integrations → Webhooks** → New Webhook → pick the channel (e.g. `#flow`) → **Copy Webhook URL** → `DISCORD_WEBHOOK_URL`.

## 3. Env (backend/.env — gitignored, never chat these values)

```bash
DISCORD_BOT_TOKEN=<paste>
DISCORD_WEBHOOK_URL=<paste>
DISCORD_ALLOWED_USER_IDS=<your numeric user id>
DISCORD_MIN_TIER=GOLD                 # GOLD only by default
DISCORD_RULES=OICONF,WHALE,SCORE,PRIME
ALPACA_API_KEY=<paper key from app.alpaca.markets/paper/dashboard/overview>
ALPACA_SECRET_KEY=<paper secret>
```

Empty allowlist = trading commands denied for everyone (read-only still works).

## 4. Run

```bash
cd backend
.venv/bin/python3 discord_bot.py     # separate process; backend boots without it
```

Verify wiring without Discord open: `GET /api/discord/status` (booleans only)
and `POST /api/discord/test` (posts a ping; both behind the API key).

## 5. Commands

`!buy <qty> <SYM> [limit <px>]` · `!sell <qty> <SYM>` · `!approve <alert-key> [qty]`
`!holdings` · `!orders` · `!alerts [n]` · `!help`

Alert embeds carry the approve key: `!approve score|SPY|call|745|2099-01-08 2`
buys 2 shares of SPY on Alpaca paper (direction from alert bias).
