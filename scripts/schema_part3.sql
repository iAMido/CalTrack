-- CalTrack Schema Part 3 of 3 — Runs, daily summary, calibration
-- Paste this into the Supabase SQL editor and run it AFTER Part 2.

CREATE TABLE IF NOT EXISTS caltrack_runs (
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
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_caltrack_runs_date ON caltrack_runs (run_date DESC);

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
    calibration_trigger TEXT NOT NULL CHECK (calibration_trigger IN ('weekly_auto', 'manual', 'weight_milestone')),
    calibrated_at TIMESTAMPTZ DEFAULT NOW()
);
