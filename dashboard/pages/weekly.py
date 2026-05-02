import streamlit as st
import sys, os, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dashboard.components.filters import week_selector
from dashboard.components.charts import calorie_bar_chart, weight_trend_chart
from bot.db import queries as db_queries
from bot.db import supabase_client as db
from datetime import timedelta


def render():
    st.title("📈 Weekly Trend")
    start, end = week_selector()

    profile = asyncio.run(db_queries.get_user_profile())
    if not profile:
        st.error("No user profile found.")
        return

    client = db.get_client()
    summaries = (
        client.table("daily_summary")
        .select("*")
        .gte("date", start.isoformat())
        .lte("date", end.isoformat())
        .order("date")
        .execute()
        .data or []
    )

    if not summaries:
        st.info("No data for selected week.")
        return

    dates = [s["date"] for s in summaries]
    cal_in = [s.get("total_calories_in", 0) for s in summaries]
    cal_burned = [s.get("calories_burned_exercise", 0) for s in summaries]
    targets = [s.get("target_calories", 2000) for s in summaries]
    weights = [s.get("weight_kg") for s in summaries]

    st.plotly_chart(calorie_bar_chart(dates, cal_in, cal_burned, targets), use_container_width=True)

    weight_data = [(d, w) for d, w in zip(dates, weights) if w]
    if weight_data:
        st.plotly_chart(weight_trend_chart([d for d, _ in weight_data], [w for _, w in weight_data]), use_container_width=True)

    # Summary table
    avg_cal = sum(cal_in) / len(cal_in) if cal_in else 0
    avg_target = sum(targets) / len(targets) if targets else 0
    col1, col2, col3 = st.columns(3)
    col1.metric("Avg Daily Calories", f"{avg_cal:.0f} kcal")
    col2.metric("Avg Target", f"{avg_target:.0f} kcal")
    col3.metric("Avg Deficit", f"{avg_cal - avg_target:.0f} kcal")
