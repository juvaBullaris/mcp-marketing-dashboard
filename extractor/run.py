"""Command line entry point.

    python -m extractor.run discover [ga4|meta]   # step 1: see what each MCP server offers
    python -m extractor.run call <server> <tool> '<json args>'   # step 2: try one tool by hand
    python -m extractor.run extract [ga4|meta]    # step 3: pull data into SQLite
    python -m extractor.run demo                  # fill the DB with fake data (no credentials)
"""
import asyncio
import json
import os
import random
import sys
from datetime import date, datetime, timedelta

import yaml
from dotenv import load_dotenv

from . import storage
from .mcp_client import call_tool_json, connect
from .sources import ga4, meta_ads

SOURCES = {"ga4": ga4, "meta": meta_ads}


def load_config(path="config.yaml") -> dict:
    load_dotenv()

    def expand(v):
        if isinstance(v, str):
            return os.path.expandvars(v)
        if isinstance(v, dict):
            return {k: expand(x) for k, x in v.items()}
        if isinstance(v, list):
            return [expand(x) for x in v]
        return v

    with open(path, encoding="utf-8") as f:
        return expand(yaml.safe_load(f))


async def discover(cfg, names):
    for name in names:
        print(f"\n=== {name} ===")
        async with connect(cfg["servers"][name]) as session:
            tools = await session.list_tools()
            for t in tools.tools:
                print(f"\n- {t.name}: {(t.description or '').strip().splitlines()[0] if t.description else ''}")
                props = (t.inputSchema or {}).get("properties", {})
                required = set((t.inputSchema or {}).get("required", []))
                for arg, schema in props.items():
                    flag = "*" if arg in required else " "
                    print(f"    {flag} {arg}: {schema.get('type', schema.get('anyOf', '?'))}")


async def call(cfg, server, tool, args_json):
    async with connect(cfg["servers"][server]) as session:
        result = await call_tool_json(session, tool, json.loads(args_json))
        print(json.dumps(result, indent=2, default=str)[:20000])


def save_raw(name, raw):
    os.makedirs("data/raw", exist_ok=True)
    path = f"data/raw/{name}-{datetime.now():%Y%m%d-%H%M%S}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2, default=str)
    print(f"  raw response saved to {path}")


async def extract(cfg, names):
    end = date.today() - timedelta(days=1)  # yesterday is the last complete day
    start = end - timedelta(days=int(cfg.get("lookback_days", 30)) - 1)
    conn = storage.connect()

    for name in names:
        table = "ga4_daily" if name == "ga4" else "meta_daily"
        print(f"[{name}] {start} -> {end}")
        try:
            async with connect(cfg["servers"][name]) as session:
                raw, rows = await SOURCES[name].fetch(session, cfg[name], start, end)
            if cfg.get("save_raw_responses"):
                save_raw(name, raw)
            n = storage.upsert(conn, table, rows)
            storage.log_run(conn, name, n, "ok")
            print(f"  {n} rows written to {table}")
        except Exception as e:  # keep going so one broken source doesn't block the other
            storage.log_run(conn, name, 0, "error", str(e))
            print(f"  ERROR: {e}")


def demo():
    """Seed fake data so the dashboard can be tried before credentials exist."""
    conn = storage.connect()
    rnd = random.Random(42)
    channels = ["Organic Search", "Paid Social", "Direct", "Email", "Referral"]
    campaigns = [("c1", "Prospecting - Broad"), ("c2", "Retargeting 7d"), ("c3", "Catalog Sales")]
    ga_rows, meta_rows = [], []
    for i in range(60):
        d = (date.today() - timedelta(days=60 - i)).isoformat()
        for ch in channels:
            s = rnd.randint(80, 900) * (2 if ch == "Paid Social" else 1)
            ga_rows.append({"date": d, "property_id": "demo", "channel": ch, "sessions": s,
                            "users": int(s * 0.8), "new_users": int(s * 0.5),
                            "key_events": round(s * rnd.uniform(0.01, 0.04)),
                            "revenue": round(s * rnd.uniform(0.5, 2.5), 2)})
        for cid, cname in campaigns:
            spend = round(rnd.uniform(40, 220), 2)
            imp = int(spend * rnd.uniform(80, 140))
            clicks = int(imp * rnd.uniform(0.008, 0.02))
            purch = round(clicks * rnd.uniform(0.02, 0.06))
            meta_rows.append({"date": d, "account_id": "act_demo", "campaign_id": cid,
                              "campaign_name": cname, "spend": spend, "impressions": imp,
                              "clicks": clicks, "purchases": purch,
                              "purchase_value": round(purch * rnd.uniform(30, 70), 2)})
    storage.upsert(conn, "ga4_daily", ga_rows)
    storage.upsert(conn, "meta_daily", meta_rows)
    storage.log_run(conn, "demo", len(ga_rows) + len(meta_rows), "ok", "fake data")
    print(f"Demo data written to {storage.db_path()}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "extract"
    rest = sys.argv[2:]
    if cmd == "demo":
        load_dotenv()
        return demo()
    cfg = load_config()
    if cmd == "discover":
        asyncio.run(discover(cfg, rest or list(cfg["servers"])))
    elif cmd == "call":
        asyncio.run(call(cfg, rest[0], rest[1], rest[2] if len(rest) > 2 else "{}"))
    elif cmd == "extract":
        asyncio.run(extract(cfg, rest or list(SOURCES)))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
