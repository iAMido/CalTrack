"""The small slice of python-telegram-bot the handlers used, without the library
(2026-10-20, "CalTrack without Telegram", step 2).

The handlers still build "keyboards": a list of rows of buttons with a label
and a callback_data. The WhatsApp adapter (bot/whatsapp/shim.py) turns them
into polls; it only reads `markup.inline_keyboard`, `button.text` and
`button.callback_data`. `Update` and `ContextTypes` were type hints only — the
handlers receive the adapter's WAUpdate / WAContext objects.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class InlineKeyboardButton:
    text: str
    callback_data: str | None = None


class InlineKeyboardMarkup:
    def __init__(self, inline_keyboard) -> None:
        self.inline_keyboard = tuple(tuple(row) for row in inline_keyboard)

    def __repr__(self) -> str:
        return f"InlineKeyboardMarkup({self.inline_keyboard!r})"


Update = Any


class ContextTypes:
    DEFAULT_TYPE = Any
