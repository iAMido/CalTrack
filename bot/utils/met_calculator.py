def pace_to_sec_per_km(pace_str: str) -> int:
    """Convert 'MM:SS' pace string to seconds per km."""
    parts = pace_str.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid pace format: {pace_str}")
    return int(parts[0]) * 60 + int(parts[1])


def get_met(sec_per_km: int) -> float:
    """Return MET value based on running pace."""
    if sec_per_km < 300:    # faster than 5:00/km
        return 11.0
    elif sec_per_km < 360:  # 5:00–6:00/km
        return 9.8
    elif sec_per_km < 420:  # 6:00–7:00/km
        return 8.3
    else:                   # slower than 7:00/km
        return 7.0


def calculate_calories_burned(
    distance_km: float,
    duration_minutes: int,
    weight_kg: float,
    avg_pace_sec_per_km: int | None = None,
) -> int:
    """
    Calculate calories burned running using the MET formula.
    Falls back to pace derived from distance/duration if avg_pace not given.
    """
    if avg_pace_sec_per_km:
        pace = avg_pace_sec_per_km
    elif distance_km > 0:
        pace = int((duration_minutes * 60) / distance_km)
    else:
        pace = 420  # default to slow jog

    met = get_met(pace)
    duration_hours = duration_minutes / 60
    return round(met * weight_kg * duration_hours)


def format_pace(sec_per_km: int) -> str:
    """Convert seconds/km to 'M:SS' display string."""
    minutes = sec_per_km // 60
    seconds = sec_per_km % 60
    return f"{minutes}:{seconds:02d}"
