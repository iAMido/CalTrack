import streamlit as st
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bot.db import supabase_client as db


def render():
    st.title("🍽 Food Diary")
    search = st.text_input("Search food name")

    client = db.get_client()
    query = client.table("personal_foods").select("*").order("total_times_logged", desc=True)
    if search:
        query = query.ilike("ingredient_name", f"%{search}%")
    foods = query.limit(100).execute().data or []

    if not foods:
        st.info("No foods logged yet.")
        return

    for f in foods:
        with st.expander(f"**{f['ingredient_name']}** — logged {f.get('total_times_logged', 0)}x"):
            col1, col2 = st.columns(2)
            col1.write(f"Calories: {f.get('calories_per_100g', '?')} kcal/100g")
            col1.write(f"Protein: {f.get('protein_per_100g', '?')}g/100g")
            col2.write(f"Carbs: {f.get('carbs_per_100g', '?')}g/100g")
            col2.write(f"Times corrected: {f.get('total_times_corrected', 0)}")
