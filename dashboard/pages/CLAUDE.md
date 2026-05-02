# dashboard/pages/ — Dashboard Pages

## What This Is
Each file is one Streamlit page, accessible via the sidebar. Pages are independent — each fetches its own data from Supabase.

## Page Files
| File | Route | Description |
|------|-------|-------------|
| `daily.py` | Daily View | Pick a date, see every meal, item-by-item breakdown, macros pie chart, meal photo thumbnails |
| `weekly.py` | Weekly Trend | Line chart: calories in + calories burned + target, weight overlay, 7-day macro averages |
| `monthly.py` | Monthly Overview | Calendar heatmap (green=deficit, red=surplus), weight trend line, macro distribution |
| `food_diary.py` | Food Diary | All-time food log, searchable by name, sorted by frequency or date |
| `runs.py` | Exercise | Run history table, weekly mileage bar chart, cumulative distance trend |
| `coach_reports.py` | AI Coach | List of past weekly reports, click to expand full Hebrew text |

## Data Access Pattern
Each page imports `from bot.db.queries import ...` to reuse the same query functions as the bot.
