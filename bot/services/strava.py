"""
Strava API integration — Stage 2.
Placeholder implementation with OAuth2 refresh and activity fetch stubs.
"""
import httpx
import logging
from bot.utils.config import config

logger = logging.getLogger(__name__)

STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE = "https://www.strava.com/api/v3"

_access_token: str | None = None


async def refresh_access_token() -> str:
    """Refresh the Strava access token using the stored refresh token."""
    if not config.strava_client_id:
        raise ValueError("Strava credentials not configured")

    async with httpx.AsyncClient() as client:
        response = await client.post(STRAVA_TOKEN_URL, data={
            "client_id": config.strava_client_id,
            "client_secret": config.strava_client_secret,
            "refresh_token": config.strava_refresh_token,
            "grant_type": "refresh_token",
        })
        response.raise_for_status()

    data = response.json()
    global _access_token
    _access_token = data["access_token"]
    return _access_token


async def fetch_recent_activities(after_timestamp: int) -> list[dict]:
    """Fetch Strava activities after the given Unix timestamp."""
    global _access_token
    if not _access_token:
        _access_token = await refresh_access_token()

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{STRAVA_API_BASE}/athlete/activities",
            headers={"Authorization": f"Bearer {_access_token}"},
            params={"after": after_timestamp, "per_page": 30},
        )
        if response.status_code == 401:
            _access_token = await refresh_access_token()
            response = await client.get(
                f"{STRAVA_API_BASE}/athlete/activities",
                headers={"Authorization": f"Bearer {_access_token}"},
                params={"after": after_timestamp, "per_page": 30},
            )
        response.raise_for_status()

    return [a for a in response.json() if a.get("type") == "Run"]


def parse_strava_activity(activity: dict, user_weight_kg: float) -> dict:
    """Convert a Strava activity dict to our runs table format."""
    from bot.utils.met_calculator import calculate_calories_burned

    distance_km = round(activity.get("distance", 0) / 1000, 2)
    duration_min = round(activity.get("moving_time", 0) / 60)
    avg_speed_ms = activity.get("average_speed", 0)
    pace_sec_per_km = round(1000 / avg_speed_ms) if avg_speed_ms > 0 else None
    avg_hr = activity.get("average_heartrate")
    strava_calories = activity.get("calories")

    calories = strava_calories or calculate_calories_burned(
        distance_km, duration_min, user_weight_kg, pace_sec_per_km
    )

    return {
        "distance_km": distance_km,
        "duration_minutes": duration_min,
        "avg_pace_sec_per_km": pace_sec_per_km,
        "avg_heart_rate": int(avg_hr) if avg_hr else None,
        "calories_burned": calories,
        "elevation_gain_m": activity.get("total_elevation_gain"),
        "source": "strava",
        "external_id": str(activity["id"]),
        "external_url": f"https://www.strava.com/activities/{activity['id']}",
        "run_date": activity.get("start_date"),
    }
