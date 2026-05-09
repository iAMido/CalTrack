-- Strava token storage for CalTrack bot
-- Run this in Supabase SQL editor

CREATE TABLE IF NOT EXISTS strava_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES user_profile(id),
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Grant access
GRANT ALL ON strava_tokens TO service_role;
