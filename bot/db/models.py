from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date
import uuid


class UserProfile(BaseModel):
    id: Optional[str] = None
    height_cm: int
    current_weight_kg: float
    age: int
    sex: str
    target_weight_kg: float
    target_daily_calories: int
    target_weekly_deficit_kg: float = 0.5
    bmr: Optional[int] = None
    tdee: Optional[int] = None
    activity_factor: float = 1.55
    telegram_chat_id: int
    food_preferences: dict = {}


class UsdaFood(BaseModel):
    fdc_id: int
    description: str
    food_category: Optional[str] = None
    calories_per_100g: Optional[float] = None
    protein_per_100g: Optional[float] = None
    carbs_per_100g: Optional[float] = None
    fat_per_100g: Optional[float] = None
    fiber_per_100g: Optional[float] = None


class Meal(BaseModel):
    id: Optional[str] = None
    user_id: str
    meal_type: str
    eaten_at: Optional[str] = None
    photo_path: Optional[str] = None
    total_calories: int = 0
    total_protein_g: float = 0
    total_carbs_g: float = 0
    total_fat_g: float = 0
    total_fiber_g: float = 0
    ai_model_used: Optional[str] = None
    status: str = "confirmed"


class MealItem(BaseModel):
    id: Optional[str] = None
    meal_id: str
    ingredient_name: str
    ingredient_name_he: Optional[str] = None
    fdc_id: Optional[int] = None
    weight_grams: int
    weight_source: str
    ai_estimated_grams: Optional[int] = None
    calories: Optional[int] = None
    protein_g: Optional[float] = None
    carbs_g: Optional[float] = None
    fat_g: Optional[float] = None
    fiber_g: Optional[float] = None
    ai_confidence: Optional[float] = None


class WeightEntry(BaseModel):
    id: Optional[str] = None
    user_id: str
    weight_kg: float
    measured_at: Optional[str] = None


class WaterEntry(BaseModel):
    id: Optional[str] = None
    user_id: str
    amount_ml: int
    logged_at: Optional[str] = None


class Run(BaseModel):
    id: Optional[str] = None
    user_id: str
    distance_km: Optional[float] = None
    duration_minutes: Optional[int] = None
    avg_pace_sec_per_km: Optional[int] = None
    avg_heart_rate: Optional[int] = None
    calories_burned: Optional[int] = None
    elevation_gain_m: Optional[int] = None
    source: str = "manual"
    external_id: Optional[str] = None
    run_date: Optional[str] = None


class DailySummary(BaseModel):
    date: str
    user_id: str
    total_calories_in: int = 0
    total_protein_g: float = 0
    total_carbs_g: float = 0
    total_fat_g: float = 0
    total_fiber_g: float = 0
    meal_count: int = 0
    calories_burned_exercise: int = 0
    bmr_calories: Optional[int] = None
    tdee_calories: Optional[int] = None
    target_calories: Optional[int] = None
    weight_kg: Optional[float] = None
    water_ml: int = 0
