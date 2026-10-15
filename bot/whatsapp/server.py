"""Inbound endpoint for the CalTrack WhatsApp group (POST /wa/inbound).

The gateway (TARS's wa-gateway) posts each message or poll vote with the
shared bearer token. We answer 200 at once and handle events one at a time
in a worker: photo analysis takes longer than the gateway's 15 s timeout,
and a timeout would make it retry (a duplicate meal).
"""

import asyncio
import hmac
import logging
import re

from aiohttp import web

from bot.utils.config import config
from bot.whatsapp import gateway
from bot.whatsapp.shim import Outbox, Session, WACallbackQuery, WAContext, WAMessage, WAUpdate

logger = logging.getLogger(__name__)

# Text states where the next message is an answer, not a command.
AWAITING = ("awaiting_rename_item", "awaiting_manual_weight", "awaiting_add_item", "waiting_for")
# "1 150" / "2 80g" → set item 1 to 150 g (replaces the gram buttons).
SET_WEIGHT = re.compile(r"^\s*(\d{1,2})\s+(\d{1,4})\s*(?:g|gr|ג|גר|גרם)?\s*$", re.IGNORECASE)
SEEN_MAX = 500
_tasks: set = set()   # keep a reference so the worker is not garbage-collected


def commands() -> dict:
    from bot.handlers import commands as c
    from bot.handlers.admin import handle_calibrate, handle_stats
    from bot.handlers.barcode import handle_barcode_command
    from bot.handlers.label import handle_label
    from bot.handlers.template import handle_template

    return {
        "weight": c.handle_weight, "water": c.handle_water, "run": c.handle_run,
        "summary": c.handle_summary, "s": c.handle_summary,
        "week": c.handle_week, "w": c.handle_week,
        "status": c.handle_status, "undo": c.handle_undo, "history": c.handle_history,
        "label": handle_label, "add": c.handle_add, "calibrate": handle_calibrate,
        "stats": handle_stats, "help": c.handle_help, "start": c.handle_help,
        "barcode": handle_barcode_command, "template": handle_template, "t": handle_template,
    }


def parse_command(text: str, user_data: dict, names) -> tuple[str, list[str]] | None:
    """"/weight 80" always; "weight 80" only when no answer is awaited."""
    parts = text.strip().split()
    if not parts:
        return None
    head = parts[0]
    if head.startswith("/"):
        name = head[1:].split("@", 1)[0].lower()
        return (name, parts[1:]) if name in names else None
    if any(k in user_data for k in AWAITING):
        return None
    name = head.lower()
    return (name, parts[1:]) if name in names else None


class Dispatcher:
    def __init__(self) -> None:
        self.session = Session()
        self.outbox = Outbox(self.session)
        self.queue: asyncio.Queue = asyncio.Queue()
        self.seen: dict[str, None] = {}

    def accept(self, ev: dict) -> bool:
        key = ev.get("id") or f"{ev.get('poll_id')}:{ev.get('ts')}:{ev.get('selected')}"
        if key in self.seen:
            return False
        self.seen[key] = None
        while len(self.seen) > SEEN_MAX:
            self.seen.pop(next(iter(self.seen)))
        self.queue.put_nowait(ev)
        return True

    async def worker(self) -> None:
        while True:
            ev = await self.queue.get()
            try:
                await self.handle(ev)
            except Exception as e:
                logger.error(f"WhatsApp event failed: {type(e).__name__}: {e}", exc_info=True)
                try:
                    await gateway.send_text("⚠️ Something went wrong. Please try again.")
                except Exception:
                    pass
            finally:
                self.queue.task_done()

    def ctx(self, args: list[str] | None = None) -> WAContext:
        return WAContext(self.session, self.outbox, args)

    async def handle(self, ev: dict) -> None:
        if ev.get("type") == "poll_vote":
            await self.vote(ev)
            return
        kind = ev.get("kind")
        if kind == "image" and ev.get("has_media"):
            from bot.handlers.photo import handle_photo
            msg = WAMessage(self.outbox, photo_id=ev["id"], caption=ev.get("text") or None)
            await handle_photo(WAUpdate(message=msg), self.ctx())
        elif kind == "text":
            await self.text(ev.get("text") or "")
        elif kind in ("voice", "audio", "video", "document", "sticker"):
            await gateway.send_text("I can read text and photos here. Send a meal photo or a command (help).")

    async def text(self, text: str) -> None:
        if not text.strip():
            return
        ud = self.session.user_data
        cmds = commands()
        parsed = parse_command(text, ud, cmds)
        if parsed:
            name, args = parsed
            msg = WAMessage(self.outbox, text=text)
            await cmds[name](WAUpdate(message=msg), self.ctx(args))
            return
        m = SET_WEIGHT.match(text)
        pending = ud.get("pending_meal")
        if m and pending and not any(k in ud for k in AWAITING):
            idx, grams = int(m.group(1)) - 1, int(m.group(2))
            if 0 <= idx < len(pending.get("items", [])) and grams > 0:
                await self.callback(f"w:{idx}:{grams}")
                return
        from bot.handlers.callbacks import handle_text_input
        msg = WAMessage(self.outbox, text=text)
        await handle_text_input(WAUpdate(message=msg), self.ctx())

    async def vote(self, ev: dict) -> None:
        selected = ev.get("selected") or []
        if not selected:                 # a vote was withdrawn
            return
        data = self.session.callback_for(ev.get("poll_id", ""), selected[0])
        if data is None:
            await gateway.send_text("⌛ That menu has expired. Please start again.")
            return
        await self.callback(data)

    async def callback(self, data: str) -> None:
        from bot.handlers.callbacks import handle_callback
        q = WACallbackQuery(self.outbox, data)
        await handle_callback(WAUpdate(callback_query=q), self.ctx())


def build_app(dispatcher: Dispatcher) -> web.Application:
    async def inbound(request: web.Request) -> web.Response:
        auth = request.headers.get("Authorization", "")
        if not hmac.compare_digest(auth.encode(), f"Bearer {config.wa_token}".encode()):
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            ev = await request.json()
        except Exception:
            return web.json_response({"error": "bad json"}, status=400)
        if not isinstance(ev, dict) or ev.get("type") not in ("message", "poll_vote"):
            return web.json_response({"error": "unknown event"}, status=400)
        if ev.get("from_me"):
            return web.json_response({"ok": True, "ignored": "from_me"})
        dup = not dispatcher.accept(ev)
        return web.json_response({"ok": True, "duplicate": dup})

    async def health(request: web.Request) -> web.Response:
        return web.json_response({"ok": True, "queued": dispatcher.queue.qsize()})

    app = web.Application(client_max_size=1024 * 1024)
    app.router.add_post("/wa/inbound", inbound)
    app.router.add_get("/wa/health", health)
    return app


async def start() -> web.AppRunner | None:
    """Started from bot/main.py post_init when WA_TOKEN is set."""
    if not config.wa_enabled:
        logger.info("WhatsApp: off (no WA_TOKEN).")
        return None
    dispatcher = Dispatcher()
    task = asyncio.get_running_loop().create_task(dispatcher.worker())
    _tasks.add(task)
    runner = web.AppRunner(build_app(dispatcher), access_log=None)
    await runner.setup()
    await web.TCPSite(runner, config.wa_listen_host, config.wa_listen_port).start()
    logger.info(f"WhatsApp: listening on {config.wa_listen_host}:{config.wa_listen_port}/wa/inbound")
    return runner
