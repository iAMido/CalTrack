"""Reusable Plotly chart components for the CalTrack dashboard."""
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd


def calorie_bar_chart(dates: list, calories_in: list, calories_out: list, targets: list) -> go.Figure:
    fig = go.Figure()
    fig.add_bar(x=dates, y=calories_in, name="Calories In", marker_color="#FF6B6B")
    fig.add_bar(x=dates, y=calories_out, name="Exercise Burn", marker_color="#4ECDC4")
    fig.add_scatter(x=dates, y=targets, name="Target", mode="lines", line=dict(color="#FFE66D", dash="dash", width=2))
    fig.update_layout(
        title="Daily Calories",
        barmode="group",
        xaxis_title="Date",
        yaxis_title="kcal",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def macro_pie_chart(protein_g: float, carbs_g: float, fat_g: float) -> go.Figure:
    prot_cal = protein_g * 4
    carbs_cal = carbs_g * 4
    fat_cal = fat_g * 9
    total = prot_cal + carbs_cal + fat_cal or 1
    fig = go.Figure(go.Pie(
        labels=["Protein", "Carbs", "Fat"],
        values=[prot_cal, carbs_cal, fat_cal],
        marker_colors=["#4ECDC4", "#FFE66D", "#FF6B6B"],
        textinfo="label+percent",
    ))
    fig.update_layout(title="Macro Split (by calories)")
    return fig


def weight_trend_chart(dates: list, weights: list) -> go.Figure:
    fig = go.Figure()
    fig.add_scatter(x=dates, y=weights, mode="lines+markers", name="Weight",
                    line=dict(color="#4ECDC4", width=2), marker=dict(size=6))
    if len(weights) >= 2:
        # Simple linear trend
        import numpy as np
        x_num = list(range(len(dates)))
        coeffs = np.polyfit(x_num, weights, 1)
        trend = [coeffs[0] * i + coeffs[1] for i in x_num]
        fig.add_scatter(x=dates, y=trend, mode="lines", name="Trend",
                        line=dict(color="#FF6B6B", dash="dash", width=1))
    fig.update_layout(title="Weight Trend (kg)", xaxis_title="Date", yaxis_title="kg")
    return fig


def deficit_heatmap(df: pd.DataFrame) -> go.Figure:
    """df must have columns: date, deficit (negative = good)"""
    fig = go.Figure(go.Heatmap(
        z=df["deficit"].tolist(),
        x=df["date"].tolist(),
        colorscale=[[0, "#4ECDC4"], [0.5, "#FFFFFF"], [1, "#FF6B6B"]],
        colorbar=dict(title="kcal"),
    ))
    fig.update_layout(title="Daily Deficit Heatmap (green = deficit, red = surplus)")
    return fig


def weekly_line_chart(dates: list, cal_in: list, cal_net: list, targets: list, weights: list) -> go.Figure:
    fig = go.Figure()
    fig.add_scatter(x=dates, y=cal_in, name="Calories In", mode="lines+markers", line=dict(color="#FF6B6B"))
    fig.add_scatter(x=dates, y=cal_net, name="Net Calories", mode="lines+markers", line=dict(color="#FF9F43"))
    fig.add_scatter(x=dates, y=targets, name="Target", mode="lines", line=dict(color="#FFE66D", dash="dash"))
    fig.update_layout(title="Weekly Calorie Trend", xaxis_title="Date", yaxis_title="kcal")
    return fig
