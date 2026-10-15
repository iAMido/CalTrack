"""WhatsApp adapter tests (bot/whatsapp). No network: the gateway and the
handlers are replaced with recorders.

    docker compose run --rm --no-deps caltrack python tests/test_whatsapp.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for k, v in {"TELEGRAM_BOT_TOKEN": "1:x", "TELEGRAM_ALLOWED_CHAT_ID": "555",
             "SUPABASE_URL": "http://localhost", "SUPABASE_KEY": "x",
             "WA_TOKEN": "t" * 40}.items():
    os.environ.setdefault(k, v)

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as M  # noqa: E402

from bot.whatsapp import cards, gateway, server, shim  # noqa: E402


class Rec:
    def __init__(self):
        self.texts, self.polls, self.calls = [], [], []

    def install(self):
        async def send_text(text):
            self.texts.append(text)

        async def send_poll(q, opts):
            self.polls.append((q, opts))
            return f"P{len(self.polls)}"

        async def fetch_media(mid):
            return b"JPEG" + mid.encode()

        gateway.send_text, gateway.send_poll, gateway.fetch_media = send_text, send_poll, fetch_media
        shim.gateway.send_text = send_text
        server.gateway.send_text = send_text
        shim.gateway.send_poll = send_poll


def meal_markup(n_items, sugg=(100, 150, 200)):
    rows = []
    for i in range(n_items):
        row = [B(f"{i + 1}.", callback_data="noop")]
        row += [B(f"{w}g", callback_data=f"w:{i}:{w}") for w in sugg]
        row += [B("✏️", callback_data=f"w:{i}:m"), B("🔄", callback_data=f"rename:{i}")]
        rows.append(row)
    rows.append([B("✅ Confirm All", callback_data="ok"), B("❌ Cancel", callback_data="no")])
    rows.append([B("🔄 Re-analyze", callback_data="re"), B("➕ Missing item?", callback_data="add")])
    return M(rows)


def test_keyboard_small_keeps_everything_and_prefixes_rows():
    opts = shim.keyboard_options(meal_markup(1))
    assert opts["1. 150g"] == "w:0:150" and opts["1. ✏️"] == "w:0:m" and opts["1. 🔄"] == "rename:0"
    assert opts["✅ Confirm All"] == "ok" and len(opts) == 9
    assert "1." not in opts                                    # the noop label is not an option


def test_keyboard_big_drops_gram_buttons_then_trims():
    opts = shim.keyboard_options(meal_markup(3))               # 3*5 + 4 = 19 → drop grams → 10
    assert len(opts) == 10 and not any(d.startswith("w:") and d[-1].isdigit() for d in opts.values())
    opts = shim.keyboard_options(meal_markup(6))               # 6*2 + 4 = 16 → 8 + last 4
    assert len(opts) == 12 and list(opts.values())[-4:] == ["ok", "no", "re", "add"]


def test_duplicate_labels_stay_unique():
    opts = shim.keyboard_options(M([[B("x", callback_data="a"), B("x", callback_data="b")]]))
    assert sorted(opts.values()) == ["a", "b"] and len(opts) == 2


def test_markdown_links_and_split():
    assert gateway.to_whatsapp("see [docs](https://a.b/c) *now*") == "see docs (https://a.b/c) *now*"
    parts = gateway.split("\n".join(["y" * 1000] * 8))
    assert all(len(p) <= gateway.MAX_CHUNK for p in parts) and len(parts) == 3


def test_parse_command():
    names = {"weight", "water", "w", "t"}
    assert server.parse_command("/weight 80.5", {}, names) == ("weight", ["80.5"])
    assert server.parse_command("Water 500", {}, names) == ("water", ["500"])
    assert server.parse_command("/weight@caltrack_bot 80", {}, names) == ("weight", ["80"])
    assert server.parse_command("white rice, 150", {}, names) is None
    assert server.parse_command("water 500", {"awaiting_add_item": True}, names) is None   # an answer
    assert server.parse_command("/water 500", {"awaiting_add_item": True}, names) == ("water", ["500"])


def run(coro):
    return asyncio.run(coro)


def test_flow_photo_poll_vote_and_shortcut():
    rec = Rec()
    rec.install()
    seen = {}

    async def fake_photo(update, context):
        data = await (await update.message.photo[-1].get_file()).download_as_bytearray()
        seen["photo"] = bytes(data)
        assert update.effective_chat.id == 555
        context.user_data["pending_meal"] = {"items": [{"weight_grams": 100}, {"weight_grams": 50}]}
        await update.message.reply_text("🍽 *Lunch*", reply_markup=meal_markup(2), parse_mode="Markdown")

    async def fake_callback(update, context):
        q = update.callback_query
        await q.answer()
        rec.calls.append(q.data)
        await q.edit_message_text(f"done {q.data}")

    async def fake_text(update, context):
        rec.calls.append(("text", update.message.text))

    import bot.handlers.callbacks as cb
    import bot.handlers.photo as ph
    ph.handle_photo, cb.handle_callback, cb.handle_text_input = fake_photo, fake_callback, fake_text

    d = server.Dispatcher()
    run(d.handle({"type": "message", "id": "IMG1", "kind": "image", "has_media": True, "text": ""}))
    assert seen["photo"] == b"JPEGIMG1"
    assert rec.polls[0][0] == cards.POLL_QUESTION
    assert list(rec.polls[0][1]) == [cards.SAVE, cards.GRAMS, cards.FIX_MANY, cards.ADD, cards.CANCEL]
    assert "🔥" in rec.texts[0] and "Lunch" not in rec.texts[0]          # the Hebrew card, not Telegram's

    run(d.handle({"type": "poll_vote", "poll_id": "P1", "selected": [cards.SAVE]}))
    run(d.handle({"type": "poll_vote", "poll_id": "P1", "selected": []}))           # withdrawn: nothing
    run(d.handle({"type": "message", "id": "T1", "kind": "text", "text": "2 80g"}))  # shortcut
    run(d.handle({"type": "message", "id": "T2", "kind": "text", "text": "9 80"}))   # no item 9 → text
    run(d.handle({"type": "poll_vote", "poll_id": "OLD", "selected": ["x"]}))
    assert rec.calls == ["ok", "w:1:80", ("text", "9 80")]
    assert rec.texts[-1].startswith("⌛")


def test_dedupe_and_auth():
    from aiohttp.test_utils import TestClient, TestServer

    async def go():
        d = server.Dispatcher()
        client = TestClient(TestServer(server.build_app(d)))
        await client.start_server()
        try:
            ev = {"type": "message", "id": "A", "kind": "text", "text": "hi"}
            r = await client.post("/wa/inbound", json=ev)
            assert r.status == 401
            h = {"Authorization": "Bearer " + "t" * 40}
            assert (await (await client.post("/wa/inbound", json=ev, headers=h)).json())["duplicate"] is False
            assert (await (await client.post("/wa/inbound", json=ev, headers=h)).json())["duplicate"] is True
            r = await client.post("/wa/inbound", json={"type": "nope"}, headers=h)
            assert r.status == 400
            assert d.queue.qsize() == 1
        finally:
            await client.close()

    run(go())


def test_card_steps_and_save():
    rec = Rec()
    rec.install()
    import bot.handlers.callbacks as cb
    import bot.db.queries as q

    async def fake_callback(update, context):
        data = update.callback_query.data
        rec.calls.append(data)
        if data == "ok":
            context.user_data.pop("pending_meal", None)
            await update.callback_query.edit_message_text("✅ *Saved!* english")

    async def fake_text(update, context):
        rec.calls.append(("text", update.message.text, context.user_data.get("awaiting_rename_item")))

    async def profile():
        return {"id": "u1"}

    async def refresh(day, uid):
        return {"total_calories_in": 1500, "target_calories": 2200, "meal_count": 3, "water_ml": 1500}

    cb.handle_callback, cb.handle_text_input = fake_callback, fake_text
    q.get_user_profile, q.refresh_daily_summary = profile, refresh

    one = {"meal_type": "dinner", "items": [{"ingredient_name_he": "פיצה גבינה", "weight_grams": 350,
                                              "ai_estimated_grams": 200, "calories": 931}]}
    card = cards.render_meal(one, "21:45")
    assert "*פיצה גבינה* — 350 גר׳ · 931 קל׳" in card and "הערכת AI: 200" in card and "ארוחת ערב" in card
    assert list(cards.meal_options(one).values()) == ["ok", "w:0:m", "rename:0", "add", "wa:cancel"]

    d = server.Dispatcher()
    d.session.user_data["pending_meal"] = {"meal_type": "lunch", "items": [{"calories": 100}, {"calories": 50}]}
    run(d.callback("wa:grams"))
    assert d.session.user_data["wa_await"] == "grams" and "2 150" in rec.texts[-1]
    run(d.text("weight"))                                     # not a command while a step waits
    assert rec.texts[-1].startswith("לא הבנתי") and d.session.user_data["wa_await"] == "grams"
    run(d.text("2 150"))
    run(d.callback("wa:fix"))
    run(d.text("1 חזה עוף"))
    assert rec.calls == ["w:1:150", ("text", "חזה עוף", 0)]
    run(d.callback("w:0:m"))                                  # ✏️ on a single item → Hebrew prompt, no handler
    assert d.session.user_data["awaiting_manual_weight"] == 0 and "כמה גרם" in rec.texts[-1]
    run(d.callback("ok"))
    assert "✅ *נשמר* · 150 קל׳" in rec.texts[-1] and "1,500 / 2,200" in rec.texts[-1] and "english" not in rec.texts[-1]
    d.session.user_data["pending_meal"] = {"items": [{}]}
    run(d.callback("wa:cancel"))
    assert "pending_meal" not in d.session.user_data and rec.texts[-1].startswith("❌")


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, type(e).__name__, e)
    print("ALL PASS" if not fails else f"{fails} FAILED")
    sys.exit(1 if fails else 0)
