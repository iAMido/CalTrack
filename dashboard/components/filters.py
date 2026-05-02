"""Reusable Streamlit filter widgets."""
import streamlit as st
from datetime import date, timedelta


def date_picker(label: str = "Select date", default: date = None) -> date:
    return st.date_input(label, value=default or date.today())


def week_selector() -> tuple[date, date]:
    """Returns (start_date, end_date) for selected week."""
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    col1, col2 = st.columns(2)
    with col1:
        start = st.date_input("Week start", value=start_of_week)
    with col2:
        end = st.date_input("Week end", value=start_of_week + timedelta(days=6))
    return start, end


def month_selector() -> tuple[int, int]:
    """Returns (year, month)."""
    today = date.today()
    col1, col2 = st.columns(2)
    with col1:
        year = st.number_input("Year", min_value=2024, max_value=2030, value=today.year)
    with col2:
        month = st.selectbox("Month", list(range(1, 13)),
                             index=today.month - 1,
                             format_func=lambda m: date(2024, m, 1).strftime("%B"))
    return int(year), int(month)
