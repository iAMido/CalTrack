"""Telegram-shaped objects for the existing handlers, backed by WhatsApp.

Only the surface CalTrack's handlers use is implemented: reply_text /
edit_text / edit_message_text (WhatsApp can't edit, so each becomes a new
message), query.answer, effective_chat.id, context.args / user_data / bot,
and msg.photo[-1].get_file().download_as_bytearray().

An inline keyboard becomes a WhatsApp poll (max 12 options). The poll's
option labels map back to the buttons' callback_data, so a vote replays as
a CallbackQuery into handle_callback.
"""

import re
from itertools import count

from datetime import datetime

import pytz

from bot.utils.config import config
from bot.whatsapp import cards, gateway

MAX_OPTIONS = 12
MAX_POLLS = 50
WEIGHT_BUTTON = re.compile(r"^w:\d+:\d+$")
POLL_QUESTION = "👆 Choose:"
POLL_QUESTION_WEIGHTS = "👆 Choose — or type e.g. 1 150 to set item 1 to 150 g"
# A meal waiting for ✅ (Ido 2026-10-15: after "1 350" the new poll looked like
# a repeat, and the meal was never saved).
POLL_QUESTION_MEAL = "📝 Not saved yet — vote ✅ Confirm All to save. To change grams type e.g. 1 150"

_ids = count(1)


def keyboard_options(markup) -> dict[str, str]:
    """InlineKeyboardMarkup → {poll option label: callback_data}.

    A row that starts with a "noop" label (the meal keyboard's "1.") prefixes
    the row's other buttons, so "✏️" becomes "1. ✏️". If there are more than 12
    options, the gram-suggestion buttons go first (typing "1 150" replaces
    them); after that the first 8 and the last 4 (the action row) are kept.
    """
    if markup is None:
        return {}
    pairs: list[tuple[str, str]] = []
    for row in markup.inline_keyboard:
        btns = list(row)
        prefix = ""
        if btns and btns[0].callback_data == "noop":
            prefix = btns[0].text.strip().rstrip(".") + ". "
            btns = btns[1:]
        for b in btns:
            data = b.callback_data
            if not data or data == "noop":
                continue
            pairs.append(((prefix + b.text).strip()[: gateway.POLL_OPTION_MAX], data))
    if len(pairs) > MAX_OPTIONS:
        pairs = [p for p in pairs if not WEIGHT_BUTTON.match(p[1])]
    if len(pairs) > MAX_OPTIONS:
        pairs = pairs[:8] + pairs[-4:]
    out: dict[str, str] = {}
    for label, data in pairs:
        while label in out:          # poll options must be unique
            label += "\u200b"
        out[label] = data
    return out


class Session:
    """State for the one WhatsApp user (Ido): PTB's context.user_data and the
    poll → buttons map. In memory; a restart forgets a half-confirmed meal,
    as Telegram's in-memory user_data does."""

    def __init__(self) -> None:
        self.user_data: dict = {}
        self.polls: dict[str, dict[str, str]] = {}

    def remember_poll(self, poll_id: str, options: dict[str, str]) -> None:
        self.polls[poll_id] = options
        while len(self.polls) > MAX_POLLS:
            self.polls.pop(next(iter(self.polls)))

    def callback_for(self, poll_id: str, label: str) -> str | None:
        return (self.polls.get(poll_id) or {}).get(label)


class Outbox:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.capture: list[str] | None = None    # collect instead of sending (server.py)

    async def send(self, text: str, reply_markup=None) -> "WAMessage":
        if self.capture is not None:
            self.capture.append(text)
            return WAMessage(self)
        options = keyboard_options(reply_markup)
        pending = self.session.user_data.get("pending_meal")
        if pending and {"ok", "add"} <= set(options.values()):
            # The meal keyboard → the WhatsApp card (cards.py), not Telegram's.
            now = datetime.now(pytz.timezone(config.user_timezone)).strftime("%H:%M")
            await gateway.send_text(cards.render_meal(pending, now))
            meal_opts = cards.meal_options(pending)
            poll_id = await gateway.send_poll(cards.POLL_QUESTION, list(meal_opts))
            if poll_id:
                self.session.remember_poll(poll_id, meal_opts)
            return WAMessage(self)
        await gateway.send_text(cards.TRANSLATE.get(text, text))
        if len(options) >= 2:
            has_weights = any(WEIGHT_BUTTON.match(d) or d.endswith(":m") for d in options.values())
            if "ok" in options.values():
                question = POLL_QUESTION_MEAL
            else:
                question = POLL_QUESTION_WEIGHTS if has_weights else POLL_QUESTION
            poll_id = await gateway.send_poll(question, list(options))
            if poll_id:
                self.session.remember_poll(poll_id, options)
        elif len(options) == 1:      # a single button: say what to type instead
            label = next(iter(options))
            await gateway.send_text(f"({label})")
        return WAMessage(self)


class WAChat:
    type = "private"

    def __init__(self) -> None:
        self.id = config.telegram_allowed_chat_id


class WAFile:
    def __init__(self, media_id: str) -> None:
        self.file_id = media_id

    async def download_as_bytearray(self) -> bytearray:
        return bytearray(await gateway.fetch_media(self.file_id))


class WAPhotoSize:
    def __init__(self, media_id: str) -> None:
        self.file_id = media_id
        self.file_unique_id = media_id

    async def get_file(self) -> WAFile:
        return WAFile(self.file_id)


class WAMessage:
    def __init__(self, outbox: Outbox, text: str | None = None, photo_id: str | None = None,
                 caption: str | None = None) -> None:
        self._outbox = outbox
        self.message_id = next(_ids)
        self.text = text
        self.caption = caption
        self.photo = [WAPhotoSize(photo_id)] if photo_id else []
        self.chat = WAChat()

    async def reply_text(self, text: str, parse_mode=None, reply_markup=None, **kw) -> "WAMessage":
        return await self._outbox.send(text, reply_markup)

    async def edit_text(self, text: str, parse_mode=None, reply_markup=None, **kw) -> "WAMessage":
        return await self._outbox.send(text, reply_markup)


class WACallbackQuery:
    def __init__(self, outbox: Outbox, data: str) -> None:
        self.data = data
        self.message = WAMessage(outbox)
        self._outbox = outbox

    async def answer(self, *a, **kw) -> None:
        return None

    async def edit_message_text(self, text: str, parse_mode=None, reply_markup=None, **kw):
        return await self._outbox.send(text, reply_markup)


class WABot:
    def __init__(self, outbox: Outbox) -> None:
        self._outbox = outbox

    async def send_message(self, chat_id=None, text: str = "", parse_mode=None, reply_markup=None, **kw):
        return await self._outbox.send(text, reply_markup)


class WAUpdate:
    def __init__(self, message: WAMessage | None = None, callback_query: WACallbackQuery | None = None) -> None:
        self.message = message
        self.callback_query = callback_query
        self.effective_chat = WAChat()
        self.effective_message = message or (callback_query.message if callback_query else None)


class WAContext:
    def __init__(self, session: Session, outbox: Outbox, args: list[str] | None = None) -> None:
        self.user_data = session.user_data
        self.args = args or []
        self.bot = WABot(outbox)
