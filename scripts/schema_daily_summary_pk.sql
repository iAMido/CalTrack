-- =============================================================
-- C1 — daily_summary primary key migration
-- =============================================================
-- Before: PRIMARY KEY (date)                     ← single-tenant only
-- After:  PRIMARY KEY (user_id, date)            ← multi-tenant safe
--
-- Why: dashboard and bot upserts both target daily_summary. With the
-- old single-column PK, an upsert by `date` alone could overwrite
-- another user's row in a multi-user world, and it forced every upsert
-- to use `on_conflict='date'` which is brittle. The (user_id, date)
-- composite PK makes upserts merge correctly per user.
--
-- Safe to re-run: uses IF EXISTS guards.
-- =============================================================

BEGIN;

-- 1. Drop the existing PK (only if it is on `date` alone)
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    WHERE t.relname = 'daily_summary'
      AND c.contype = 'p'
      AND (
        SELECT array_agg(attname ORDER BY attnum)
        FROM pg_attribute
        WHERE attrelid = c.conrelid AND attnum = ANY(c.conkey)
      ) = ARRAY['date']::name[]
  ) THEN
    ALTER TABLE daily_summary DROP CONSTRAINT daily_summary_pkey;
  END IF;
END $$;

-- 2. Make sure user_id is NOT NULL before we use it in the PK
ALTER TABLE daily_summary
  ALTER COLUMN user_id SET NOT NULL;

-- 3. Add the composite PK (only if it doesn't already exist)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    WHERE t.relname = 'daily_summary'
      AND c.contype = 'p'
  ) THEN
    ALTER TABLE daily_summary ADD PRIMARY KEY (user_id, date);
  END IF;
END $$;

COMMIT;

-- Verification:
-- SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint
-- WHERE conrelid = 'daily_summary'::regclass AND contype = 'p';
-- Expected: PRIMARY KEY (user_id, date)
