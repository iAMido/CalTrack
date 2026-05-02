-- CalTrack — Grant permissions to all roles
-- Run this in the Supabase SQL editor once.

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO service_role;

-- Reload PostgREST schema cache so new tables are visible
NOTIFY pgrst, 'reload schema';
