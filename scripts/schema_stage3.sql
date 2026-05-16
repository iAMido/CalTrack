-- Stage 3 schema: Coach Reports + Meal Templates
-- Run this in the Supabase SQL editor after schema_part3.sql

-- ── Coach Reports ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS coach_reports (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID        NOT NULL REFERENCES user_profile(id) ON DELETE CASCADE,
  week_start  DATE        NOT NULL,
  week_end    DATE        NOT NULL,
  report_text TEXT        NOT NULL,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_coach_reports_user ON coach_reports(user_id, week_start DESC);

-- ── Meal Templates ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS meal_templates (
  id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID        NOT NULL REFERENCES user_profile(id) ON DELETE CASCADE,
  name            TEXT        NOT NULL,
  total_calories  INTEGER,
  total_protein_g NUMERIC(6,1),
  total_carbs_g   NUMERIC(6,1),
  total_fat_g     NUMERIC(6,1),
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS meal_template_items (
  id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  template_id     UUID        NOT NULL REFERENCES meal_templates(id) ON DELETE CASCADE,
  ingredient_name TEXT        NOT NULL,
  fdc_id          INTEGER,
  weight_grams    INTEGER     NOT NULL,
  calories        INTEGER,
  protein_g       NUMERIC(6,1),
  carbs_g         NUMERIC(6,1),
  fat_g           NUMERIC(6,1),
  fiber_g         NUMERIC(6,1)
);

CREATE INDEX IF NOT EXISTS idx_meal_templates_user ON meal_templates(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_template_items_template ON meal_template_items(template_id);

-- Grants (if you use RLS service role bypass, these are optional but good practice)
GRANT ALL ON coach_reports TO service_role;
GRANT ALL ON meal_templates TO service_role;
GRANT ALL ON meal_template_items TO service_role;
