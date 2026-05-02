# dashboard/ — Streamlit Analytics Dashboard

## What This Is
A visual analytics dashboard (Stage 3). Reads from Supabase and displays calorie trends, macro charts, weight progression, meal drill-downs, and AI Coach reports.

## Stage
This is **Stage 3** functionality. The bot (Stage 1) must be working before building the dashboard.

## Running
```bash
streamlit run dashboard/app.py
```

## Pages
| Page | File | Shows |
|------|------|-------|
| Daily View | `pages/daily.py` | Calendar picker → meals with photos → item breakdown → macros pie |
| Weekly Trend | `pages/weekly.py` | Calories in vs. target vs. TDEE, weight overlay, deficit chart |
| Monthly Overview | `pages/monthly.py` | Heatmap of deficit/surplus days, average macros, weight trend |
| Food Diary | `pages/food_diary.py` | Searchable all-time food log, sorted by frequency |
| Runs | `pages/runs.py` | Run list + stats, weekly mileage, calorie burn trend |
| AI Coach Reports | `pages/coach_reports.py` | Browse past weekly Hebrew reports |

## Tech
- Streamlit for layout + interactivity
- Plotly for charts (line, bar, pie, heatmap)
- supabase-py for data access (same client as bot)

## Future
If Streamlit becomes limiting (mobile UX, real-time updates), the plan is to replace with a Next.js dashboard. See Stage 4 in the main CLAUDE.md.
