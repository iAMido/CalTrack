import streamlit as st
import sys, os, asyncio, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dashboard.components.filters import month_selector
from dashboard.components.charts import weight_trend_chart
from bot.db import queries as db_queries
from bot.db import supabase_client as db
from datetime import date


def render():
    st.title("📆 Monthly Overview")
    year, month = month_selector()

    import calendar
    _, last_day = calendar.monthrange(year, month)
    start_str = f"{year}-{month:02d}-01"
    end_str = f"{year}-{month:02d}-{last_day}"

    client = db.get_client()
    summaries = (
        client.table("daily_summary")
        .select("*")
        .gte("date", start_str)
        .lte("date", end_str)
        .order("date")
        .execute()
        .data or []
    )

    if not summaries:
        st.info("No data for selected month.")
        return

    dates = [s["date"] for s in summaries]
    deficits = [
        (s.get("total_calories_in", 0) - s.get("calories_burned_exercise", 0)) - (s.get("target_calories") or 2000)
        for s in summaries
    ]
    weights = [s.get("weight_kg") for s in summaries]

    # Deficit colour table
    df = pd.DataFrame({"date": dates, "deficit": deficits})
    st.dataframe(df.style.background_gradient(cmap="RdYlGn_r", subset=["deficit"]), use_container_width=True)

    weight_data = [(d, w) for d, w in zip(dates, weights) if w]
    if weight_data:
        st.plotly_chart(weight_trend_chart([d for d, _ in weight_data], [w for _, w in weight_data]), use_container_width=True)
