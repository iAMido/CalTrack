"""Hebrew for WhatsApp (Ido, 2026-10-15: "convert the commands and nudges to
Hebrew too"). The handlers keep their English (Telegram is unchanged during
the overlap week); every text that goes to WhatsApp passes through he_text(),
which rewrites the handlers' fixed phrasings. Anything not matched stays as
it was, so a new English string is never lost, only untranslated.
"""

import re

MEAL = {"breakfast": "ארוחת בוקר", "lunch": "ארוחת צהריים", "dinner": "ארוחת ערב", "snack": "נשנוש",
        "meal": "ארוחה"}
DAYS = {"Sunday": "ראשון", "Monday": "שני", "Tuesday": "שלישי", "Wednesday": "רביעי",
        "Thursday": "חמישי", "Friday": "שישי", "Saturday": "שבת"}
MONTHS = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                      "September", "October", "November", "December"], 1)}
MON3 = {m[:3]: i for m, i in MONTHS.items()}

# Hebrew command words → the English command (server.commands()).
COMMAND_ALIASES = {
    "משקל": "weight", "מים": "water", "ריצה": "run", "סיכום": "summary", "מצב": "status",
    "היסטוריה": "history", "ביטול": "undo", "עזרה": "help", "הוסף": "add", "תבנית": "template",
    "תבניות": "template", "שבוע": "week", "תווית": "label", "ברקוד": "barcode", "כיול": "calibrate",
    "נתונים": "stats",
}

HELP = """🤖 *CalTrack — מה אפשר לכתוב כאן*

*רישום*
📷 תמונה של הארוחה — ניתוח ושמירה
➕ `הוסף צהריים פיתה שווארמה` — רישום בכתב
📋 `תבנית` — ארוחה שמורה בלחיצה
⚖️ `משקל 87.3`
💧 `מים 500` (מ״ל)
🏃 `ריצה 5.2 28:30 152` (ק״מ, זמן, דופק)
🏷️ `תווית` — צילום תווית תזונה

*מעקב*
📊 `סיכום` — היום במלואו
🎯 `מצב` — כמה נשאר היום
📋 `היסטוריה 5` — הארוחות האחרונות
↩️ `ביטול` — ביטול הארוחה האחרונה
📈 `שבוע` — דוח המאמן השבועי
🔧 `כיול` / `נתונים` — BMR / TDEE ויעד

אפשר גם באנגלית, עם או בלי `/` (`s`, `/weight 87`)."""

EXACT = {
    "🔍 Analyzing your meal...": "🔍 מנתח את הארוחה…",
    "🔍 Breaking down your meal...": "🔍 מפרק את הארוחה…",
    "🔍 Reading the nutrition label...": "🔍 קורא את התווית…",
    "🔍 Decoding barcode…": "🔍 מפענח ברקוד…",
    "📊 Generating your weekly AI Coach report...": "📊 מכין את דוח המאמן השבועי…",
    "🔧 Recalculating BMR/TDEE...": "🔧 מחשב מחדש BMR/TDEE…",
    "❌ Session expired. Please send the photo again.": "⌛ הארוחה כבר לא פתוחה — שלח את התמונה שוב.",
    "Session expired. Please send the photo again.": "⌛ הארוחה כבר לא פתוחה — שלח את התמונה שוב.",
    "⚠️ Session expired. Please scan again.": "⌛ פג תוקף — סרוק שוב.",
    "Please type the food name.": "כתוב את שם המאכל.",
    "Please enter a valid number of grams, e.g. `150`": "כתוב מספר גרמים, למשל 150",
    "Format not recognised. Try: `chicken breast, 150`": "לא הבנתי. כתוב למשל: חזה עוף, 150",
    "🔄 Please send the photo again to re-analyze.": "🔄 שלח את התמונה שוב לניתוח מחדש.",
    "Usage: `/weight 87.3`": "כתוב למשל: `משקל 87.3`",
    "❌ Invalid weight. Use: `/weight 87.3`": "❌ לא הבנתי את המשקל. כתוב למשל: `משקל 87.3`",
    "Usage: `/water 500` (ml)": "כתוב למשל: `מים 500` (מ״ל)",
    "❌ Invalid amount. Use: `/water 500`": "❌ לא הבנתי את הכמות. כתוב למשל: `מים 500`",
    "Please describe what you ate.": "מה אכלת? כתוב למשל: `הוסף צהריים פיתה שווארמה`",
    "No meals to undo.": "אין ארוחה לבטל.",
    "No meals logged yet.": "עוד לא נרשמו ארוחות.",
    "↩️ Last meal undone.": "↩️ הארוחה האחרונה בוטלה.",
    "✅ Meal kept.": "✅ הארוחה נשארה.",
    "❌ Meal cancelled.": "❌ בוטל — הארוחה לא נשמרה.",
    "❌ Cancelled.": "❌ בוטל.",
    "❌ Template not found.": "❌ התבנית לא נמצאה.",
    "❌ Template has no items.": "❌ בתבנית אין פריטים.",
    "❌ AI analysis timed out. Please try again.": "❌ הניתוח לקח יותר מדי זמן. נסה שוב.",
    "❌ Could not process any ingredients.": "❌ לא הצלחתי לעבד את המרכיבים.",
    "❌ Could not generate the weekly report. Try again later.": "❌ לא הצלחתי להכין את הדוח השבועי. נסה שוב מאוחר יותר.",
    "❌ Calibration failed. Check logs for details.": "❌ הכיול נכשל.",
    "❌ Failed to save meal. Please try again.": "❌ השמירה נכשלה. נסה שוב.",
    "⚠️ No profile found.": "⚠️ לא נמצא פרופיל.",
    "⚠️ No user profile found.": "⚠️ לא נמצא פרופיל.",
    "📋 *Your Meal Templates*\nTap to log instantly:": "📋 *התבניות שלך*\nבחר בסקר כדי לרשום:",
    # /barcode, /label (deep QA 2026-10-20: these were still English)
    "📷 Send me a clear photo of the product barcode (EAN/UPC).": "📷 שלח תמונה ברורה של הברקוד של המוצר.",
    "📷 Send a photo of the nutrition label and I'll extract the macros.\nMake sure the *per 100g* column is clearly visible.":
        "📷 שלח תמונה של תווית הערכים התזונתיים, ואחלץ ממנה את הערכים.\nשהעמודה *ל-100 גרם* תהיה ברורה.",
    "🔍 Decoding barcode…": "🔍 מפענח את הברקוד…",
    "🔍 Reading the nutrition label...": "🔍 קורא את התווית…",
    "⚠️ Session expired. Please scan again.": "⚠️ פג תוקף. סרוק שוב.",
    "Session expired. Please send the photo again.": "⌛ פג תוקף. שלח את התמונה שוב.",
    "Please type the food name.": "כתוב את שם המאכל.",
    # Button labels (poll options)
    "✅ Yes, undo it": "✅ כן, לבטל", "❌ Keep it": "❌ להשאיר", "❌ Cancel": "❌ ביטול",
}

NUDGES = {
    "breakfast": ("🌅", "עוד לא רשמת ארוחת בוקר", "בוקר"),
    "lunch": ("🥗", "עוד לא רשמת ארוחת צהריים", "צהריים"),
    "dinner": ("🍽️", "עוד לא רשמת ארוחת ערב", "ערב"),
}


def _meal(m: re.Match, g: int = 1) -> str:
    return MEAL.get(m.group(g).lower(), m.group(g))


def _date_long(m: re.Match) -> str:       # "Thursday, October 15, 2026"
    return f"📊 *יום {DAYS.get(m.group(1), m.group(1))} {int(m.group(3)):02d}/{MONTHS.get(m.group(2), 0):02d}*"


def _date_short(m: re.Match) -> str:      # "Oct 15 21:45 — Dinner: 931 kcal"
    return (f"• {int(m.group(2)):02d}/{MON3.get(m.group(1), 0):02d} {m.group(3)} — "
            f"{MEAL.get(m.group(4).lower(), m.group(4))}: {m.group(5)} קל׳")


RULES: list[tuple[str, object]] = [
    # Nudges (bot/services/nudge.py)
    (r"^[🌅🥗🍽]\S* \*(Breakfast|Lunch|Dinner) not logged yet\*\nSend a photo or use `/add (\S+) \.\.\.`",
     lambda m: "{0} *{1}*\nשלח תמונה, או כתוב: `הוסף {2} …`".format(*NUDGES[m.group(1).lower()])),
    (r"\nQuick options:", "\nאפשרויות מהירות:"),
    (r"^  /t ", "  תבנית "),
    # /summary
    (r"^📊 \*(\w+), (\w+) (\d+), \d{4}\*", _date_long),
    (r"🍽 \*Meals:\*", "🍽️ *ארוחות:*"),
    (r"^  (\S+) (Breakfast|Lunch|Dinner|Snack): ([\d,]+) kcal(?: \((\d\d:\d\d)\))?$",
     lambda m: f"  {m.group(1)} {_meal(m, 2)}{' ' + m.group(4) if m.group(4) else ''} — {m.group(3)} קל׳"),
    (r"📥 Total in:\s+\*([\d,]+) kcal\*", r"📥 נכנס: *\1* קל׳"),
    (r"📤 Exercise:\s+\*(-?[\d,]+) kcal\*", r"🏃 פעילות: *\1* קל׳"),
    (r"📊 Net:\s+\*([-\d,]+) kcal\*", r"📊 נטו: *\1* קל׳"),
    (r"🎯 Target:\s+\*([\d,]+) kcal\*", r"🎯 יעד: *\1* קל׳"),
    (r"(✅|⚠️) Deficit:\s+\*([-+\d,]+) kcal\*", r"\1 גירעון: *\2* קל׳"),
    (r"(✅|⚠️) Surplus:\s+\*([-+\d,]+) kcal\*", r"\1 עודף: *\2* קל׳"),
    (r"💪 Macros: P (\d+)g \| C (\d+)g \| F (\d+)g \| Fiber (\d+)g",
     r"💪 חלבון \1 · פחמ׳ \2 · שומן \3 · סיבים \4 גר׳"),
    (r"💧 Water: ([\d.]+)L", r"💧 מים: \1 ל׳"),
    (r"⚖️ Weight: ([\d.]+) kg", r"⚖️ משקל: \1 ק״ג"),
    # /add and /template footer (before /status's "Remaining:")
    (r"Today: \*([\d,]+) / ([\d,]+) kcal\* \| Remaining: \*([-\d,]+) kcal\*",
     r"📊 היום: *\1 / \2* קל׳ · נשארו *\3*"),
    # /status
    (r"(✅|🔴) \*Today's status\*", r"\1 *מצב היום*"),
    (r"In: ([\d,]+) kcal \| Out: ([\d,]+) kcal", r"נכנס: \1 · פעילות: \2 קל׳"),
    (r"Net: ([-\d,]+) / ([\d,]+) kcal", r"נטו: \1 / \2 קל׳"),
    (r"Remaining: \*([-\d,]+) kcal\*", r"נשארו: *\1 קל׳*"),
    (r"Protein: (\d+)g / (\d+)g \((\d+)%\) — \*(\d+)g\* to go", r"חלבון: \1 / \2 גר׳ (\3%) — חסרים *\4 גר׳*"),
    (r"Fiber: (\d+)g / (\d+)g \((\d+)%\) — \*(\d+)g\* to go", r"סיבים: \1 / \2 גר׳ (\3%) — חסרים *\4 גר׳*"),
    # /history, /undo
    (r"📋 \*Last (\d+) meals:\*", r"📋 *\1 הארוחות האחרונות:*"),
    (r"^• (\w{3}) (\d+) (\d\d:\d\d) — (\w+): ([\d,]+) kcal$", _date_short),
    (r"^Undo last meal\? \*(\w+)\* \(([\d,]+) kcal\)",
     lambda m: f"↩️ לבטל את הארוחה האחרונה? *{_meal(m)}* ({m.group(2)} קל׳)"),
    # /weight, /water, /run
    (r"⚖️ Weight logged: \*([\d.]+) kg\*", r"⚖️ נרשם משקל: *\1 ק״ג*"),
    (r"💧 Water logged: \*(\d+) ml\*", r"💧 נרשמו *\1 מ״ל* מים"),
    (r"🏃 \*Run logged!\*", "🏃 *הריצה נרשמה!*"),
    (r"([\d.]+) km \| (\S+) \| (\S+)/km", r"\1 ק״מ · \2 · \3 לק״מ"),
    (r"Burned: ~(\d+) kcal", r"נשרפו ~\1 קל׳"),
    (r"^Usage: `/run <km> <mm:ss> \[heart_rate\]`\nExample: `/run 5\.2 28:30 152`",
     "כתוב למשל: `ריצה 5.2 28:30 152` (ק״מ, זמן, דופק)"),
    (r"^❌ Invalid format: (.*)\nExample: `/run 5\.2 28:30 152`", "❌ לא הבנתי. כתוב למשל: `ריצה 5.2 28:30 152`"),
    # /add, /template
    (r"^Usage: `/add \[meal\\_type\] <food description>`[\s\S]*",
     "כתוב מה אכלת, למשל:\n`הוסף צהריים פיתה שווארמה`\n`הוסף 150g חזה עוף`\n`הוסף ערב חלה עם שניצל וחומוס`"),
    (r"^✅ Added to (\w+)", lambda m: f"✅ נוסף ל{_meal(m)}"),
    (r"^✅ Logged \*(.+?)\* as (\w+)", lambda m: f"✅ נרשם *{m.group(1)}* כ{_meal(m, 2)}"),
    (r"^⏳ Logging \*(.+)\*\.\.\.", r"⏳ רושם *\1*…"),
    (r"\*Total: ([\d,]+) kcal\*", r"*סה״כ: \1 קל׳*"),
    (r'^❌ No template matching "(.+)"\.', r'❌ אין תבנית בשם "\1".'),
    (r"^📋 No templates saved yet\.[\s\S]*", "📋 עוד אין תבניות. אפשר לשמור תבנית בדשבורד: הוספת ארוחה ← שמירה כתבנית."),
    (r"^❌ Failed to save: (.*)", r"❌ השמירה נכשלה: \1"),
    # /barcode, /label with values
    (r"^❌ Could not read a barcode from that photo\.\n[\s\S]*",
     "❌ לא הצלחתי לקרוא ברקוד מהתמונה. נסה תמונה חדה ומוארת, או כתוב את המספר: `ברקוד 5000112545747`"),
    (r"^🔎 Looking up barcode `(\d+)`…", r"🔎 מחפש את הברקוד `\1`…"),
    (r"^❌ Product `(\d+)` not found in Open Food Facts database\.[\s\S]*", r"❌ המוצר `\1` לא נמצא במאגר Open Food Facts."),
    (r"^⚠️ Found \*(.+)\* but it has no calorie data\.", r"⚠️ מצאתי *\1* אבל אין לו נתוני קלוריות."),
    (r"^Per 100 g: \*([\d.]+) kcal\* \| P ([\d.]+)g · C ([\d.]+)g · F ([\d.]+)g · Fib ([\d.]+)g",
     r"ל-100 גרם: *\1 קל׳* · חלבון \2 · פחמ׳ \3 · שומן \4 · סיבים \5"),
    (r"How many grams did you eat\?", "כמה גרם אכלת?"),
    (r"^✅ Logged \*(.+)\* \((\d+) g\) — \*(\d+) kcal\*", r"✅ נרשם *\1* (\2 גר׳) — *\3 קל׳*"),
    (r"^❌ Could not read the label\.[\s\S]*", "❌ לא הצלחתי לקרוא את התווית. ודא שהטבלה ברורה ונסה שוב (`תווית`)."),
    (r"^Format not recognised\. Try: `chicken breast, 150`", "לא הבנתי. כתוב שם וכמות, למשל: `חזה עוף, 150`"),
    (r"^Please enter a valid number of grams, e\.g\. `150`", "כתוב מספר גרמים, למשל `150`"),
    # /stats
    (r"^🔧 \*System Stats\*", "🔧 *נתוני מערכת*"),
    (r"^🎯 Target: ([\d.]+) kg", r"🎯 יעד: \1 ק״ג"),
    (r"^🍽 Daily target: (\d+) kcal", r"🍽️ יעד יומי: \1 קל׳"),
    (r"^📅 Last calibration: (.+)$", r"📅 כיול אחרון: \1"),
    # Calibration (bot/services/calibration.py)
    (r"📊 \*Calibration updated\* \((.*?)\)", "📊 *הכיול עודכן*"),
    (r"⚖️ Weight used: \*([\d.]+) kg\* \(7-day avg\)", r"⚖️ משקל בחישוב: *\1 ק״ג* (ממוצע 7 ימים)"),
    (r"7-day trend: \*([-+\d.]+) kg\*", r"מגמה ב-7 ימים: *\1 ק״ג*"),
    (r"🎯 Daily target: ", "🎯 יעד יומי: "),
    # Generic units, last: "(150g)" and "kcal" anywhere left
    (r"\((\d+)g\)", r"(\1 גר׳)"),
    (r"(\d\**) kcal\b", r"\1 קל׳"),
]
_COMPILED = [(re.compile(p, re.MULTILINE), r) for p, r in RULES]


def he_text(text: str) -> str:
    if not text:
        return text
    if text in EXACT:
        return EXACT[text]
    if text.startswith("🤖 *CalTrack Commands*"):
        return HELP
    for rx, repl in _COMPILED:
        text = rx.sub(repl, text)
    return text
