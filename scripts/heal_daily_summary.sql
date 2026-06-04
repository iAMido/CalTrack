-- =============================================================
-- D2 — One-time healing of stale daily_summary rows
-- =============================================================
-- Run ONCE after applying scripts/schema_daily_summary_pk.sql.
-- Recomputes total_calories_in / macros / meal_count from the raw
-- `meals` table, grouped by Israel local date (matches the way the
-- bot and dashboard now compute summary dates).
--
-- Idempotent — re-running is a no-op once everything is in sync.
-- Wraps in BEGIN/COMMIT so the whole heal succeeds or fails atomically.
-- =============================================================

BEGIN;

WITH actuals AS (
  SELECT
    DATE(eaten_at AT TIME ZONE 'Asia/Jerusalem') AS d,
    user_id,
    SUM(total_calories)::int            AS cal,
    SUM(total_protein_g)::numeric(10,1) AS p,
    SUM(total_carbs_g)::numeric(10,1)   AS c,
    SUM(total_fat_g)::numeric(10,1)     AS f,
    SUM(total_fiber_g)::numeric(10,1)   AS fib,
    COUNT(*)                            AS n
  FROM meals
  WHERE status = 'confirmed'
  GROUP BY 1, 2
)
INSERT INTO daily_summary (user_id, date, total_calories_in, total_protein_g, total_carbs_g, total_fat_g, total_fiber_g, meal_count)
SELECT a.user_id, a.d, a.cal, a.p, a.c, a.f, a.fib, a.n
FROM actuals a
ON CONFLICT (user_id, date) DO UPDATE
SET total_calories_in = EXCLUDED.total_calories_in,
    total_protein_g   = EXCLUDED.total_protein_g,
    total_carbs_g     = EXCLUDED.total_carbs_g,
    total_fat_g       = EXCLUDED.total_fat_g,
    total_fiber_g     = EXCLUDED.total_fiber_g,
    meal_count        = EXCLUDED.meal_count;

COMMIT;

-- Verification — should return zero rows after a successful heal:
-- WITH actuals AS (
--   SELECT DATE(eaten_at AT TIME ZONE 'Asia/Jerusalem') AS d, user_id,
--          SUM(total_calories)::int AS cal, COUNT(*) AS n
--   FROM meals WHERE status = 'confirmed' GROUP BY 1, 2
-- )
-- SELECT ds.date, ds.total_calories_in, a.cal, ds.meal_count, a.n
-- FROM daily_summary ds JOIN actuals a USING (user_id, date)
-- WHERE ds.total_calories_in IS DISTINCT FROM a.cal
--    OR ds.meal_count        IS DISTINCT FROM a.n;
