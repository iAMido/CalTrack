# CalTrack — Main Project

## What This Is
A single-user, privacy-first calorie tracking system. Photograph meals via Telegram, AI identifies the food, confirm weights, and the system tracks calories + macros automatically. Weekly AI coaching reports in Hebrew.

## Architecture Overview
- **Input**: Telegram Bot (`bot/`) — photo → OpenRouter Vision AI → inline keyboard confirmation
- **Input**: Freeform `/add` command — Hebrew text → AI breakdown → nutrition calculation
- **Input**: `/barcode` command — photo → pyzbar decode → Open Food Facts API → save meal
- **Input**: `/template` command — one-tap re-logging from saved meal templates
- **Database**: Supabase (PostgreSQL + Storage) — service_role key, all tables in public schema
- **Dashboard**: Next.js web app (lives in `running-coach` repo at `/caltrack`) — meals CRUD, weight, overview, coach reports
- **Nutrition Data**: USDA SR Legacy + Foundation Foods (8,156 foods in `usda_foundation` table)
- **Nutrition (freeform)**: AI-provided values (OpenRouter gpt-4o-mini) — used directly, not USDA matched
- **Exercise**: Manual `/run` command; all other runs come from RunCoach via the `caltrack_runs` view (no sync in CalTrack)
- **AI Coach**: Weekly Hebrew report (Saturday 22:00) — saved to DB + displayed in dashboard
- **Language**: Hebrew input supported everywhere via translation layer (gpt-4o-mini)

## Directory Map
```
caltrack/
├── bot/            # Telegram bot — core application
│   ├── handlers/   # photo.py, commands.py, callbacks.py, admin.py, label.py,
│   │               # barcode.py, template.py
│   ├── services/   # vision.py, nutrition.py, personal_foods.py, calibration.py,
│   │               # daily_summary.py, translator.py, barcode.py, coach.py
│   ├── db/         # supabase_client.py, queries.py, models.py
│   └── utils/      # config.py, formatters.py, met_calculator.py
├── dashboard/      # (unused — dashboard lives in running-coach repo at /caltrack)
├── data/           # USDA JSON files (gitignored)
└── scripts/        # One-time setup scripts
```

## Key Files
- `bot/main.py` — entry point: `python -m bot.main`
- `bot/utils/config.py` — all config loaded from `.env` via pydantic-settings
- `bot/db/supabase_client.py` — Supabase REST helpers (insert/upsert/select/update)
- `bot/db/queries.py` — higher-level queries; paginates USDA load (8k+ rows)
- `bot/services/vision.py` — OpenRouter vision AI (meal photos) + label extraction
- `bot/services/nutrition.py` — 8k USDA in-memory cache + fuzzy matcher + AI fallback
- `bot/services/translator.py` — Hebrew→English translation (fast local map + gpt-4o-mini)
- `bot/services/barcode.py` — pyzbar decode + Open Food Facts product lookup
- `bot/services/coach.py` — weekly AI report generation + DB persistence
- `bot/handlers/label.py` — `/label` command: scan nutrition label → save custom food
- `bot/handlers/barcode.py` — `/barcode` command: photo → decode → lookup → save meal
- `bot/handlers/template.py` — `/template` command: one-tap logging from saved templates
- `scripts/import_usda.py` — imports Foundation Foods + SR Legacy + FNDDS (any available)
- `scripts/schema_stage3.sql` — DDL for coach_reports, meal_templates, meal_template_items
- `.env` — local secrets (gitignored)

## Development Stages
| Stage | Features | Status |
|-------|----------|--------|
| 1 — MVP | Photo logging, inline confirmation, daily summary, /run /weight /water /undo | ✅ Complete |
| 2 — Learning | /label, /add (freeform AI), per-item rename, Hebrew input, meal editing, personal food history | ✅ Complete |
| 2.5 — Dashboard | Next.js dashboard (in running-coach): meals CRUD, AI analysis, weight tracking, overview | ✅ Complete |
| 3 — AI Coach | Weekly Hebrew report, BMR calibration, coach reports saved to DB | ✅ Complete |
| 3.5 — Templates & Barcode | /template command, /barcode command, meal photos in dashboard, personal foods in Add Meal | ✅ Complete |
| 4 — Extras | Garmin sync, reminders, photo improvements | 📋 Future |

## Dashboard (Next.js — lives in running-coach repo)
The CalTrack web dashboard is at `C:\Users\ido\running-coach\app\caltrack\`. It connects to the same Supabase database as the Telegram bot.

**Dashboard pages:**
- `/caltrack` — Overview: today's calories/macros, weight chart, weekly averages
- `/caltrack/meals` — Meals list with add/edit/delete, AI analysis, date range filter
- `/caltrack/weight` — Weight log
- `/caltrack/foods` — Food database browser

**Dashboard API routes** (`running-coach/app/api/caltrack/`):
- `meals/route.ts` — GET meals list (with ingredient names)
- `meals/add/route.ts` — POST new meal with ingredients
- `meals/edit/route.ts` — PUT edit meal (type, ingredients, recalculate)
- `meals/delete/route.ts` — DELETE meal (cascades: ai_corrections → meal_items → meal)
- `analyze/route.ts` — POST AI food analysis (Hebrew → ingredients + nutrition)
- `overview/route.ts` — GET daily summary + stats

## Key Design Decisions
- **Freeform `/add` uses AI nutrition directly** — not USDA fuzzy matching. USDA matching caused accuracy issues (e.g., "egg" matched "Egg, whole, dried" at 575 cal/100g). AI values from gpt-4o-mini are more accurate for freeform text input.
- **Original Hebrew description saved in `meals.notes`** — displayed as meal title in dashboard instead of ingredient names. E.g., "3 מיני בורקסים" shows as the title.
- **`weight_source` constraint** — `meal_items.weight_source` must be one of: `ai_estimate`, `user_confirmed`, `user_corrected`, `personal_db_auto`, `barcode_lookup`. Dashboard uses `ai_estimate` for new meals, `user_corrected` for edits.
- **`caltrack_runs` is a VIEW, not a table** (since 2026-08-08, `scripts/schema_stage4_runcoach_runs_view.sql`). CalTrack's Strava sync died on 2026-06-29 and five weeks of exercise calories silently read as zero. RunCoach syncs into the same Supabase project, so the view reads `runcoach.runs` directly — no sync, no API call, no CalTrack code change. Writes from `/run` still work: `INSTEAD OF` triggers route them to the retained physical table `_bak_caltrack_runs`. Rows sourced from RunCoach reject UPDATE/DELETE with a clear error.
- **CalTrack has no Strava integration** (removed 2026-08-08). RunCoach moved off Strava to intervals.icu, so its rows reach the view as `source='intervals_sync'`. The old `_run_exists()` dedupe matched on `source='strava'` and would not have caught them — a re-enabled sync would have re-imported runs that were already visible, double-counting them. `bot/services/strava.py`, the 22:00 job, `/syncstrava` and the `strava_tokens` table are all gone. `/run` is the only remaining writer. Do not re-add a sync: the view already provides the data.
- **Exercise-calorie changeover date: 2026-06-29.** The view serves history (`<= 2026-06-29`) from the preserved CalTrack rows and only reads RunCoach from `2026-06-30` on. The two systems disagree on **every** shared run — mean 30.4 kcal, range −137..+108, net just −81 kcal — because `strava.py` stored `strava_calories or MET_fallback` while RunCoach stored its own figure. Serving history from RunCoach would retroactively restate an already-reconciled deficit/weight series. Do not "simplify" the view by dropping the cutover.

## First-Time Setup
```bash
pip install -r requirements.txt
# 1. Run schema in Supabase SQL editor (in order):
#    scripts/schema_part1.sql, schema_part2.sql, schema_part3.sql, schema_grants.sql
# 2. Seed profile:
python scripts/seed_profile.py
# 3. Download USDA datasets to data/ and import:
#    data/foundation_food.json  (Foundation Foods)
#    data/sr_legacy_food.json   (SR Legacy — recommended)
python scripts/import_usda.py
# 4. Storage bucket 'meals' already created (private, via SQL)
# 5. Start the bot:
python -m bot.main
```

## Environment Variables (.env)
| Variable | Purpose |
|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather |
| `TELEGRAM_ALLOWED_CHAT_ID` | Your Telegram user ID (single-user auth) |
| `OPENROUTER_API_KEY` | OpenRouter key for Vision AI + Coach + translation |
| `OPENROUTER_VISION_MODEL` | e.g. `openai/gpt-4o` |
| `OPENROUTER_COACH_MODEL` | e.g. `anthropic/claude-sonnet-4-5` |
| `SUPABASE_URL` | Project URL |
| `SUPABASE_KEY` | service_role key (bypasses RLS) |
| `USER_TIMEZONE` | e.g. `Asia/Jerusalem` |

## Deployment (Hetzner + Docker)
The bot runs 24/7 in a Docker container on the Hetzner box `tars-prod`, alongside
the TARS bot. **Railway was retired 2026-08-10** — it charged a $5/mo base fee for
one long-polling process, and the box already had 6.7 GB of RAM idle. CalTrack's
actual footprint is ~60 MB.

Reach the box with `ssh tars-vps` (user `tars`, key auth, over Tailscale).

**Layout on the box:**
- `~/caltrack/` — git checkout, hard-reset to origin on every deploy. Never edit here.
- `/etc/caltrack/caltrack.env` — the 8 runtime secrets, `root:tars 0640`.
  Group-readable by `tars` on purpose: both `docker compose` and the restic
  backup job run as `tars` and must read it.
- Logs — `docker compose logs`, capped at 10 MB × 5 by `docker-compose.yml`.

**Deploy workflow:**
```bash
git push origin master
ssh tars-vps "cd ~/caltrack && ./deploy.sh"   # pull, rebuild, restart
```

**Files that matter:**
- `Dockerfile` — installs `libzbar0` (required by `pyzbar`; the container has no
  system Python packages to fall back on)
- `docker-compose.yml` — `restart: unless-stopped`, `mem_limit: 768m`, log caps.
  **Never add a `ports:` block** — the bot only makes outbound connections, and
  Docker's iptables rules would punch straight through UFW.
- `.dockerignore` — must keep `!requirements.txt` (the `*.txt` pattern above it
  would otherwise exclude the manifest and break the build). `.gitignore` has the
  same trap and the same escape.
- `.gitattributes` — forces LF on `*.sh`/`*.yml`/`Dockerfile`. Development is on
  Windows; a CRLF shebang fails on Linux with `bad interpreter: ...^M`.

**Backups:** `/etc/caltrack/caltrack.env` is included in the TARS restic backup
(`~/tars/scripts/tars-backup.sh`), which runs hourly to Backblaze B2. That file is
the only CalTrack state not in Supabase or git.

**Dependency rule:** `python-telegram-bot==21.3` requires `httpx~=0.27`. Use
`supabase>=2.7.0` — older supabase pins httpx<0.26 and causes a build conflict.

**Important:** Only one bot instance can poll Telegram at a time. Running locally
while the container is up causes a 409 Conflict. Run `docker compose down` on the
box first, or don't run locally.

**Restart semantics — `docker kill` is not a crash test.** Docker flags any
`docker kill`/`docker stop` as a *manual* stop, and `restart: unless-stopped`
deliberately does not restart from those. `os.kill(1, SIGKILL)` from inside the
container does nothing either — the kernel shields PID 1 from signals originating
in its own namespace. To genuinely test crash recovery:
```bash
ssh tars-vps 'sudo kill -9 $(docker inspect caltrack --format "{{.State.Pid}}")'
```
Then confirm `RestartCount` incremented.

## Security
- Telegram: all updates checked against `TELEGRAM_ALLOWED_CHAT_ID`
- Supabase: service_role key kept in `.env` (gitignored) locally and in
  `/etc/caltrack/caltrack.env` (`root:tars 0640`) in production — never committed
- Photos stored in private Supabase Storage bucket `meals` (no public URLs)
- Host firewall denies all inbound except `22/tcp` and the tailnet. CalTrack needs
  no inbound ports; if a change appears to require one, something is wrong.
- **`httpx` logging is pinned to WARNING in `bot/main.py`.** Telegram embeds the
  bot token in the URL path, and `httpx` logs full URLs at INFO — leaving it at
  INFO writes the token to disk in cleartext every ~10 seconds. Do not revert this
  to INFO for debugging without redacting.
