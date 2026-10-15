"""HTTP client for TARS's wa-gateway. Every send goes to the CalTrack group
(`"to": "caltrack"`); the gateway refuses any other recipient."""

import logging
import re

import httpx

from bot.utils.config import config

logger = logging.getLogger(__name__)

MAX_CHUNK = 3500
POLL_OPTION_MAX = 100


def _headers() -> dict:
    return {"Authorization": f"Bearer {config.wa_token}"}


def to_whatsapp(text: str) -> str:
    """Telegram Markdown (v1) → WhatsApp. *bold*, _italic_ and `code` are the
    same in both; only links differ."""
    return re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"\1 (\2)", text or "")


def split(text: str, max_len: int = MAX_CHUNK) -> list[str]:
    if len(text) <= max_len:
        return [text]
    chunks, cur = [], ""
    for line in text.split("\n"):
        while len(line) > max_len:
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(line[:max_len])
            line = line[max_len:]
        if cur and len(cur) + len(line) + 1 > max_len:
            chunks.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        chunks.append(cur)
    return chunks


async def send_text(text: str) -> None:
    text = to_whatsapp(text).strip()
    if not text:
        return
    async with httpx.AsyncClient(timeout=20) as c:
        for chunk in split(text):
            r = await c.post(f"{config.wa_gateway_url}/send", headers=_headers(),
                             json={"text": chunk, "to": "caltrack"})
            r.raise_for_status()


async def send_poll(question: str, options: list[str]) -> str:
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{config.wa_gateway_url}/poll", headers=_headers(),
                         json={"question": question[:250], "options": options, "to": "caltrack"})
        r.raise_for_status()
        return r.json().get("id", "")


async def fetch_media(media_id: str) -> bytes:
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.get(f"{config.wa_gateway_url}/media/{media_id}", headers=_headers())
        r.raise_for_status()
        return r.content


async def notify(text: str) -> None:
    """Scheduled messages (nudges, reports) → WhatsApp too. Never raises, so
    the Telegram copy is never blocked by a WhatsApp problem."""
    if not config.wa_enabled:
        return
    from bot.whatsapp.he import he_text
    try:
        await send_text(he_text(text))
    except Exception as e:
        logger.warning(f"WhatsApp notify failed: {type(e).__name__}: {e}")
