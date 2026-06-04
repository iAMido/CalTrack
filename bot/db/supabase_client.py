from supabase import create_client, Client
from bot.utils.config import config

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(config.supabase_url, config.supabase_key)
    return _client


async def insert(table: str, data: dict) -> dict:
    client = get_client()
    result = client.table(table).insert(data).execute()
    return result.data[0] if result.data else {}


async def upsert(table: str, data: dict, on_conflict: str = "") -> dict:
    client = get_client()
    kwargs = {"on_conflict": on_conflict} if on_conflict else {}
    result = client.table(table).upsert(data, **kwargs).execute()
    return result.data[0] if result.data else {}


async def select(table: str, filters: dict = None, limit: int = None, order: str = None, descending: bool = False) -> list[dict]:
    client = get_client()
    query = client.table(table).select("*")
    if filters:
        for col, val in filters.items():
            query = query.eq(col, val)
    if order:
        query = query.order(order, desc=descending)
    if limit:
        query = query.limit(limit)
    result = query.execute()
    return result.data or []


async def select_one(table: str, filters: dict = None) -> dict | None:
    rows = await select(table, filters, limit=1)
    return rows[0] if rows else None


async def update(table: str, filters: dict, data: dict) -> list[dict]:
    client = get_client()
    query = client.table(table).update(data)
    for col, val in filters.items():
        query = query.eq(col, val)
    result = query.execute()
    return result.data or []


async def delete_row(table: str, filters: dict) -> list[dict]:
    client = get_client()
    query = client.table(table).delete()
    for col, val in filters.items():
        query = query.eq(col, val)
    result = query.execute()
    return result.data or []


async def upload_photo(file_bytes: bytes, path: str) -> str:
    """Upload photo to Supabase Storage `meals` bucket. Returns storage path.

    Raises whatever supabase-py raises on failure — callers should catch.
    The expected file_options key is `content-type` (lowercase) per
    storage3 v0.7+; mismatched casing silently uploads with default
    application/octet-stream which then 404s when the dashboard tries
    to serve it as an image.
    """
    client = get_client()
    # `file_options` is the THIRD positional arg of upload(); the supabase-py
    # signature is upload(path, file, file_options=None). Pass as a kwarg
    # so future signature changes don't shift our values silently.
    client.storage.from_("meals").upload(
        path=path,
        file=file_bytes,
        file_options={"content-type": "image/jpeg", "upsert": "true"},
    )
    return path


async def get_photo_url(path: str) -> str:
    """Get a signed URL for a stored photo (valid 1 hour)."""
    client = get_client()
    result = client.storage.from_("meals").create_signed_url(path, 3600)
    return result.get("signedURL", "") or result.get("signedUrl", "")


async def storage_health_check() -> tuple[bool, str]:
    """Verify the `meals` bucket exists and is reachable. Called at boot.

    Returns (ok, message). On failure, the bot still starts but logs a
    prominent warning so silent storage misconfiguration cannot persist.
    """
    try:
        client = get_client()
        buckets = client.storage.list_buckets()
        # supabase-py returns a list of dicts (or objects with .name)
        names = []
        for b in buckets or []:
            if isinstance(b, dict):
                names.append(b.get("name") or b.get("id"))
            else:
                names.append(getattr(b, "name", None) or getattr(b, "id", None))
        if "meals" in names:
            return True, "Storage bucket 'meals' OK"
        return False, (
            f"Storage bucket 'meals' NOT FOUND. Existing buckets: {names}. "
            "Photos will silently fail. Create with: "
            "INSERT INTO storage.buckets (id, name, public) "
            "VALUES ('meals', 'meals', false);"
        )
    except Exception as e:
        return False, f"Storage health check raised: {type(e).__name__}: {e}"
