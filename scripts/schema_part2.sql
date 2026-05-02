-- CalTrack Schema Part 2 of 3 — Learning + tracking tables
-- Paste this into the Supabase SQL editor and run it AFTER Part 1.

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

CREATE TABLE IF NOT EXISTS weight_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES user_profile(id),
    weight_kg DECIMAL(5,2) NOT NULL,
    measured_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_weight_date ON weight_log (measured_at DESC);

CREATE TABLE IF NOT EXISTS water_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES user_profile(id),
    amount_ml INTEGER NOT NULL,
    logged_at TIMESTAMPTZ DEFAULT NOW()
);
