# bot/whatsapp/ — CalTrack's only transport (since 2026-10-20)

Ido logs meals in the WhatsApp group **"CalTrack"** (`120363431701833971@g.us`; Ido and the assistant number only).
CalTrack has **no Telegram** since 2026-10-20 (CalTrack #18–#21). Full QA record: `docs/QA-2026-10-20.md`.

## Message flow
```
WhatsApp group "CalTrack"
  → TARS wa-gateway (Go, ~/tars/wa-gateway; caltrack.go routes WA_CALTRACK_JID;
    disk retry queue ~/.tars/wa/caltrack-queue.jsonl, retried every 30 s)
  → POST 127.0.0.1:8093/wa/inbound  (bearer WA_TOKEN)        server.py build_app
  → Dispatcher.accept (dedupe by event id) → queue → worker → Dispatcher.handle
       image  → handlers/photo.handle_photo  (→ barcode / label if one is awaited)
       text   → a command (Hebrew word or /cmd) → handlers/*   |  an answer to a step  |  plain text = food ("הוסף …")
       poll_vote → Session.callback_for(poll_id, label) → handlers/callbacks.handle_callback
  ← replies: shim.Outbox → gateway.send_text / send_poll → wa-gateway /send, /poll {"to": "caltrack"}
```
Answers are sent through the gateway (`to: "caltrack"`). The gateway can only address Ido and this group.

## Files
| File | What it does |
|---|---|
| `server.py` | aiohttp endpoint (`/wa/inbound`, `/wa/health`) and `Dispatcher`: dedupe, a one-at-a-time worker (photo analysis takes longer than the gateway's 15 s timeout), command parsing (`parse_command`, `commands()` incl. Hebrew aliases), meal steps (`multi_item_step`, `callback`, `save`), and the **photo-wait rule** (below). |
| `shim.py` | Telegram-shaped objects the old handlers still expect: `WAUpdate`, `WAMessage` (`reply_text`, `photo[-1].get_file()`), `WACallbackQuery`, `WAContext` (`args`, `user_data`), `WAChat.id = OWNER_CHAT_ID`. `Outbox.send` turns a keyboard (`bot/ui.py` buttons) into a poll; the meal keyboard becomes the Hebrew card + `cards.meal_options`. `Session` keeps `user_data` and poll id → {label: callback_data} **in memory** (a restart forgets an open meal card). |
| `cards.py` | The Hebrew meal card (`render_meal`), its poll ("לשמור את הארוחה?": ✅ שמור / ✏️ שנה כמות / 🔄 זה לא… / ➕ הוסף פריט / ❌ בטל), step prompts, the "נשמר" card. |
| `he.py` | English handler text → Hebrew: `EXACT` strings, regex `RULES`, `COMMAND_ALIASES` (`סיכום`, `מצב`, `משקל`, `מים`, `ריצה`, `היסטוריה`, `ביטול`, `עזרה`, `הוסף`, `תבנית(ות)`, `שבוע`, `תווית`, `ברקוד`, `כיול`, `נתונים`), `HELP`. **New English replies need a rule here**, or they reach Ido in English. |
| `gateway.py` | HTTP client to wa-gateway: `send_text` (→ `to_whatsapp` → `split` into ≤ 3,500-char messages), `send_poll`, `fetch_media`, `notify` (scheduled messages; never raises). `to_whatsapp` converts links and full Markdown (`##` → `*…*`, `**` → `*`, `---` dropped). |

Outside this folder: `bot/runner.py` (scheduler + listener start-up), `bot/ui.py` (button/type shapes), `bot/main.py` (weekly jobs, entry point).

## States that change how text is read (`Session.user_data`)
- `pending_meal`: an open meal card. Plain text gets "📝 יש ארוחה פתוחה…"; `N grams` (e.g. `1 150`) sets an item's weight.
- `awaiting_manual_weight` / `awaiting_rename_item` / `awaiting_add_item` / `wa_await`: the next text is the answer. Bare command words are NOT commands then (`/cmd` still is).
- `waiting_for="barcode"` / `awaiting_label_photo`: waiting for a **photo**. Since 20/10 a command ends the wait and runs; any other text gets "📷 מחכה לתמונה של…". Before that fix, every plain command was silently swallowed.

## Rules
- Item display names are what Ido typed (Hebrew). English is only for the nutrition lookup (`ingredient_name` vs `ingredient_name_he`).
- Nothing is saved before ✅ (photo, typed meal, barcode). ❌ never writes.
- Access: the gateway only forwards this group, from Ido. The endpoint requires `WA_TOKEN`. The handlers' `allowed_chat_ids` check always passes for `OWNER_CHAT_ID`.

## Testing (on the VPS, in the image; nothing sent, nothing written)
- `tests/test_whatsapp.py`: unit tests, incl. `test_no_telegram_left`, `test_photo_wait_does_not_swallow_commands`, `test_markdown_report_becomes_whatsapp`.
- `scripts/wa_smoke.py`: 7 steps vs a saved baseline (shapes).
- `scripts/wa_deep_qa.py`: ~53 steps, every DB write intercepted; `--json` for an A/B diff.
- `scripts/db_fingerprint.py` before/after: proves the real DB is unchanged.
- Commands are in `docs/QA-2026-10-20.md` § 6. **Never test `שבוע` or a ✅ save without the write guard.**
