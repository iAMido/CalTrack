import streamlit as st
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dashboard.components.filters import date_picker
from dashboard.components.charts import macro_pie_chart
from bot.db import queries as db_queries
from bot.db import supabase_client as db
import asyncio


def render():
    st.title("📅 Daily View")
    selected_date = date_picker()
    date_str = selected_date.strftime("%Y-%m-%d")

    profile = asyncio.run(db_queries.get_user_profile())
    if not profile:
        st.error("No user profile found. Run seed_profile.py first.")
        return

    daily = asyncio.run(db_queries.refresh_daily_summary(date_str, profile["id"]))

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Calories In", f"{daily.get('total_calories_in', 0):,} kcal")
    col2.metric("Exercise", f"-{daily.get('calories_burned_exercise', 0):,} kcal")
    net = daily.get('total_calories_in', 0) - daily.get('calories_burned_exercise', 0)
    target = daily.get('target_calories', 0) or 2000
    col3.metric("Net", f"{net:,} kcal", delta=f"{net - target:+,} vs target")
    col4.metric("Weight", f"{daily.get('weight_kg', '—')} kg")

    st.markdown("---")

    # Macro pie
    protein = daily.get('total_protein_g', 0)
    carbs = daily.get('total_carbs_g', 0)
    fat = daily.get('total_fat_g', 0)
    if protein + carbs + fat > 0:
        st.plotly_chart(macro_pie_chart(protein, carbs, fat), use_container_width=True)

    # Meals table
    st.subheader("Meals")
    client = db.get_client()
    meals_result = (
        client.table("meals")
        .select("*")
        .gte("eaten_at", f"{date_str}T00:00:00")
        .lte("eaten_at", f"{date_str}T23:59:59")
        .eq("status", "confirmed")
        .order("eaten_at")
        .execute()
    )
    meals = meals_result.data or []

    if not meals:
        st.info("No meals logged for this date.")
        return

    for meal in meals:
        with st.expander(f"{meal['meal_type'].capitalize()} — {meal['total_calories']} kcal"):
            items_result = client.table("meal_items").select("*").eq("meal_id", meal["id"]).execute()
            items = items_result.data or []
            for item in items:
                st.write(f"• **{item['ingredient_name']}** ({item.get('ingredient_name_he', '')}): "
                         f"{item['weight_grams']}g → {item.get('calories', 0)} kcal | "
                         f"P:{item.get('protein_g', 0):.0f}g C:{item.get('carbs_g', 0):.0f}g F:{item.get('fat_g', 0):.0f}g")
