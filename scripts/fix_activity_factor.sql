-- =============================================================
-- Energy model fix — set activity_factor to sedentary baseline
-- =============================================================
-- Why: CalTrack credits every logged workout's calories explicitly
-- (dashboard, /status, coach all compute target + exercise). The old
-- profile value of 1.55 ("moderately active") already includes 3-5
-- workouts/week inside the multiplier — so every run was counted
-- TWICE, inflating run-day budgets by 300-500 kcal.
--
-- The bot now also caps the factor at 1.2 in code (calibration.py),
-- so this UPDATE is belt-and-braces to keep the stored value honest.
--
-- After running: send /calibrate in Telegram to recompute the target.
-- =============================================================

UPDATE user_profile SET activity_factor = 1.2;

-- Verify:
-- SELECT activity_factor, bmr, tdee, target_daily_calories FROM user_profile;
