"""Self-hosted dashboard. Reads only from SQLite; never talks to Google or Meta.

    streamlit run dashboard/app.py
"""
import os
import sqlite3
from datetime import date, timedelta

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
DB_PATH = os.environ.get("DB_PATH", "./data/marketing.db")

st.set_page_config(page_title="Marketing Dashboard", layout="wide")


@st.cache_data(ttl=300)
def load(query: str) -> pd.DataFrame:
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(query, conn, parse_dates=["date"] if "date" in query else None)


ga = load("SELECT * FROM ga4_daily")
meta = load("SELECT * FROM meta_daily")
runs = load("SELECT ran_at, source, rows, status, message FROM extract_runs ORDER BY id DESC LIMIT 10")

st.title("Marketing Dashboard")
if ga.empty and meta.empty:
    st.info("No data yet. Run `python -m extractor.run extract` (or `demo`).")
    st.stop()

# ---- Filters ----
all_dates = pd.concat([ga.get("date", pd.Series(dtype="datetime64[ns]")),
                       meta.get("date", pd.Series(dtype="datetime64[ns]"))])
max_d = all_dates.max().date()
picked = st.sidebar.date_input(
    "Date range", (max(all_dates.min().date(), max_d - timedelta(days=29)), max_d)
)
if len(picked) != 2:  # user is mid-selection
    st.stop()
start, end = picked
in_range = lambda df: df[(df["date"].dt.date >= start) & (df["date"].dt.date <= end)] if not df.empty else df
ga, meta = in_range(ga), in_range(meta)

# ---- KPI row ----
def total(df, col):
    return float(df[col].sum()) if not df.empty else 0.0

spend, revenue_meta = total(meta, "spend"), total(meta, "purchase_value")
clicks = total(meta, "clicks")
k = st.columns(6)
k[0].metric("Sessions", f"{total(ga, 'sessions'):,.0f}")
k[1].metric("Users", f"{total(ga, 'users'):,.0f}")
k[2].metric("Key events", f"{total(ga, 'key_events'):,.0f}")
k[3].metric("Meta spend", f"${spend:,.2f}")
k[4].metric("CPC", f"${spend / clicks:,.2f}" if clicks else "–")
k[5].metric("Meta ROAS", f"{revenue_meta / spend:,.2f}x" if spend else "–")

# ---- Trends ----
left, right = st.columns(2)
with left:
    st.subheader("Sessions by channel")
    if not ga.empty:
        st.area_chart(ga.pivot_table(index="date", columns="channel", values="sessions", aggfunc="sum"))
with right:
    st.subheader("Meta spend vs. purchase value")
    if not meta.empty:
        st.line_chart(meta.groupby("date")[["spend", "purchase_value"]].sum())

# ---- Tables ----
st.subheader("Meta campaigns")
if not meta.empty:
    camp = meta.groupby("campaign_name")[["spend", "impressions", "clicks", "purchases", "purchase_value"]].sum()
    camp["ctr_%"] = (camp["clicks"] / camp["impressions"] * 100).round(2)
    camp["cpc"] = (camp["spend"] / camp["clicks"]).round(2)
    camp["roas"] = (camp["purchase_value"] / camp["spend"]).round(2)
    st.dataframe(camp.sort_values("spend", ascending=False), use_container_width=True)

st.subheader("GA4 channels")
if not ga.empty:
    ch = ga.groupby("channel")[["sessions", "users", "key_events", "revenue"]].sum()
    ch["conv_rate_%"] = (ch["key_events"] / ch["sessions"] * 100).round(2)
    st.dataframe(ch.sort_values("sessions", ascending=False), use_container_width=True)

with st.expander("Extraction log"):
    st.dataframe(runs, use_container_width=True)
