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
from bot.whatsapp import cards, gateway
from bot.whatsapp.shim import Outbox, Session, WACallbackQuery, WAContext, WAMessage, WAUpdate

logger = logging.getLogger(__name__)

# Text states where the next message is an answer, not a command.
AWAITING = ("awaiting_rename_item", "awaiting_manual_weight", "awaiting_add_item", "waiting_for", "wa_await")
FIX_ITEM = re.compile(r"^\s*(\d{1,2})\s+(\S.*)$")
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

    from bot.whatsapp.he import COMMAND_ALIASES

    cmds = {
        "weight": c.handle_weight, "water": c.handle_water, "run": c.handle_run,
        "summary": c.handle_summary, "s": c.handle_summary,
        "week": c.handle_week, "w": c.handle_week,
        "status": c.handle_status, "undo": c.handle_undo, "history": c.handle_history,
        "label": handle_label, "add": c.handle_add, "calibrate": handle_calibrate,
        "stats": handle_stats, "help": c.handle_help, "start": c.handle_help,
        "barcode": handle_barcode_command, "template": handle_template, "t": handle_template,
    }
    cmds.update({he: cmds[en] for he, en in COMMAND_ALIASES.items()})
    return cmds


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
            logger.info(f"WhatsApp vote: {ev.get('selected')}")
        else:
            logger.info(f"WhatsApp message: {ev.get('kind')}")
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
        pending = ud.get("pending_meal")
        step = ud.pop("wa_await", None)
        if step and pending:
            await self.multi_item_step(step, text, pending)
            return
        m = SET_WEIGHT.match(text)
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
        logger.info(f"WhatsApp vote → {data}")
        if data is None:
            await gateway.send_text("⌛ That menu has expired. Please start again.")
            return
        await self.callback(data)

    async def multi_item_step(self, step: str, text: str, pending: dict) -> None:
        """Typed answer to ✏️/🔄 on a meal with several items ("2 150", "2 חזה עוף")."""
        n = len(pending.get("items") or [])
        if step == "grams":
            m = SET_WEIGHT.match(text)
            if m and 0 < int(m.group(1)) <= n and int(m.group(2)) > 0:
                await self.callback(f"w:{int(m.group(1)) - 1}:{int(m.group(2))}")
                return
        elif step == "fix":
            m = FIX_ITEM.match(text)
            if m and 0 < int(m.group(1)) <= n:
                from bot.handlers.callbacks import handle_text_input
                self.session.user_data["awaiting_rename_item"] = int(m.group(1)) - 1
                msg = WAMessage(self.outbox, text=m.group(2))
                await handle_text_input(WAUpdate(message=msg), self.ctx())
                return
        self.session.user_data["wa_await"] = step
        await gateway.send_text("לא הבנתי. " + cards.prompt_for(f"wa:{step}", pending))

    async def callback(self, data: str) -> None:
        from bot.handlers.callbacks import handle_callback
        ud = self.session.user_data
        pending = ud.get("pending_meal")
        if data == "wa:cancel":
            for k in ("pending_meal", *AWAITING):
                ud.pop(k, None)
            await gateway.send_text("❌ בוטל — הארוחה לא נשמרה.")
            return
        prompt = cards.prompt_for(data, pending) if pending else None
        if prompt:
            for k in AWAITING:
                ud.pop(k, None)
            if data.startswith("w:"):
                ud["awaiting_manual_weight"] = int(data.split(":")[1])
            elif data.startswith("rename:"):
                ud["awaiting_rename_item"] = int(data.split(":")[1])
            elif data == "add":
                ud["awaiting_add_item"] = True
            else:
                ud["wa_await"] = data.split(":", 1)[1]
            await gateway.send_text(prompt)
            return
        q = WACallbackQuery(self.outbox, data)
        if data == "ok" and pending:
            await self.save(q, pending)
            return
        await handle_callback(WAUpdate(callback_query=q), self.ctx())

    async def save(self, q, pending: dict) -> None:
        """✅: the handler saves; the reply is the Hebrew card, not its English one."""
        from datetime import datetime

        import pytz

        from bot.db import queries as db_queries
        from bot.handlers.callbacks import handle_callback
        from bot.services.nutrition import calculate_meal_totals

        kcal = int(round(calculate_meal_totals(pending["items"])["total_calories"] or 0))
        self.outbox.capture = []
        try:
            await handle_callback(WAUpdate(callback_query=q), self.ctx())
        finally:
            said, self.outbox.capture = self.outbox.capture, None
        if "pending_meal" in self.session.user_data:      # not saved (no profile, …): show why
            for t in said:
                await gateway.send_text(t)
            return
        profile = await db_queries.get_user_profile()
        today = datetime.now(pytz.timezone(config.user_timezone)).strftime("%Y-%m-%d")
        daily = await db_queries.refresh_daily_summary(today, profile["id"]) if profile else {}
        await gateway.send_text(cards.render_saved(kcal, daily or {}))


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
