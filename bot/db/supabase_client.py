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
    query = client.table(table).upsert(data)
    if on_conflict:
        query = query.on_conflict(on_conflict)
    result = query.execute()
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
    """Upload photo to Supabase Storage. Returns storage path."""
    client = get_client()
    client.storage.from_("meals").upload(
        path,
        file_bytes,
        {"content-type": "image/jpeg"},
    )
    return path


async def get_photo_url(path: str) -> str:
    """Get a signed URL for a stored photo (valid 1 hour)."""
    client = get_client()
    result = client.storage.from_("meals").create_signed_url(path, 3600)
    return result.get("signedURL", "")
