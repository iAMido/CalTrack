import streamlit as st
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def render():
    st.title("🤖 AI Coach Reports")
    st.info("AI Coach reports (Stage 3) will appear here once the weekly analysis feature is enabled.")
    st.markdown("""
    **What's coming:**
    - Weekly Hebrew analysis reports
    - Deficit tracking and trend analysis
    - Macro balance feedback
    - Personalized recipe suggestions
    - Week-over-week comparison

    Enable by adding your OpenRouter API key to `.env` and running the weekly coach.
    """)
