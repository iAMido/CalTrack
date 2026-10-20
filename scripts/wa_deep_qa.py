"""Deep QA for CalTrack on WhatsApp — every command and flow, end to end,
with real reads and NO writes (2026-10-20, after "CalTrack without Telegram").

* A fake gateway captures every /send and /poll and serves a real meal photo
  (downloaded read-only from Storage) for the photo flow.
* Every database WRITE is intercepted and recorded instead of executed:
  supabase_client.insert/upsert/update/delete_row/upload_photo, and any
  .insert/.update/.upsert/.delete on get_client().table(...) or .storage.
  Reads (select) go to the real database.
* Scheduled jobs (nudges, weekly calibration, weekly coach) are called once.

Runs on the OLD code (before 2026-10-20, Telegram included) and the NEW code;
`--json out.json` saves the transcript so the two can be diffed.

  docker run --rm --network host --env-file <env> -v <checkout>:/app -w /app <image> \\
      python scripts/wa_deep_qa.py --json /app/out.json
"""

import asyncio
import json
import os
import re
import sys
import time
import uuid
from types import SimpleNamespace

FAKE_GW, LISTEN = 18089, 18093
os.environ["WA_GATEWAY_URL"] = f"http://127.0.0.1:{FAKE_GW}"
os.environ["WA_LISTEN_PORT"] = str(LISTEN)
os.environ["WA_LISTEN_HOST"] = "127.0.0.1"
for k, v in {"TELEGRAM_BOT_TOKEN": "1:x", "TELEGRAM_ALLOWED_CHAT_ID": "1"}.items():   # old code needs them
    os.environ.setdefault(k, v)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx  # noqa: E402
from aiohttp import web  # noqa: E402

out: list[tuple[str, str, list]] = []
writes: list[dict] = []
PHOTO = {"bytes": b""}


# ---------------------------------------------------------------- write interception
class _FakeQuery:
    def __init__(self, table, op, args, kw):
        self.rec = {"table": table, "op": op, "data": args[0] if args else kw}
        self.filters = []

    def __getattr__(self, name):          # .eq / .in_ / .match / ... all chain
        def chain(*a, **k):
            self.filters.append([name, [str(x)[:60] for x in a]])
            return self
        return chain

    def execute(self):
        self.rec["filters"] = self.filters
        writes.append(self.rec)
        data = self.rec["data"]
        rows = data if isinstance(data, list) else [data if isinstance(data, dict) else {}]
        return SimpleNamespace(data=[{"id": str(uuid.uuid4()), **r} for r in rows])


class _TableProxy:
    def __init__(self, real, name):
        self._real, self._name = real, name

    def __getattr__(self, attr):
        if attr in ("insert", "update", "upsert", "delete"):
            return lambda *a, **k: _FakeQuery(self._name, attr, a, k)
        return getattr(self._real, attr)


class _BucketProxy:
    def __init__(self, real, name):
        self._real, self._name = real, name

    def __getattr__(self, attr):
        if attr in ("upload", "update", "remove", "move"):
            def fake(*a, **k):
                writes.append({"table": f"storage:{self._name}", "op": attr, "data": str(a[0])[:80] if a else ""})
                return SimpleNamespace(path=str(a[0]) if a else "")
            return fake
        return getattr(self._real, attr)


class _StorageProxy:
    def __init__(self, real):
        self._real = real

    def from_(self, name):
        return _BucketProxy(self._real.from_(name), name)

    def __getattr__(self, attr):
        return getattr(self._real, attr)


class _ClientProxy:
    def __init__(self, real):
        self._real = real
        self.storage = _StorageProxy(real.storage)

    def table(self, name):
        return _TableProxy(self._real.table(name), name)

    def from_(self, name):
        return self.table(name)

    def __getattr__(self, attr):
        return getattr(self._real, attr)


def install_write_guard() -> None:
    from bot.db import supabase_client as db

    real_get = db.get_client
    proxy = {"c": None}

    def get_client():
        if proxy["c"] is None:
            proxy["c"] = _ClientProxy(real_get())
        return proxy["c"]

    async def insert(table, data):
        writes.append({"table": table, "op": "insert", "data": data})
        return {"id": str(uuid.uuid4()), **(data if isinstance(data, dict) else {})}

    async def upsert(table, data, on_conflict=""):
        writes.append({"table": table, "op": "upsert", "data": data})
        return {"id": data.get("id") or str(uuid.uuid4()), **data} if isinstance(data, dict) else {}

    async def update(table, filters, data):
        writes.append({"table": table, "op": "update", "data": data, "filters": filters})
        return [{**filters, **data}]

    async def delete_row(table, filters):
        writes.append({"table": table, "op": "delete", "filters": filters})
        return [filters]

    async def upload_photo(file_bytes, path):
        writes.append({"table": "storage:meals", "op": "upload", "data": path})
        return path

    db.get_client, db.insert, db.upsert, db.update, db.delete_row, db.upload_photo = (
        get_client, insert, upsert, update, delete_row, upload_photo)


# ---------------------------------------------------------------- fake gateway
async def fake_gateway() -> web.AppRunner:
    async def send(request):
        body = await request.json()
        out.append(("text", body.get("text", ""), []))
        return web.json_response({"id": f"S{len(out)}"})

    async def poll(request):
        body = await request.json()
        out.append(("poll", body.get("question", ""), body.get("options", [])))
        return web.json_response({"id": f"P{len(out)}"})

    async def media(request):
        if PHOTO["bytes"]:
            return web.Response(body=PHOTO["bytes"], content_type="image/jpeg")
        return web.json_response({"error": "not found"}, status=404)

    app = web.Application(client_max_size=20 * 1024 * 1024)
    app.router.add_post("/send", send)
    app.router.add_post("/poll", poll)
    app.router.add_get("/media/{id}", media)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", FAKE_GW).start()
    return runner


async def settle(n0: int, quiet: float = 5.0, limit: float = 150.0) -> list:
    t0, last_n, last_t = time.time(), len(out), time.time()
    while time.time() - t0 < limit:
        await asyncio.sleep(0.5)
        if len(out) != last_n:
            last_n, last_t = len(out), time.time()
        elif len(out) > n0 and time.time() - last_t >= quiet:
            break
    return out[n0:]


# ---------------------------------------------------------------- driver
class Driver:
    def __init__(self, client, hdr):
        self.c, self.hdr, self.i = client, hdr, 0
        self.transcript: list[dict] = []
        self.failures: list[str] = []

    async def post(self, body: dict) -> int:
        r = await self.c.post(f"http://127.0.0.1:{LISTEN}/wa/inbound", json=body, headers=self.hdr)
        return r.status_code

    def last_poll(self):
        for j in range(len(out) - 1, -1, -1):
            if out[j][0] == "poll":
                return f"P{j + 1}", out[j][2]
        return None, []

    async def step(self, name: str, *, text=None, kind="text", vote=None, check=None, quiet=5.0, raw=None, mid=None):
        self.i += 1
        n0, w0 = len(out), len(writes)
        if raw is not None:
            code = await self.post(raw)
        elif vote is not None:
            pid, opts = self.last_poll()
            label = next((o for o in opts if vote in o), None)
            if label is None:
                self.fail(name, f"no poll option containing {vote!r} in {opts}")
                return []
            code = await self.post({"type": "poll_vote", "poll_id": pid, "selected": [label], "ts": self.i,
                                    "voter_jid": "972500000000@s.whatsapp.net"})
        else:
            ev = {"type": "message", "id": mid or f"DQA{self.i}-{int(time.time() * 1000)}", "chat_jid": "dqa@g.us",
                  "is_group": True, "sender_jid": "972500000000@s.whatsapp.net", "ts": int(time.time()),
                  "from_me": False, "kind": kind, "text": text or ""}
            if kind == "image":
                ev["has_media"] = True
            code = await self.post(ev)
        got = await settle(n0, quiet=quiet) if code == 200 else []
        new_w = writes[w0:]
        msgs = [{"k": k, "t": t, "o": o} for k, t, o in got]
        ok = True
        why = ""
        if any("השתבש" in m["t"] for m in msgs):
            ok, why = False, "error reply"
        elif check is not None:
            try:
                res = check(msgs, new_w, code)
                ok, why = (res, "") if isinstance(res, bool) else res
            except Exception as e:  # noqa: BLE001
                ok, why = False, f"check crashed: {e}"
        self.transcript.append({"step": name, "http": code, "msgs": msgs,
                                "writes": [{k: v for k, v in w.items() if k != "data"} | {"keys": sorted((w.get("data") or {}).keys()) if isinstance(w.get("data"), dict) else str(w.get("data"))[:40]} for w in new_w]})
        tag = "PASS" if ok else "FAIL"
        summary = " | ".join(f"{m['k']}:{' '.join(m['t'].split())[:80]}" for m in msgs) or "(no reply)"
        wsum = ", ".join(f"{w['op']} {w['table']}" for w in new_w)
        print(f"{tag} {name}: HTTP {code} → {summary}" + (f"  [writes: {wsum}]" if wsum else "") + (f"  ← {why}" if why else ""), flush=True)
        if not ok:
            self.failures.append(f"{name}: {why}")
        return msgs

    def fail(self, name, why):
        print(f"FAIL {name}: {why}", flush=True)
        self.failures.append(f"{name}: {why}")


def has(text):
    return lambda msgs, w, c: (any(text in m["t"] for m in msgs), f"no reply containing {text!r}")


def heb(msgs, w, c):
    return (bool(msgs) and all(re.search(r"[֐-׿]", m["t"]) for m in msgs if m["k"] == "text"),
            "a reply without Hebrew")


def no_writes(msgs, w, c):
    return (not w, f"unexpected writes {[(x['op'], x['table']) for x in w]}")


def both(*checks):
    def f(msgs, w, c):
        for ch in checks:
            r = ch(msgs, w, c)
            ok, why = (r, "") if isinstance(r, bool) else r
            if not ok:
                return False, why
        return True, ""
    return f


async def main() -> int:
    out_json = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None
    install_write_guard()
    from bot.db import supabase_client as db
    from bot.utils.config import config
    from bot.whatsapp import cards, server

    # A real meal photo, read-only, for the photo flow.
    try:
        real = db.get_client()._real
        m = real.table("meals").select("photo_path").not_.is_("photo_path", "null").order("eaten_at", desc=True).limit(1).execute().data
        if m:
            PHOTO["bytes"] = real.storage.from_("meals").download(m[0]["photo_path"])
    except Exception as e:  # noqa: BLE001
        print(f"INFO photo: none available ({type(e).__name__}: {e})")

    gw = await fake_gateway()
    runner = await server.start()
    if runner is None:
        print("FAIL: listener did not start")
        return 1
    hdr = {"Authorization": f"Bearer {config.wa_token}"}
    async with httpx.AsyncClient(timeout=15) as c:
        d = Driver(c, hdr)
        S = d.step
        # --- read-only commands
        await S("help", text="עזרה", check=both(heb, has("CalTrack"), no_writes))
        await S("help_slash_en", text="/help", check=both(heb, has("CalTrack")))
        await S("summary", text="סיכום", check=heb)
        await S("summary_s", text="s", check=heb)
        await S("status", text="מצב", check=both(heb, has("מצב היום")))
        await S("history", text="היסטוריה", check=both(heb, has("הארוחות האחרונות")))
        await S("templates", text="תבניות", check=heb)
        await S("stats", text="נתונים", check=heb)
        # --- usage errors (no args)
        await S("weight_usage", text="משקל", check=both(heb, no_writes))
        await S("water_usage", text="מים", check=both(heb, no_writes))
        await S("run_usage", text="ריצה", check=both(heb, no_writes))
        # --- writes (captured, never executed)
        await S("weight", text="משקל 85.4", check=lambda m, w, c: (any(x["table"] == "weight_log" for x in w), "no weight_log write"))
        await S("water", text="מים 500", check=lambda m, w, c: (any(x["table"] == "water_log" for x in w), "no water_log write"))
        await S("run", text="ריצה 5.2 28:30 152", check=lambda m, w, c: (bool(w) and bool(m), "no run write/reply"))
        # --- typed meal: ✏️ grams → ✅ save
        await S("typed_meal", text="2 ביצים וטוסט", check=lambda m, w, c: (any(x["k"] == "poll" and x["t"] == cards.POLL_QUESTION for x in m)
                                                                         and not any(x["table"] in ("meals", "meal_items") for x in w), "no card/poll, or saved early"))
        await S("pending_hint", text="בננה", check=has("יש ארוחה פתוחה"))
        await S("vote_grams", vote="שנה כמות", check=heb)
        await S("grams_answer", text="1 150", check=lambda m, w, c: (any("150" in x["t"] for x in m), "card not updated to 150"))
        await S("vote_save", vote="שמור", check=lambda m, w, c: (any(x["table"] == "meals" for x in w) and any(x["table"] == "meal_items" for x in w)
                                                                  and any("נשמר" in x["t"] for x in m), "no meals+meal_items write or no 'נשמר'"))
        await S("stale_vote", vote="שמור", check=has("כבר לא בתוקף"))
        # --- single item: 🔄 rename, ➕ add, ❌ cancel
        await S("typed_single", text="חזה עוף 150 גרם", check=lambda m, w, c: (any(x["k"] == "poll" for x in m), "no poll"))
        await S("vote_rename", vote="זה לא", check=heb)
        await S("rename_answer", text="חזה הודו", check=heb)
        await S("vote_add", vote="הוסף פריט", check=heb)
        await S("add_answer", text="אורז לבן, 150", check=lambda m, w, c: (any("אורז" in x["t"] or "rice" in x["t"].lower() for x in m), "item not added"))
        await S("shortcut_set_weight", text="2 200", check=lambda m, w, c: (any("200" in x["t"] for x in m), "item 2 not set to 200"))
        await S("vote_cancel", vote="בטל", check=both(has("בוטל"), lambda m, w, c: (not any(x["table"] in ("meals", "meal_items") for x in w), "saved on cancel")))
        # --- undo (would delete the last meal: captured)
        await S("undo", text="ביטול", check=lambda m, w, c: (any(x["k"] == "poll" for x in m) or bool(m), "no undo prompt"))
        pid, opts = d.last_poll()
        keep = next((o for o in opts if "השאר" in o or "Keep" in o or "לא" in o), None)
        if keep:
            await S("undo_keep", vote=keep, check=lambda m, w, c: (not any(x["op"] == "delete" for x in w), "deleted on keep"))
        await S("undo_again", text="ביטול")
        pid, opts = d.last_poll()
        yes = next((o for o in opts if "כן" in o or "Yes" in o), None)
        if yes:
            await S("undo_yes", vote=yes, check=lambda m, w, c: (any(x["op"] == "delete" or x["table"] == "meals" for x in w), "no delete captured"))
        # --- photo flow (real photo, vision LLM; upload + save captured)
        if PHOTO["bytes"]:
            await S("photo", kind="image", text="", quiet=8.0,
                    check=lambda m, w, c: (any(x["k"] == "poll" for x in m) and any(x["table"].startswith("storage:") for x in w),
                                           "no card/poll or no (captured) upload"))
            await S("photo_save", vote="שמור", check=lambda m, w, c: (any(x["table"] == "meals" for x in w), "no meals write"))
        await S("barcode_cmd", text="ברקוד", check=heb)
        await S("label_cmd", text="תווית", check=heb)
        # --- other kinds, dedupe, auth
        for k in ("voice", "audio", "video", "document", "sticker"):
            await S(f"kind_{k}", kind=k, text="", check=has("רק טקסט ותמונות"))
        await S("dupe_first", text="מצב", mid="DQA-DUPE")
        await S("dupe_again", text="מצב", mid="DQA-DUPE", check=lambda m, w, c: (not m, "duplicate processed twice"), quiet=3.0)
        r = await c.post(f"http://127.0.0.1:{LISTEN}/wa/inbound", json={"type": "message"}, headers={"Authorization": "Bearer nope"})
        print(f"{'PASS' if r.status_code == 401 else 'FAIL'} auth_bad_token: HTTP {r.status_code}")
        if r.status_code != 401:
            d.failures.append("auth_bad_token")
        r = await c.post(f"http://127.0.0.1:{LISTEN}/wa/inbound", content=b"not json", headers=hdr)
        print(f"{'PASS' if r.status_code == 400 else 'FAIL'} bad_json: HTTP {r.status_code}")
        r = await c.post(f"http://127.0.0.1:{LISTEN}/wa/inbound", json={"type": "weird"}, headers=hdr)
        print(f"{'PASS' if r.status_code == 400 else 'FAIL'} unknown_type: HTTP {r.status_code}")
        r = await c.post(f"http://127.0.0.1:{LISTEN}/wa/inbound", json={"type": "message", "id": "x", "from_me": True, "kind": "text", "text": "מצב"}, headers=hdr)
        print(f"{'PASS' if r.json().get('ignored') == 'from_me' else 'FAIL'} from_me_ignored: {r.json()}")
        h = await c.get(f"http://127.0.0.1:{LISTEN}/wa/health")
        print(f"{'PASS' if h.json().get('ok') else 'FAIL'} health: {h.json()}")

        # --- scheduled jobs, called once (sends captured, writes captured)
        import bot.services.nudge as nudge
        try:
            import bot.main as bm
            jobs = [("job_nudge_breakfast", nudge.nudge_breakfast), ("job_nudge_lunch", nudge.nudge_lunch),
                    ("job_nudge_dinner", nudge.nudge_dinner), ("job_weekly_calibration", bm.weekly_calibration_job),
                    ("job_weekly_coach", bm.weekly_coach_job)]
        except Exception as e:  # noqa: BLE001
            d.fail("jobs_import", str(e))
            jobs = []

        class _Bot:                                  # old code sends to Telegram too: swallow it
            async def send_message(self, *a, **k):
                return None

        ctx = SimpleNamespace(bot=_Bot())
        for name, fn in jobs:
            n0, w0 = len(out), len(writes)
            t0 = time.time()
            try:
                await fn(ctx)
                err = ""
            except Exception as e:  # noqa: BLE001
                err = f"{type(e).__name__}: {e}"
            got = out[n0:]
            wsum = ", ".join(f"{w['op']} {w['table']}" for w in writes[w0:])
            ok = not err and not any("השתבש" in t for _k, t, _o in got)
            print(f"{'PASS' if ok else 'FAIL'} {name} ({time.time() - t0:.0f}s): "
                  + (" | ".join(" ".join(t.split())[:90] for _k, t, _o in got) or "(silent: meal already logged)")
                  + (f"  [writes: {wsum}]" if wsum else "") + (f"  ← {err}" if err else ""), flush=True)
            d.transcript.append({"step": name, "msgs": [{"k": k, "t": t, "o": o} for k, t, o in got],
                                 "writes": [{"op": w["op"], "table": w["table"]} for w in writes[w0:]]})
            if not ok:
                d.failures.append(name)

    await runner.cleanup()
    await gw.cleanup()
    if out_json:
        json.dump({"transcript": d.transcript, "writes": len(writes)}, open(out_json, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
    print(f"WRITES intercepted (none executed): {len(writes)}")
    print("DEEPQA " + ("OK" if not d.failures else f"FAILED {d.failures}"))
    return 1 if d.failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
