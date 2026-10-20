"""WhatsApp smoke test for CalTrack, end to end, NOTHING sent (2026-10-20, the
"remove Telegram" clean-up: each step must answer exactly like the last).

Starts the real WhatsApp listener on a private port with a FAKE gateway that
captures every /send and /poll, then posts real-shaped events (Hebrew
commands, a typed meal → card + poll, ❌ cancel, a voice note). Reads the real
database (summary, status…); never saves: the meal is cancelled.

  docker run --rm --network host --env-file /etc/caltrack/caltrack.env \\
      -v <checkout>:/app -w /app caltrack-caltrack:latest python scripts/wa_smoke.py [baseline.json]

With a baseline file: compares each step's SHAPE (who answered, how many
messages/polls, first words with digits masked) and exits 1 on a difference.
Without one: prints the shapes as JSON (save them as the baseline).
"""

import asyncio
import json
import os
import re
import sys
import time

FAKE_GW, LISTEN = 18089, 18093
os.environ["WA_GATEWAY_URL"] = f"http://127.0.0.1:{FAKE_GW}"
os.environ["WA_LISTEN_PORT"] = str(LISTEN)
os.environ["WA_LISTEN_HOST"] = "127.0.0.1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx  # noqa: E402
from aiohttp import web  # noqa: E402

out: list[tuple[str, str, list]] = []          # (kind, text/question, options)


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
        return web.json_response({"error": "not found"}, status=404)

    app = web.Application()
    app.router.add_post("/send", send)
    app.router.add_post("/poll", poll)
    app.router.add_get("/media/{id}", media)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", FAKE_GW).start()
    return runner


def shape(items: list) -> list:
    """Stable across days: kind + the first words, digits masked."""
    return [[k, re.sub(r"\d", "#", " ".join(t.split())[:24]), len(o)] for k, t, o in items]


async def settle(n0: int, quiet: float = 4.0, limit: float = 90.0) -> list:
    t0, last_n, last_t = time.time(), len(out), time.time()
    while time.time() - t0 < limit:
        await asyncio.sleep(0.5)
        if len(out) != last_n:
            last_n, last_t = len(out), time.time()
        elif len(out) > n0 and time.time() - last_t >= quiet:
            break
    return out[n0:]


async def main() -> int:
    from bot.utils.config import config
    from bot.whatsapp import server

    gw = await fake_gateway()
    runner = await server.start()
    if runner is None:
        print("FAIL: WhatsApp listener did not start (WA_TOKEN missing?)")
        return 1
    hdr = {"Authorization": f"Bearer {config.wa_token}"}
    owner = "972500000000@s.whatsapp.net"
    steps = [
        ("help", {"kind": "text", "text": "עזרה"}),
        ("summary", {"kind": "text", "text": "סיכום"}),
        ("status", {"kind": "text", "text": "מצב"}),
        ("history", {"kind": "text", "text": "היסטוריה"}),
        ("week", {"kind": "text", "text": "שבוע"}),
        ("typed_meal", {"kind": "text", "text": "2 ביצים וטוסט"}),
        ("cancel", None),                     # ❌ on the meal poll
        ("voice", {"kind": "voice", "text": ""}),
    ]
    results, bad = {}, []
    async with httpx.AsyncClient(timeout=10) as c:
        for i, (name, ev) in enumerate(steps):
            n0 = len(out)
            if ev is None:
                poll = next(((f"P{j + 1}", o) for j, (k, _q, o) in reversed(list(enumerate(out))) if k == "poll"), None)
                if poll is None:
                    bad.append(f"{name}: no meal poll to vote on")
                    continue
                cancel = next(o for o in poll[1] if "בטל" in o)
                body = {"type": "poll_vote", "poll_id": poll[0], "selected": [cancel], "ts": i, "voter_jid": owner}
            else:
                body = {"type": "message", "id": f"SMOKE{i}-{int(time.time())}", "chat_jid": "smoke@g.us",
                        "is_group": True, "sender_jid": owner, "ts": int(time.time()), "from_me": False, **ev}
            r = await c.post(f"http://127.0.0.1:{LISTEN}/wa/inbound", json=body, headers=hdr)
            got = await settle(n0)
            results[name] = shape(got)
            errors = [t for _k, t, _o in got if "השתבש" in t]
            print(f"{'PASS' if got and not errors else 'FAIL'} {name}: HTTP {r.status_code} → "
                  + " | ".join(f"{k}:{' '.join(t.split())[:70]}" for k, t, _o in got), flush=True)
            if not got or errors:
                bad.append(name)
    await runner.cleanup()
    await gw.cleanup()

    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        base = json.load(open(sys.argv[1], encoding="utf-8"))
        for name, sh in base.items():
            if results.get(name) != sh:
                bad.append(f"{name} changed: {sh} → {results.get(name)}")
    else:
        print("BASELINE " + json.dumps(results, ensure_ascii=False))
    print("SMOKE " + ("OK" if not bad else f"FAILED {bad}"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
