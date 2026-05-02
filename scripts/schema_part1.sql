-- CalTrack Schema Part 1 of 3 — Core tables
-- Paste this into the Supabase SQL editor and run it.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS user_profile (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    height_cm INTEGER NOT NULL,
    current_weight_kg DECIMAL(5,2) NOT NULL,
    age INTEGER NOT NULL,
    sex TEXT NOT NULL CHECK (sex IN ('male', 'female')),
    target_weight_kg DECIMAL(5,2) NOT NULL,
    target_daily_calories INTEGER NOT NULL,
    target_weekly_deficit_kg DECIMAL(3,2) DEFAULT 0.5,
    bmr INTEGER,
    tdee INTEGER,
    activity_factor DECIMAL(3,2) DEFAULT 1.55,
    last_calibration_date DATE,
    food_preferences JSONB DEFAULT '{}'::JSONB,
    telegram_chat_id BIGINT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

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

CREATE INDEX IF NOT EXISTS idx_usda_category ON usda_foundation (food_category);

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
