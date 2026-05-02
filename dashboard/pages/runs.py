import streamlit as st
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bot.db import supabase_client as db
from bot.utils.met_calculator import format_pace
import pandas as pd


def render():
    st.title("🏃 Runs")

    client = db.get_client()
    runs = client.table("runs").select("*").order("run_date", desc=True).limit(50).execute().data or []

    if not runs:
        st.info("No runs logged yet.")
        return

    rows = []
    for r in runs:
        pace = format_pace(r["avg_pace_sec_per_km"]) if r.get("avg_pace_sec_per_km") else "—"
        rows.append({
            "Date": r.get("run_date", "")[:10],
            "Distance (km)": r.get("distance_km"),
            "Duration (min)": r.get("duration_minutes"),
            "Pace": pace,
            "Heart Rate": r.get("avg_heart_rate"),
            "Calories": r.get("calories_burned"),
            "Source": r.get("source"),
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True)

    total_km = sum(r.get("distance_km") or 0 for r in runs)
    total_cal = sum(r.get("calories_burned") or 0 for r in runs)
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Runs", len(runs))
    col2.metric("Total Distance", f"{total_km:.1f} km")
    col3.metric("Total Calories Burned", f"{total_cal:,} kcal")
