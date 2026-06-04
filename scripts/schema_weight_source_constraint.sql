-- =============================================================
-- C2 — meal_items.weight_source CHECK constraint
-- =============================================================
-- Ensures the column only allows the 5 documented values:
--   ai_estimate, user_confirmed, user_corrected,
--   personal_db_auto, barcode_lookup
--
-- Safe to re-apply: drops any existing CHECK on weight_source first.
-- =============================================================

BEGIN;

-- Drop any pre-existing CHECK constraint(s) on weight_source.
DO $$
DECLARE
  c RECORD;
BEGIN
  FOR c IN
    SELECT con.conname
    FROM pg_constraint con
    JOIN pg_class rel ON rel.oid = con.conrelid
    WHERE rel.relname = 'meal_items'
      AND con.contype = 'c'
      AND pg_get_constraintdef(con.oid) ILIKE '%weight_source%'
  LOOP
    EXECUTE format('ALTER TABLE meal_items DROP CONSTRAINT %I', c.conname);
  END LOOP;
END $$;

-- Re-add canonical CHECK
ALTER TABLE meal_items
  ADD CONSTRAINT meal_items_weight_source_check
  CHECK (weight_source IN (
    'ai_estimate',
    'user_confirmed',
    'user_corrected',
    'personal_db_auto',
    'barcode_lookup'
  ));

COMMIT;
