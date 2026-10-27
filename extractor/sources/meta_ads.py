"""Meta Ads via an MCP server exposing get_insights (e.g. pipeboard meta-ads-mcp).

Tool used: get_insights(object_id, time_range, level, limit, after, ...)
The response mirrors the Marketing API insights endpoint:
  {data: [{campaign_id, campaign_name, spend, impressions, clicks,
           actions: [{action_type, value}], action_values: [...]}],
   paging: {cursors: {after}, next}}

get_insights has no daily breakdown argument, so we ask for one day at a
time. That keeps every row attributable to a single date.
"""
from datetime import date, timedelta

from ..mcp_client import call_tool_json


def _sum_actions(items, wanted) -> float:
    return sum(float(a.get("value", 0)) for a in items or [] if a.get("action_type") in wanted)


async def fetch(session, cfg: dict, start: date, end: date):
    raws, rows = [], []
    day = start
    while day <= end:
        after = None
        while True:
            args = {
                "object_id": cfg["account_id"],
                "time_range": {"since": day.isoformat(), "until": day.isoformat()},
                "level": cfg["level"],
                **cfg.get("extra_args", {}),
            }
            if after:
                args["after"] = after
            raw = await call_tool_json(session, cfg["tool"], args)
            raws.append(raw)
            rows += normalize(raw, cfg, day)

            # Follow pagination only if the server says there is more.
            paging = raw.get("paging", {}) if isinstance(raw, dict) else {}
            after = paging.get("cursors", {}).get("after") if paging.get("next") else None
            if not after:
                break
        day += timedelta(days=1)
    return raws, rows


def normalize(raw, cfg: dict, day: date) -> list[dict]:
    data = raw.get("data", []) if isinstance(raw, dict) else raw
    wanted = set(cfg.get("purchase_action_types", []))
    return [
        {
            "date": day.isoformat(),
            "account_id": cfg["account_id"],
            "campaign_id": str(item.get("campaign_id", "(account)")),
            "campaign_name": item.get("campaign_name", "(account)"),
            "spend": float(item.get("spend", 0)),
            "impressions": int(item.get("impressions", 0)),
            "clicks": int(item.get("clicks", 0)),
            "purchases": _sum_actions(item.get("actions"), wanted),
            "purchase_value": _sum_actions(item.get("action_values"), wanted),
        }
        for item in data
    ]
