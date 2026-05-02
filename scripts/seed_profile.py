"""
One-time script: Creates the user profile in Supabase.
Run once after setting up the database schema.

Usage: python scripts/seed_profile.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from supabase import create_client
from dotenv import load_dotenv
import math

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_ALLOWED_CHAT_ID", "0"))

# ============================================================
# USER PROFILE DATA — edit these values
# ============================================================
PROFILE = {
    "height_cm": 183,
    "current_weight_kg": 90.0,
    "age": 44,
    "sex": "male",
    "target_weight_kg": 81.0,
    "target_weekly_deficit_kg": 0.5,   # 0.5 kg/week loss
    "activity_factor": 1.55,           # moderate activity
    "telegram_chat_id": TELEGRAM_CHAT_ID,
    "food_preferences": {
        "likes": ["grilled meats", "salads", "rice dishes", "eggs"],
        "dislikes": [],
        "allergies": [],
        "cooking_style": "simple, quick meals"
    },
}
# ============================================================


def calculate_bmr(weight_kg, height_cm, age, sex):
    """Mifflin-St Jeor equation."""
    base = (10 * weight_kg) + (6.25 * height_cm) - (5 * age)
    return round(base + 5 if sex == "male" else base - 161)


def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERROR: SUPABASE_URL and SUPABASE_KEY must be set in .env")
        sys.exit(1)

    if TELEGRAM_CHAT_ID == 0:
        print("ERROR: TELEGRAM_ALLOWED_CHAT_ID must be set in .env")
        sys.exit(1)

    client = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Calculate BMR and TDEE
    bmr = calculate_bmr(
        PROFILE["current_weight_kg"],
        PROFILE["height_cm"],
        PROFILE["age"],
        PROFILE["sex"],
    )
    tdee = round(bmr * PROFILE["activity_factor"])

    # Calculate daily deficit target
    daily_deficit = (PROFILE["target_weekly_deficit_kg"] * 7700) / 7
    target_calories = round(tdee - daily_deficit)
    min_calories = 1500  # male minimum

    if target_calories < min_calories:
        print(f"WARNING: Calculated target {target_calories} kcal is below minimum {min_calories} kcal. Capping at {min_calories}.")
        target_calories = min_calories

    profile_data = {
        **PROFILE,
        "bmr": bmr,
        "tdee": tdee,
        "target_daily_calories": target_calories,
    }

    result = client.table("user_profile").upsert(
        profile_data,
        on_conflict="telegram_chat_id",
    ).execute()

    print("\n[OK] User profile created/updated successfully!")
    print(f"   Height: {PROFILE['height_cm']} cm")
    print(f"   Weight: {PROFILE['current_weight_kg']} kg -> Target: {PROFILE['target_weight_kg']} kg")
    print(f"   BMR: {bmr} kcal/day")
    print(f"   TDEE: {tdee} kcal/day (activity factor: {PROFILE['activity_factor']})")
    print(f"   Daily target: {target_calories} kcal/day")
    print(f"   Weekly loss target: {PROFILE['target_weekly_deficit_kg']} kg/week")
    print(f"   Telegram chat ID: {TELEGRAM_CHAT_ID}")
    print(f"\n   Profile ID: {result.data[0]['id']}")


if __name__ == "__main__":
    main()
