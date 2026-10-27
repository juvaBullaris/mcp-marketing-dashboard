"""Google Analytics 4 via Google's official analytics-mcp server.

Tool used: run_report(property_id, date_ranges, dimensions, metrics, ...)
The response is a GA4 Data API RunReportResponse turned into a dict:
  {dimension_headers: [...], metric_headers: [...],
   rows: [{dimension_values: [{value}], metric_values: [{value}]}]}
"""
from datetime import date

from ..mcp_client import call_tool_json

# GA metric name -> our column name
COLUMNS = {
    "sessions": "sessions",
    "totalUsers": "users",
    "newUsers": "new_users",
    "keyEvents": "key_events",
    "totalRevenue": "revenue",
}


def _get(d: dict, snake: str, camel: str):
    # Proto-to-dict output can use either naming style.
    return d.get(snake, d.get(camel, []))


async def fetch(session, cfg: dict, start: date, end: date):
    args = {
        "property_id": cfg["property_id"],
        "date_ranges": [{"start_date": start.isoformat(), "end_date": end.isoformat()}],
        "dimensions": cfg["dimensions"],
        "metrics": cfg["metrics"],
        "limit": 10000,
    }
    raw = await call_tool_json(session, cfg["tool"], args)
    return raw, normalize(raw, cfg)


def normalize(raw: dict, cfg: dict) -> list[dict]:
    dims = [h["name"] for h in _get(raw, "dimension_headers", "dimensionHeaders")]
    mets = [h["name"] for h in _get(raw, "metric_headers", "metricHeaders")]

    rows = []
    for r in raw.get("rows", []):
        dv = [v.get("value") for v in _get(r, "dimension_values", "dimensionValues")]
        mv = [v.get("value") for v in _get(r, "metric_values", "metricValues")]
        d = dict(zip(dims, dv))
        m = dict(zip(mets, mv))

        ymd = d.get("date", "")  # GA returns YYYYMMDD
        row = {
            "date": f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
            "property_id": str(cfg["property_id"]),
            "channel": d.get("sessionDefaultChannelGroup", "(all)"),
        }
        for metric, col in COLUMNS.items():
            row[col] = float(m.get(metric) or 0)
        rows.append(row)
    return rows
