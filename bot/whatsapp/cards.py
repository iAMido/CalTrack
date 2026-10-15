"""WhatsApp-native Hebrew meal card (Ido, 2026-10-15: the Telegram-style card
with 9 poll options "is not clear").

One short card per state of the pending meal, and a 4–5 option poll:
✅ save · ✏️ grams · 🔄 wrong food · ➕ add · ❌ cancel. Gram suggestion
buttons are gone; grams are typed. The handlers still do the work: the poll
options map to their callback_data, or to "wa:*" steps handled in server.py.
"""

from bot.services.nutrition import calculate_meal_totals

MEAL_HE = {"breakfast": ("☀️", "ארוחת בוקר"), "lunch": ("🌤️", "ארוחת צהריים"),
           "dinner": ("🌙", "ארוחת ערב"), "snack": ("🍪", "נשנוש")}
POLL_QUESTION = "לשמור את הארוחה?"
SAVE, GRAMS, ADD, CANCEL = "✅ שמור", "✏️ שנה כמות", "➕ הוסף פריט", "❌ בטל"
FIX_MANY = "🔄 תקן פריט"

# Fixed English handler replies → Hebrew (exact match, after Markdown).
TRANSLATE = {
    "🔍 Analyzing your meal...": "🔍 מנתח את הארוחה…",
    "❌ Session expired. Please send the photo again.": "⌛ הארוחה כבר לא פתוחה — שלח את התמונה שוב.",
    "Session expired. Please send the photo again.": "⌛ הארוחה כבר לא פתוחה — שלח את התמונה שוב.",
    "Please type the food name.": "כתוב את שם המאכל.",
    "Please enter a valid number of grams, e.g. `150`": "כתוב מספר גרמים, למשל 150",
    "Format not recognised. Try: `chicken breast, 150`": "לא הבנתי. כתוב למשל: חזה עוף, 150",
    "🔄 Please send the photo again to re-analyze.": "🔄 שלח את התמונה שוב לניתוח מחדש.",
}


def item_name(item: dict) -> str:
    return (item.get("ingredient_name_he") or item.get("ingredient_name") or "פריט").strip()


def _n(x) -> int:
    return int(round(x or 0))


def render_meal(pending: dict, now_hhmm: str) -> str:
    emoji, title = MEAL_HE.get(pending.get("meal_type"), ("🍽️", "ארוחה"))
    items = pending.get("items") or []
    many = len(items) > 1
    lines = [f"{emoji} *{title}* · {now_hhmm}", ""]
    for i, it in enumerate(items):
        w, ai = it.get("weight_grams") or 0, it.get("ai_estimated_grams")
        num = f"{i + 1}. " if many else ""
        lines.append(f"{num}*{item_name(it)}* — {w} גר׳ · {_n(it.get('calories'))} קל׳")
        if it.get("auto_approved"):
            lines.append("   _(לפי מה שאכלת בעבר)_")
        elif ai and ai != w:
            lines.append(f"   _(הערכת AI: {ai} גר׳)_")
    t = calculate_meal_totals(items)
    lines += ["", f"🔥 *{_n(t['total_calories'])} קל׳* · חלבון {_n(t['total_protein_g'])} · "
                  f"פחמ׳ {_n(t['total_carbs_g'])} · שומן {_n(t['total_fat_g'])}"]
    return "\n".join(lines)


def meal_options(pending: dict) -> dict[str, str]:
    items = pending.get("items") or []
    opts = {SAVE: "ok"}
    if len(items) == 1:
        opts[GRAMS] = "w:0:m"
        opts[f"🔄 זה לא {item_name(items[0])[:40]}"] = "rename:0"
    elif items:
        opts[GRAMS] = "wa:grams"
        opts[FIX_MANY] = "wa:fix"
    opts[ADD] = "add"
    opts[CANCEL] = "wa:cancel"
    return opts


def prompt_for(data: str, pending: dict) -> str | None:
    """The Hebrew question for a step that waits for typed text."""
    items = (pending or {}).get("items") or []
    if data.startswith("w:") and data.endswith(":m"):
        i = int(data.split(":")[1])
        return f"✏️ כמה גרם *{item_name(items[i])}*? כתוב מספר, למשל 150" if i < len(items) else None
    if data.startswith("rename:"):
        i = int(data.split(":")[1])
        return f"🔄 מה זה באמת, במקום *{item_name(items[i])}*? כתוב את שם המאכל" if i < len(items) else None
    if data == "add":
        return "➕ מה להוסיף? כתוב שם וכמות, למשל: אורז לבן, 150"
    if data == "wa:grams":
        return "✏️ איזה פריט וכמה גרם? למשל: 2 150"
    if data == "wa:fix":
        return "🔄 איזה פריט ומה הוא באמת? למשל: 2 חזה עוף"
    return None


def render_saved(meal_kcal: int, daily: dict) -> str:
    cal_in = _n(daily.get("total_calories_in"))
    target = _n(daily.get("target_calories") or 2000)
    burned = _n(daily.get("calories_burned_exercise"))
    water = (daily.get("water_ml") or 0) / 1000
    lines = [f"✅ *נשמר* · {meal_kcal} קל׳", "",
             f"📊 היום: *{cal_in:,} / {target:,}* קל׳ · נשארו *{target - cal_in:,}*"]
    if burned:
        lines.append(f"🏃 שרפת {burned:,} קל׳")
    lines.append(f"🍽️ {daily.get('meal_count') or 0} ארוחות · 💧 {water:.1f} ל׳")
    return "\n".join(lines)
