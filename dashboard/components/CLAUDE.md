# dashboard/components/ — Reusable Dashboard Components

## What This Is
Reusable Streamlit + Plotly components shared across multiple dashboard pages.

## Files
| File | Exports | Used By |
|------|---------|---------|
| `charts.py` | `calorie_bar_chart()`, `macro_pie_chart()`, `weight_trend_chart()`, `deficit_heatmap()`, `weekly_line_chart()` | All pages |
| `filters.py` | `date_picker()`, `week_selector()`, `month_selector()` | daily.py, weekly.py, monthly.py |

## Design Principle
Components return Plotly figures — the page calls `st.plotly_chart(fig)`. This keeps chart logic separate from layout/data-fetching logic.
