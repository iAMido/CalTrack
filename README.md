# CalTrack

A single-user, privacy-first calorie tracker. Photograph meals via Telegram → AI identifies the food → confirm weights → calories and macros are logged automatically. Weekly AI coaching reports in Hebrew.

## How It Works

1. Send a meal photo to the Telegram bot
2. The bot uses vision AI (GPT-4o) to identify food items and estimate weights
3. Confirm or correct each item via inline keyboard buttons
4. The system logs nutrition data and shows remaining calories for the day
5. Use `/add`, `/weight`, `/water`, `/run` for manual entries

## Commands

| Command | Action |
|---------|--------|
| 📷 Send photo | Log a meal |
| `/add lunch 150g chicken breast` | Manually add a food item (freeform, AI-parsed) |
| `/barcode` | Photo of a barcode → Open Food Facts lookup → logged |
| `/template` or `/t` | One-tap re-logging from saved meal templates |
| `/label` | Scan a nutrition label → save as a custom food |
| `/weight 87.3` | Log body weight |
| `/water 500` | Log water intake (ml) |
| `/run 5.2 28:30 152` | Log a run manually (km, time, heart rate) |
| `/summary` or `/s` | Today's full summary |
| `/week` or `/w` | This week's summary |
| `/status` | Remaining calories today |
| `/history 5` | Last N meals |
| `/undo` | Cancel last meal |
| `/calibrate` | Recalculate BMR/TDEE from recent data |
| `/stats` | Bot/database statistics |
| `/help` | All commands |

Hebrew input is supported everywhere.

**Exercise data is read, not entered.** Runs come from the separate RunCoach
project through the `caltrack_runs` database view; `/run` exists for anything
RunCoach doesn't cover. There is no Strava integration — it was removed on
2026-08-08 once RunCoach became the source of truth.

---

## Deployment (Hetzner + Docker — Production)

The bot runs 24/7 in a Docker container on the Hetzner VPS `tars-prod`, sharing the
box with the TARS bot. Access is `ssh tars-vps` over Tailscale.

> **Railway was retired on 2026-08-10.** It billed a $5/mo base fee to run a single
> long-polling process, while the existing VPS had ~6.7 GB of RAM sitting idle.
> CalTrack uses about 60 MB there, so the move costs nothing extra.

### Deploy

```bash
git push origin master
ssh tars-vps "cd ~/caltrack && ./deploy.sh"
```

`deploy.sh` fetches, hard-resets to `origin/master`, rebuilds the image, and
restarts the container. **The checkout on the box is disposable — never edit files
there**, since the reset will discard them.

Useful commands:

```bash
ssh tars-vps "cd ~/caltrack && docker compose logs --tail 50"
ssh tars-vps "cd ~/caltrack && docker compose restart"
ssh tars-vps "cd ~/caltrack && docker compose down"     # full stop
```

### Environment Variables

Production values live in `/etc/caltrack/caltrack.env` on the box, owned
`root:tars` mode `0640`. **Never put secrets in any committed file.**

The group-read bit is deliberate: both `docker compose` (via `env_file`) and the
restic backup job run as the `tars` user and must be able to read it.

| Variable | Purpose |
|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather |
| `TELEGRAM_ALLOWED_CHAT_ID` | Your Telegram user ID |
| `OPENROUTER_API_KEY` | OpenRouter API key |
| `OPENROUTER_VISION_MODEL` | e.g. `openai/gpt-4o` |
| `OPENROUTER_COACH_MODEL` | e.g. `anthropic/claude-sonnet-4-5` |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase service_role key |
| `USER_TIMEZONE` | e.g. `Asia/Jerusalem` |

These eight are the complete set. Strava variables are **not** used — that
integration was removed on 2026-08-08 and runs now arrive from RunCoach through
the `caltrack_runs` view. `SUPABASE_DB_PASSWORD` is not read by the bot either.

### Deployment files

| File | Purpose |
|------|---------|
| `Dockerfile` | Container definition; installs `libzbar0` for `pyzbar` |
| `docker-compose.yml` | Restart policy, memory cap, log rotation, `env_file` |
| `deploy.sh` | Pull, rebuild, restart (runs on the box) |
| `.gitattributes` | Forces LF endings so shell scripts work on Linux |

### Backups

`/etc/caltrack/caltrack.env` is included in the TARS restic backup to Backblaze
B2, which runs hourly. It is the only piece of CalTrack state that lives neither
in Supabase nor in git.

---

## Local Development

```bash
# 1. Clone and install dependencies
pip install -r requirements.txt

# 2. Copy .env template and fill in your values
cp .env.example .env

# 3. Run Supabase schema (one-time, in Supabase SQL editor):
#    scripts/schema_part1.sql → schema_part2.sql → schema_part3.sql → schema_grants.sql

# 4. Seed your user profile (one-time):
python scripts/seed_profile.py

# 5. Import USDA nutrition data (one-time):
#    Download data/foundation_food.json and data/sr_legacy_food.json from USDA
python scripts/import_usda.py

# 6. Start the bot
python -m bot.main
```

---

## Project Structure

```
caltrack/
├── bot/                # Telegram bot — the whole application
│   ├── handlers/       # photo, commands, callbacks, admin, label, barcode, template
│   ├── services/       # vision, nutrition, barcode, coach, calibration,
│   │                   # translator, personal_foods, daily_summary, nudge
│   ├── db/             # supabase_client.py, queries.py, models.py
│   └── utils/          # config.py, formatters.py, met_calculator.py, image.py
├── dashboard/          # Abandoned Streamlit prototype — NOT the live dashboard
├── data/               # USDA JSON files (gitignored — download separately)
├── scripts/            # One-time setup + SQL schema files
├── Dockerfile          # Container definition (installs libzbar0 for pyzbar)
├── docker-compose.yml  # Restart policy, memory cap, log rotation
├── deploy.sh           # Pull + rebuild + restart (runs on the VPS)
├── .gitattributes      # Forces LF so shell scripts work on Linux
├── requirements.txt
├── .env.example        # Environment variable template
└── .env                # Local secrets (gitignored — never commit)
```

> The live web dashboard is **not** in this repo. It's a Next.js app in the
> `running-coach` repo under `/caltrack`, pointed at the same Supabase project.
> The `dashboard/` directory here is a dead Streamlit prototype kept only for
> reference.

---

## Security

- **Secrets**: All API keys and tokens are in `.env` locally and in
  `/etc/caltrack/caltrack.env` (`root:tars 0640`) in production. Neither is committed to git.
- **Telegram**: Every incoming message is checked against `TELEGRAM_ALLOWED_CHAT_ID`. Unauthorized users get no response.
- **Supabase**: Uses `service_role` key (kept private). Photos stored in a private storage bucket with no public URLs.
- **Network**: The VPS firewall denies all inbound traffic except SSH and the
  tailnet. The bot long-polls outbound only and publishes no ports — never add a
  `ports:` block to `docker-compose.yml`, as Docker's iptables rules bypass UFW.
- **Log hygiene**: `httpx` logging is pinned to `WARNING` in `bot/main.py`. Telegram
  embeds the bot token in the request URL, and `httpx` logs full URLs at `INFO` —
  which would write the token to disk in cleartext every few seconds.

---

## Development Stages

| Stage | Features | Status |
|-------|----------|--------|
| 1 — MVP | Photo logging, inline confirmation, daily summary, `/run` `/weight` `/water` `/undo` | ✅ Complete |
| 2 — Learning | `/label`, `/add`, Hebrew input, personal food history, meal editing | ✅ Complete |
| 2.5 — Dashboard | Next.js dashboard (in `running-coach`): meals CRUD, weight, overview | ✅ Complete |
| 3 — AI Coach | Weekly Hebrew report, BMR calibration, reports saved to DB | ✅ Complete |
| 3.5 — Templates & Barcode | `/template`, `/barcode`, meal photos in dashboard | ✅ Complete |
| 4 — Extras | Garmin sync, richer reminders, photo improvements | 📋 Future |

See [CLAUDE.md](CLAUDE.md) for current architecture and design decisions, and
[WHATS_NEXT.md](WHATS_NEXT.md) for recent changes.
[caltrack-architecture.md](caltrack-architecture.md) is the original design
blueprint — useful for background, but superseded on several points (it predates
the Hetzner move, the RunCoach exercise view, and the Strava removal).

## WhatsApp (since 2026-10-15)

CalTrack also answers in the WhatsApp group **CalTrack**, through TARS's
`wa-gateway` on the same box. See `bot/whatsapp/__init__.py` and TARS's
`docs/whatsapp-phase3-caltrack.md`.

- **How it works:** the Telegram handlers run unchanged on Telegram-shaped
  objects. Buttons become polls; type `1 150` to set item 1 to 150 g.
  Commands work with or without `/`.
- **Nudges and weekly reports** go to both Telegram and WhatsApp.
- **On/off:** `WA_TOKEN` in `/etc/caltrack/caltrack.env` (off if unset).
  CalTrack listens on `127.0.0.1:8093/wa/inbound`.
- **Tests:** `docker compose run --rm --no-deps caltrack python tests/test_whatsapp.py`
