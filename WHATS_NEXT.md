# CalTrack — What's Next

## Recently Completed (2026-08-08)

### Exercise calories now read from RunCoach
- **`caltrack_runs` is a view** over `runcoach.runs` (cutover 2026-06-29) — recovered 18 runs / 9,450 kcal that had silently counted as zero since the Strava outage
- **Strava sync removed** — RunCoach moved to intervals.icu, so its rows arrive as `source='intervals_sync'`; the old `source='strava'` dedupe would not have caught them and a re-enabled sync would have double-counted. `strava.py`, the 22:00 job, `/syncstrava` and `strava_tokens` are gone
- **`/run` still works** — routed to the backing table by `INSTEAD OF` triggers

## Recently Completed (2026-05-16)

### Stage 3 — AI Coach + Strava + Calibration
- **BMR Calibration** — `/calibrate` command, auto-recalibrate on weight milestones
- **Strava Sync** — OAuth connected, daily sync at 22:00, `/syncstrava` manual trigger
- **AI Weekly Coach** — Saturday 22:00 report in Hebrew, saved to `coach_reports` table
- **Coach Reports Dashboard** — `/caltrack/coach` page with expandable RTL reports

### Stage 3.5 — Templates, Barcode, Photos
- **Barcode Scanning** — `/barcode` command: send photo of barcode → pyzbar decodes → Open Food Facts lookup → log meal with nutrition
- **Meal Templates** — Save full meals from dashboard, `/template` or `/t` in Telegram to log instantly
- **Meal Photos in Dashboard** — Signed URLs from Supabase Storage, thumbnails in meal list
- **Personal Foods in Add Meal** — Dashboard "My Foods" tab in Add Meal modal for quick re-use
- **DB Schema** — `coach_reports`, `meal_templates`, `meal_template_items` tables created

---

## Remaining Polish & Improvements

### Personal Foods — Deeper Integration
- [ ] Auto-save confirmed meals to `personal_foods` (currently relies on photo flow only)
- [ ] `/foods` Telegram command to list/delete personal foods
- [ ] Priority lookup in `/add` — check personal_foods before calling AI

### Dashboard Enhancements
- [ ] Meal photo lightbox (click thumbnail to see full image)
- [ ] Template management page (edit/delete templates from dashboard)
- [ ] Foods page improvements (edit nutrition values, delete entries)

### Bot Quality of Life
- [ ] `/template` with meal type override: `/t lunch burger meal`
- [ ] Barcode — handle multiple barcodes in one image
- [ ] Better error messages when Open Food Facts has no data for a barcode

---

## Stage 4 Ideas (Future)

- **Garmin sync** — Import heart rate, steps, calories burned
- **Meal reminders** — Telegram notifications if no meal logged by certain time
- **Photo improvements** — Thumbnail generation, image compression
- **Weekly trends chart** — Visual weight/calorie trend in dashboard
- **Export** — CSV/PDF export of meal history
