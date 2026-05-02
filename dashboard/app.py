"""
CalTrack Streamlit Dashboard — Stage 3
Run with: streamlit run dashboard/app.py
"""
import streamlit as st
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

st.set_page_config(
    page_title="CalTrack Dashboard",
    page_icon="🥗",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.sidebar.title("🥗 CalTrack")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigate",
    ["📅 Daily View", "📈 Weekly Trend", "📆 Monthly", "🍽 Food Diary", "🏃 Runs", "🤖 AI Coach Reports"],
)

if page == "📅 Daily View":
    from dashboard.pages.daily import render
    render()
elif page == "📈 Weekly Trend":
    from dashboard.pages.weekly import render
    render()
elif page == "📆 Monthly":
    from dashboard.pages.monthly import render
    render()
elif page == "🍽 Food Diary":
    from dashboard.pages.food_diary import render
    render()
elif page == "🏃 Runs":
    from dashboard.pages.runs import render
    render()
elif page == "🤖 AI Coach Reports":
    from dashboard.pages.coach_reports import render
    render()
