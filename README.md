# MCP Marketing Dashboard

Pulls Google Analytics 4 and Meta Ads data **through MCP servers**, stores it in
SQLite and shows it on a self-hosted Streamlit dashboard.

```
 ┌──────────────────┐  stdio/JSON-RPC  ┌───────────────┐   GA4 Data API
 │                  │ ───────────────► │ analytics-mcp │ ───────────────► Google
 │   extractor/     │                  └───────────────┘
 │  (MCP client)    │  stdio/JSON-RPC  ┌───────────────┐   Marketing API
 │                  │ ───────────────► │ meta-ads-mcp  │ ───────────────► Meta
 └────────┬─────────┘                  └───────────────┘
          │ upsert daily rows
          ▼
   data/marketing.db (SQLite) ◄──── dashboard/app.py (Streamlit, port 8501)
```

**Why this split?** The MCP servers are the only part that talks to Google and
Meta. The extractor is a small MCP *client*: it does the same thing Claude
does when you connect an MCP server — list tools, call them, read JSON — but
on a schedule. The dashboard only reads the database, so it is fast and never
uses your API quota.

---

## Step 0 — Where to run it (important on this PC)

Your Claude Code `analytics-mcp` connection fails because **Windows Smart App
Control blocks the `grpc` DLL** that the Google client library loads:

```
ImportError: DLL load failed while importing cygrpc: An Application Control policy has blocked this file.
```

This will also block the extractor on Windows. Pick one:

| Option | Notes |
|---|---|
| **Linux server / VPS with Docker** (recommended) | It's "self-hosted" anyway. `docker compose up -d` and you're done. |
| **WSL on this PC** | `wsl --install`, then follow the Linux steps inside Ubuntu. Linux binaries aren't affected by Smart App Control. |
| Turn off Smart App Control | Windows Security → App & browser control. Windows can't turn it back on without a reinstall, so this is your call. |

The dashboard alone (`demo` + Streamlit) runs fine on Windows.

## Step 1 — Credentials

### Google Analytics 4
1. In Google Cloud console, create a project and enable **Google Analytics Data API**
   and **Google Analytics Admin API**.
2. Create a **service account** → Keys → Add key → JSON. Save it as
   `secrets/ga-service-account.json`.
3. In GA4 → Admin → Property access management, add the service account email
   as **Viewer**.
4. Note the numeric **Property ID** (Admin → Property details).

(For local tests you can use your own account instead:
`gcloud auth application-default login --scopes https://www.googleapis.com/auth/analytics.readonly,https://www.googleapis.com/auth/cloud-platform`.)

### Meta Ads
1. In Meta Business Settings → Users → **System users**, create a system user and
   assign it your ad account.
2. Generate a token with **`ads_read`** permission (pick "never expires").
3. Note your ad account ID in the form `act_1234567890`.

Copy `.env.example` to `.env` and fill in all values.

## Step 2 — Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt analytics-mcp meta-ads-mcp
```

## Step 3 — Discover what the MCP servers offer

```bash
python -m extractor.run discover
```

This starts each server, does the MCP handshake and prints every tool with its
arguments (`*` = required). This is how you learn an MCP server: **don't
guess, list.** Check that `run_report` (GA4) and `get_insights` (Meta) exist
and that the argument names match `config.yaml`. If a server version renamed
something, edit `config.yaml`, not the code.

## Step 4 — Call one tool by hand

```bash
python -m extractor.run call ga4 get_account_summaries '{}'
```

```bash
python -m extractor.run call ga4 run_report '{"property_id": "123456789", "date_ranges": [{"start_date": "7daysAgo", "end_date": "yesterday"}], "dimensions": ["date"], "metrics": ["sessions"]}'
```

```bash
python -m extractor.run call meta get_insights '{"object_id": "act_123", "time_range": "last_7d", "level": "campaign", "access_token": "EAAB..."}'
```

You see the raw JSON exactly as the server returns it. The code in
`extractor/sources/*.py` turns that JSON into table rows.

## Step 5 — Extract into the database

```bash
python -m extractor.run extract
```

Pulls the last `lookback_days` (default 30) up to yesterday and upserts them
into `data/marketing.db`. Re-running is safe: rows are keyed by date +
channel/campaign, so late-arriving numbers simply overwrite older ones. Raw
responses are kept in `data/raw/` for debugging.

## Step 6 — Dashboard

```bash
streamlit run dashboard/app.py
```

Open http://localhost:8501. No credentials yet? Run
`python -m extractor.run demo` first to load fake data.

## Step 7 — Self-host it

On a Linux server with Docker:

```bash
docker compose up -d --build
```

- `extractor` refreshes data every 6 hours.
- `dashboard` serves on port 8501. Put it behind a reverse proxy with auth
  (Caddy, nginx + basic auth, or Cloudflare Access) — Streamlit has no login.

---

## Project map

| File | What it does |
|---|---|
| `config.yaml` | Which MCP servers to launch, which tools/args to call |
| `extractor/mcp_client.py` | Connects to an MCP server (stdio or HTTP), calls tools, parses JSON |
| `extractor/sources/ga4.py` | `run_report` → `ga4_daily` rows |
| `extractor/sources/meta_ads.py` | `get_insights` (one call per day) → `meta_daily` rows |
| `extractor/storage.py` | SQLite schema + upserts + run log |
| `extractor/run.py` | CLI: `discover`, `call`, `extract`, `demo` |
| `dashboard/app.py` | KPIs, trends, campaign and channel tables |

## Adding a metric

1. Add it to `metrics:` in `config.yaml` (GA) or check it appears in Meta's response.
2. Add a column in `storage.py` and map it in the source's `normalize()`.
3. Delete `data/marketing.db` (or `ALTER TABLE`), re-run `extract`, show it in `app.py`.

## About Meta's official MCP

Meta launched a hosted MCP (`https://mcp.facebook.com/ads`, open beta) that
signs in with OAuth in the browser. That's great inside Claude, but an
unattended extractor can't click through OAuth, so this project defaults to
the self-run `meta-ads-mcp` with a system-user token. `config.yaml` has a
commented `transport: http` block if you later get a bearer token for it.
