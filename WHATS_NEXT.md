# CalTrack — What's Next

## Next Up: Personal Foods Library

### Problem
Every time a user logs "burekas" or "shakshuka", the AI re-analyzes it from scratch. Common personal foods should be saved once and reused — faster, more consistent, and allows the user to correct nutrition values once.

### What Already Exists
- **Table**: `personal_foods` in Supabase (already created in schema)
- **Service**: `bot/services/personal_foods.py` — has basic lookup/save logic
- **Handler scaffolding**: personal foods referenced in photo flow but not fully wired

### Plan
1. **Auto-save confirmed meals** — After a user confirms a meal via inline keyboard, save each ingredient to `personal_foods` with its nutrition values. If it already exists, update the average or keep the latest.

2. **Priority lookup on `/add`** — When processing freeform `/add`, check `personal_foods` first before calling OpenRouter AI. If the user types "burekas", and we have it saved with 350 cal/100g, use that directly.

3. **Dashboard food library page** — The `/caltrack/foods` page in running-coach should show personal foods, allow editing nutrition values, and deleting entries.

4. **Telegram `/foods` command** — List saved personal foods, allow deletion.

### Database Schema (already exists)
```sql
personal_foods (
  id uuid PK,
  user_id uuid FK,
  food_name text,
  food_name_he text,
  fdc_id int,
  calories_per_100g numeric,
  protein_per_100g numeric,
  carbs_per_100g numeric,
  fat_per_100g numeric,
  fiber_per_100g numeric,
  default_weight_grams int,
  use_count int DEFAULT 0,
  created_at timestamptz,
  updated_at timestamptz
)
```

---

## Stage 3 Features (Planned)

### BMR Calibration
- Track actual weight change vs. calorie intake over time
- Calculate real TDEE from data (not just Harris-Benedict estimate)
- Adjust `target_daily_calories` based on observed deficit/surplus

### Strava Sync
- OAuth connect to Strava
- Daily sync at 22:00 (Israel time) via cron job
- Import runs → `runs` table → update `daily_summary.total_calories_out`

### AI Weekly Coach Report
- Runs every Saturday at 22:00 (week = Sunday–Saturday)
- Analyzes: calorie adherence, macro balance, weight trend, exercise
- Output in Hebrew via Telegram message
- Uses Claude (anthropic/claude-sonnet) via OpenRouter

---

## Stage 4 Ideas (Future)

- **Barcode scanning** — Scan product barcode via Telegram photo → lookup in Open Food Facts API
- **Garmin sync** — Import heart rate, steps, calories burned
- **Meal reminders** — Telegram notifications if no meal logged by certain time
- **Meal templates** — Save full meals (not just ingredients) for quick re-logging
- **Photo improvements** — Better photo storage URLs, thumbnail generation
