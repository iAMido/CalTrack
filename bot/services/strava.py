import httpx
import logging
from datetime import datetime, timedelta
import pytz
from bot.utils.config import config
from bot.db import supabase_client as db
from bot.db import queries as db_queries
from bot.utils.met_calculator import calculate_calories_burned, format_pace

logger = logging.getLogger(__name__)

STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE = "https://www.strava.com/api/v3"

_access_token: str | None = None


def is_configured() -> bool:
    return bool(config.strava_client_id and config.strava_client_secret and config.strava_refresh_token)


async def _get_stored_token() -> dict | None:
    """Read stored token from DB (survives token rotation)."""
    try:
        client = db.get_client()
        result = (
            client.table("strava_tokens")
            .select("access_token,refresh_token,expires_at")
            .limit(1)
            .single()
            .execute()
        )
        return result.data
    except Exception:
        return None


async def _save_token(access_token: str, refresh_token: str, expires_at: int, user_id: str) -> None:
    """Save/update token in DB so the rotated refresh_token is preserved."""
    try:
        client = db.get_client()
        token_data = {
            "user_id": user_id,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": datetime.utcfromtimestamp(expires_at).isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        # Try upsert — if table doesn't exist yet, just log warning
        existing = await _get_stored_token()
        if existing:
            client.table("strava_tokens").update(token_data).neq("id", "00000000-0000-0000-0000-000000000000").execute()
        else:
            client.table("strava_tokens").insert(token_data).execute()
        logger.info("Strava token saved to DB")
    except Exception as e:
        logger.warning(f"Could not save Strava token to DB (table may not exist): {e}")


async def _get_refresh_token() -> str:
    """Get the latest refresh token: DB first (survives rotation), env var as fallback."""
    stored = await _get_stored_token()
    if stored and stored.get("refresh_token"):
        logger.info("Using Strava refresh token from DB")
        return stored["refresh_token"]
    logger.info("Using Strava refresh token from env var")
    return config.strava_refresh_token


async def refresh_access_token() -> str:
    """Refresh the Strava access token. Saves the new (rotated) refresh token to DB."""
    refresh_token = await _get_refresh_token()

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(STRAVA_TOKEN_URL, data={
            "client_id": config.strava_client_id,
            "client_secret": config.strava_client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        })
        response.raise_for_status()

    data = response.json()
    global _access_token
    _access_token = data["access_token"]

    # Strava rotates refresh tokens — save the new one
    new_refresh = data.get("refresh_token", refresh_token)
    expires_at = data.get("expires_at", 0)

    profile = await db_queries.get_user_profile()
    user_id = profile["id"] if profile else None
    if user_id:
        await _save_token(_access_token, new_refresh, expires_at, user_id)

    return _access_token


async def _get_token() -> str:
    """Get a valid access token, refreshing if needed."""
    global _access_token

    # Check if stored token is still valid
    stored = await _get_stored_token()
    if stored and stored.get("access_token") and stored.get("expires_at"):
        expires = datetime.fromisoformat(stored["expires_at"].replace("Z", "+00:00"))
        if expires > datetime.now(expires.tzinfo or pytz.UTC):
            _access_token = stored["access_token"]
            return _access_token

    # Need to refresh
    _access_token = await refresh_access_token()
    return _access_token


async def fetch_recent_activities(after_timestamp: int) -> list[dict]:
    token = await _get_token()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{STRAVA_API_BASE}/athlete/activities",
            headers={"Authorization": f"Bearer {token}"},
            params={"after": after_timestamp, "per_page": 30},
        )
        if resp.status_code == 401:
            token = await refresh_access_token()
            resp = await client.get(
                f"{STRAVA_API_BASE}/athlete/activities",
                headers={"Authorization": f"Bearer {token}"},
                params={"after": after_timestamp, "per_page": 30},
            )
        resp.raise_for_status()

    return [a for a in resp.json() if a.get("type") == "Run"]


def parse_strava_activity(activity: dict, user_weight_kg: float) -> dict:
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
        "calories_burned": int(calories),
        "elevation_gain_m": activity.get("total_elevation_gain"),
        "source": "strava",
        "external_id": str(activity["id"]),
        "external_url": f"https://www.strava.com/activities/{activity['id']}",
        "run_date": activity.get("start_date"),
    }


async def _run_exists(external_id: str) -> bool:
    client = db.get_client()
    result = (
        client.table("caltrack_runs")
        .select("id")
        .eq("source", "strava")
        .eq("external_id", external_id)
        .limit(1)
        .execute()
    )
    return bool(result.data)


async def sync_strava_runs() -> list[dict]:
    """
    Fetch Strava runs from the last 48 hours, save new ones, refresh daily_summary.
    Returns list of newly imported run dicts (parsed format).
    """
    if not is_configured():
        logger.info("Strava not configured — skipping sync")
        return []

    profile = await db_queries.get_user_profile()
    if not profile:
        return []

    tz = pytz.timezone(config.user_timezone)
    since = datetime.now(tz) - timedelta(hours=48)
    after_ts = int(since.timestamp())

    activities = await fetch_recent_activities(after_ts)
    imported = []

    for activity in activities:
        external_id = str(activity["id"])
        if await _run_exists(external_id):
            logger.debug(f"Strava activity {external_id} already imported — skipping")
            continue

        run_data = parse_strava_activity(activity, profile["current_weight_kg"])
        run_data["user_id"] = profile["id"]

        await db.insert("caltrack_runs", run_data)

        # Refresh daily_summary for the run's date
        run_date_str = run_data["run_date"][:10]  # "YYYY-MM-DD"
        await db_queries.refresh_daily_summary(run_date_str, profile["id"])

        imported.append(run_data)
        logger.info(f"Imported Strava run {external_id}: {run_data['distance_km']} km")

    return imported


def format_run_message(run: dict) -> str:
    pace = format_pace(run["avg_pace_sec_per_km"]) if run.get("avg_pace_sec_per_km") else "?"
    hr = f" | ❤️ {run['avg_heart_rate']}" if run.get("avg_heart_rate") else ""
    url = run.get("external_url", "")
    return (
        f"🏃 *Strava run imported*\n"
        f"{run['distance_km']} km | {run['duration_minutes']} min | {pace}/km{hr}\n"
        f"Burned: ~{run['calories_burned']} kcal\n"
        f"[View on Strava]({url})"
    )
