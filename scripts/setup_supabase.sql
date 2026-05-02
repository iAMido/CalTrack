-- CalTrack — Full Database Schema
-- Run this in the Supabase SQL editor once to create all tables.
-- Uses CREATE TABLE IF NOT EXISTS so it's safe to re-run.

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- 1. user_profile
-- ============================================================
CREATE TABLE IF NOT EXISTS user_profile (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Biometrics
    height_cm INTEGER NOT NULL,
    current_weight_kg DECIMAL(5,2) NOT NULL,
    age INTEGER NOT NULL,
    sex TEXT NOT NULL CHECK (sex IN ('male', 'female')),

    -- Goals
    target_weight_kg DECIMAL(5,2) NOT NULL,
    target_daily_calories INTEGER NOT NULL,
    target_weekly_deficit_kg DECIMAL(3,2) DEFAULT 0.5,

    -- Calculated (updated by calibration)
    bmr INTEGER,
    tdee INTEGER,
    activity_factor DECIMAL(3,2) DEFAULT 1.55,
    last_calibration_date DATE,

    -- Preferences
    food_preferences JSONB DEFAULT '{}'::JSONB,

    -- Telegram
    telegram_chat_id BIGINT UNIQUE NOT NULL,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- 2. usda_foundation  (pre-loaded nutrition data)
-- ============================================================
CREATE TABLE IF NOT EXISTS usda_foundation (
    fdc_id INTEGER PRIMARY KEY,
    description TEXT NOT NULL,
    food_category TEXT,
    calories_per_100g DECIMAL(7,2),
    protein_per_100g DECIMAL(6,2),
    carbs_per_100g DECIMAL(6,2),
    fat_per_100g DECIMAL(6,2),
    fiber_per_100g DECIMAL(6,2),
    sodium_mg_per_100g DECIMAL(7,2),
    sugar_per_100g DECIMAL(6,2),
    search_keywords TEXT[]
);

CREATE INDEX IF NOT EXISTS idx_usda_description ON usda_foundation USING gin(to_tsvector('english', description));
CREATE INDEX IF NOT EXISTS idx_usda_category ON usda_foundation (food_category);

-- ============================================================
-- 3. meals
-- ============================================================
CREATE TABLE IF NOT EXISTS meals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES user_profile(id) NOT NULL,

    meal_type TEXT NOT NULL CHECK (meal_type IN ('breakfast', 'lunch', 'dinner', 'snack')),
    eaten_at TIMESTAMPTZ DEFAULT NOW(),

    photo_path TEXT,

    total_calories INTEGER DEFAULT 0,
    total_protein_g DECIMAL(6,2) DEFAULT 0,
    total_carbs_g DECIMAL(6,2) DEFAULT 0,
    total_fat_g DECIMAL(6,2) DEFAULT 0,
    total_fiber_g DECIMAL(6,2) DEFAULT 0,

    ai_model_used TEXT,
    ai_raw_response JSONB,
    processing_time_ms INTEGER,

    status TEXT DEFAULT 'confirmed' CHECK (status IN ('pending', 'confirmed', 'cancelled')),
    notes TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_meals_date ON meals (eaten_at DESC);
CREATE INDEX IF NOT EXISTS idx_meals_user ON meals (user_id, eaten_at DESC);
CREATE INDEX IF NOT EXISTS idx_meals_status ON meals (status);

-- ============================================================
-- 4. meal_items
-- ============================================================
CREATE TABLE IF NOT EXISTS meal_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meal_id UUID REFERENCES meals(id) ON DELETE CASCADE NOT NULL,

    ingredient_name TEXT NOT NULL,
    ingredient_name_he TEXT,
    fdc_id INTEGER REFERENCES usda_foundation(fdc_id),

    weight_grams INTEGER NOT NULL,
    weight_source TEXT NOT NULL CHECK (weight_source IN (
        'ai_estimate', 'user_confirmed', 'user_corrected', 'personal_db_auto', 'barcode_lookup'
    )),
    ai_estimated_grams INTEGER,

    calories INTEGER,
    protein_g DECIMAL(6,2),
    carbs_g DECIMAL(6,2),
    fat_g DECIMAL(6,2),
    fiber_g DECIMAL(6,2),

    ai_confidence DECIMAL(3,2),

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_meal_items_meal ON meal_items (meal_id);
CREATE INDEX IF NOT EXISTS idx_meal_items_fdc ON meal_items (fdc_id);

-- ============================================================
-- 5. personal_foods
-- ============================================================
CREATE TABLE IF NOT EXISTS personal_foods (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    ingredient_name TEXT NOT NULL,
    fdc_id INTEGER REFERENCES usda_foundation(fdc_id),

    total_times_logged INTEGER DEFAULT 1,
    total_times_corrected INTEGER DEFAULT 0,
    first_logged_at TIMESTAMPTZ DEFAULT NOW(),
    last_logged_at TIMESTAMPTZ DEFAULT NOW(),

    calories_per_100g DECIMAL(7,2),
    protein_per_100g DECIMAL(6,2),
    carbs_per_100g DECIMAL(6,2),
    fat_per_100g DECIMAL(6,2),

    UNIQUE(ingredient_name)
);

-- ============================================================
-- 6. personal_food_logs
-- ============================================================
CREATE TABLE IF NOT EXISTS personal_food_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    personal_food_id UUID REFERENCES personal_foods(id) ON DELETE CASCADE,
    meal_id UUID REFERENCES meals(id) ON DELETE CASCADE,

    meal_type TEXT NOT NULL,
    weight_grams INTEGER NOT NULL,
    weight_source TEXT NOT NULL,

    ai_estimated_grams INTEGER,
    was_corrected BOOLEAN DEFAULT FALSE,

    logged_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pfl_food ON personal_food_logs (personal_food_id, meal_type);
CREATE INDEX IF NOT EXISTS idx_pfl_recent ON personal_food_logs (personal_food_id, logged_at DESC);

-- ============================================================
-- 7. ai_corrections
-- ============================================================
CREATE TABLE IF NOT EXISTS ai_corrections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meal_item_id UUID REFERENCES meal_items(id),

    ingredient_name TEXT NOT NULL,
    meal_type TEXT NOT NULL,
    ai_estimated_grams INTEGER NOT NULL,
    user_corrected_grams INTEGER NOT NULL,

    corrected_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_corrections_ingredient ON ai_corrections (ingredient_name);

-- ============================================================
-- 8. weight_log
-- ============================================================
CREATE TABLE IF NOT EXISTS weight_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES user_profile(id),
    weight_kg DECIMAL(5,2) NOT NULL,
    measured_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_weight_date ON weight_log (measured_at DESC);

-- ============================================================
-- 9. water_log
-- ============================================================
CREATE TABLE IF NOT EXISTS water_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES user_profile(id),
    amount_ml INTEGER NOT NULL,
    logged_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- 10. runs
-- ============================================================
CREATE TABLE IF NOT EXISTS runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES user_profile(id),

    distance_km DECIMAL(5,2),
    duration_minutes INTEGER,
    avg_pace_sec_per_km INTEGER,
    avg_heart_rate INTEGER,
    max_heart_rate INTEGER,
    calories_burned INTEGER,
    elevation_gain_m INTEGER,

    source TEXT NOT NULL CHECK (source IN ('strava', 'garmin', 'manual')),
    external_id TEXT,
    external_url TEXT,

    run_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(source, external_id)
);

CREATE INDEX IF NOT EXISTS idx_runs_date ON runs (run_date DESC);

-- ============================================================
-- 11. daily_summary
-- ============================================================
CREATE TABLE IF NOT EXISTS daily_summary (
    date DATE PRIMARY KEY,
    user_id UUID REFERENCES user_profile(id),

    total_calories_in INTEGER DEFAULT 0,
    total_protein_g DECIMAL(6,2) DEFAULT 0,
    total_carbs_g DECIMAL(6,2) DEFAULT 0,
    total_fat_g DECIMAL(6,2) DEFAULT 0,
    total_fiber_g DECIMAL(6,2) DEFAULT 0,
    meal_count INTEGER DEFAULT 0,

    calories_burned_exercise INTEGER DEFAULT 0,
    bmr_calories INTEGER,
    tdee_calories INTEGER,
    target_calories INTEGER,

    weight_kg DECIMAL(5,2),
    water_ml INTEGER DEFAULT 0,

    auto_approved_meal_pct DECIMAL(3,2),

    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- 12. calibration_log
-- ============================================================
CREATE TABLE IF NOT EXISTS calibration_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    previous_weight_kg DECIMAL(5,2),
    previous_bmr INTEGER,
    previous_tdee INTEGER,
    previous_target_calories INTEGER,

    new_weight_kg DECIMAL(5,2),
    new_bmr INTEGER,
    new_tdee INTEGER,
    new_target_calories INTEGER,

    weight_trend_7d DECIMAL(4,2),
    trigger TEXT NOT NULL CHECK (trigger IN ('weekly_auto', 'manual', 'weight_milestone')),

    calibrated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- Supabase Storage bucket for meal photos
-- Run this separately in Supabase dashboard or via MCP:
-- ============================================================
-- INSERT INTO storage.buckets (id, name, public)
-- VALUES ('meals', 'meals', false)
-- ON CONFLICT (id) DO NOTHING;
