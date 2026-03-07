import os
import time
import asyncio
import logging
import random
from typing import Dict, Optional

from fastapi import FastAPI, Request
from telegram import Update, Message, Chat, User
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)

# --------------------
# קונפיגורציה בסיסית
# --------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

BOT_TOKEN = os.environ["BOT_TOKEN"]               # טוקן מה-BotFather
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]     # מחרוזת אקראית לנתיב ה-webhook
PUBLIC_URL = os.environ.get("PUBLIC_URL")         # למשל: https://my-bot.onrender.com
SPECIAL_USER_ID = 919782824

DEBOUNCE_SECONDS = float(os.environ.get("DEBOUNCE_SECONDS", "1"))
AUTO_DELETE_SECONDS = int(os.environ.get("AUTO_DELETE_SECONDS", "0"))

GREETINGS_H = [
    "שיהיה לך טחורים בפה אמן !!",
    "שתיפלי לבור מלא עם האוטו וייכנס לך הישר בתחת אמן !!",
    "הלוואי וכל פעם שתכיני שקשוקה הביצים יהיו קשות!",
    "שכל פעם שתפתחי פחית טונה היא תפריץ לך לעין",
    "שיתקלקל לך המטען באמצע הלילה אמן",
    "שירד מבול ויהיה לך חור במטרייה בדיוק מעל הראש",
    "שתלכי לים תפתחי אבטיח והוא יהיה מפוצץ בגרעינים",
    "שיהיה לך צרבת",
    "שכל פעם שתכיני קפה לא יהיה לך חלב",
    "שתחפשי חניה תחשבי שמצאת ובום קאיה פיקנטו",
    "שיגמר לך הדלק בכביש 6",
    "שתתעטשי בדיוק כשאת שותה מים",
    "שתזמיני אוכל והוא יגיע קר",
    "שתיתקעי בפקק ויהיה לך ראש צב",
    "שתסבלי משלשולים קשים",
    "שתלבשי מכנס לבן ותקבלי מחזור",
    "שתיתקעי בלי טמפון אמן",
    "שיהיה לך עדכון לנייד בדיוק כשצריך לצאת מהבית",
    "שתדרכי על מים עם גרביים",
    "שיהיה לך ריח של קלמנטינה תקוע באף",
    "שתתלבשי יפה תכיני קפה תבואי לצאת מהבית ויישפך עלייך הכל",
    "שיהיה לך כוויה בגבות מהשעווה",
    "שתחתכי לימון והוא ישפריץ לך לעין",
    "שתתני ביס בקרמבו והוא יהיה ריק מבפנים",
    "שינעלו לך המפתחות בתוך האוטו",
    "שיתקע לך במוח השיר מקרנה",
    "שתלכי למטבח ותשכחי למה באת",
    "שלא יהיה לך חניה ברחוב",
    "שתכיני קפה תשבי לשתות ואז תגלי ששכחת סוכר",
    "שתנקי את האוטו ויהיה מלא אבק",
    "שתלבשי גרביים ותגלי שיש חור קטן בדיוק בבוהן",
    "שתכיני פופקורן ויישארו מלא גרעינים",
    "שתלכי יחפה בבית ותדרכי על לגו",
    "שתשבי על כסא פלסטיק והוא יישבר ותתרסקי",
    "שתיכנסי למיטה ותיזכרי ששכחת לכבות את האור",
    "שתשימי כביסה ותמצאי טישו שהתפרק בפנים",
    "שתפתחי במבה והיא תהיה פירורים",
    "שתגיעי הביתה עם פיפי דחוף תבואי לפתוח את הדלת וישבר לך המפתח בפנים",
    "שיהיה לך אפצ'ים בנהיגה",
    "שתסתובבי יום שלם עם פטרוזיליה בשיניים",
    "שיהיה לך כתם שמן בחולצה יקרה",
    "שתדרכי על חרא בנעליים יקרות",
    "שייכנס לך החוטיני לתחת",
    "שתבואי לסבתא תרצי לשתות ויהיה רק מים מהברז או קריסטל מנטה"
]

# --------------------
# ברכות רנדומליות /at /ata
# --------------------
GREETINGS_F = [
    "שתמיד תזכרי שהחיים לא קורים לך — הם קורים בשבילך.",
    "שתבחרי בעצמך גם בימים שאת שוכחת כמה את שווה.",
    "שתהיי אמיצה מספיק להתחיל וחכמה מספיק לא לוותר.",
    "שתמצאי את הדרך שלך גם כשכולם הולכים בכיוון אחר.",
    "שתמיד תזכרי: הפחד הוא לפעמים רק סימן שאת בכיוון הנכון.",
    "שתביני יום אחד שהכוח שחיפשת בחוץ תמיד היה בתוכך.",
    "שתעשי לפחות דבר אחד ביום שמקרב אותך לחיים שאת באמת רוצה.",
    "שתדעי לעצור לפעמים ולהגיד: וואלה… אני גאה בעצמי.",
    "שהקפה שלך יהיה חזק כמו הביטחון העצמי שלך בבוקר.",
    "שתמיד יהיה לך מקום חניה… גם בתל אביב.",
    "שהמקרר שלך יהיה מלא גם כשלא עשית קניות.",
    "שתשלחי הודעה חשובה… וכולם יענו רק עם אימוג'י.",
    "שתכתבי משהו בקבוצה… וכולם יחשבו שזה חכם.",
    "מאחלים לך שהארלי תענה לך ושנה טובה.",
    "מה קשור התגובה הזו? התפלפלת על כל הראש.",
    "את לא מצחיקה, את לא מעניינת — תחכי לי במיטה עכשיו!",
    "שתמיד יהיה לך מישהו שמאמין בך גם כשאת קצת שוכחת להאמין בעצמך.",
    "שתפגשי אנשים טובים בדיוק בזמן שאת צריכה אותם.",
    "שתזכרי שגם ימים קשים הם רק פרק — לא כל הסיפור.",
    "שתמיד יהיה לך מקום שבו את יכולה להיות פשוט את.",
    "שתמצאי רגעים קטנים של אושר גם בימים רגילים לגמרי.",
    "תמשיכי להיות אגדה ולא הגדה יא תחת.",
    "שתפסיקי יום אחד לחכות לזמן הנכון — ופשוט תתחילי.",
    "שתעזי לחלום בגדול גם אם זה מפחיד אחרים.",
    "שתבחרי בדרך שלך גם אם היא פחות נוחה.",
    "שתזכרי שהחיים קצרים מדי בשביל לחיות על אוטומט.",
    "שתהיי הגרסה של עצמך שאנשים עוד לא פגשו.",
    "את בדיחה וגם אותה לא מבינים.",
    "שתחשבי שאת מצחיקה ותקבלי דיק פיק שיסתום אותך."
    "שתהיה לך הצלחה גדולה בכל מה שאת נוגעת בו ✨",
    "מאחלת לך יום מלא באנרגיה טובה וחיוכים 😊",
    "שתגשימי את כל המטרות שלך צעד אחרי צעד 💪",
    "מאחלת לך ביטחון עצמי ושקט פנימי היום 🌸",
    "שתקבלי בשורות טובות ומשמחות 💛",
    "שתהיי מוקפת באנשים שעושים לך טוב 🌷",
    "מאחלת לך כוח להתמודד עם כל אתגר 💫",
    "שתמצאי זמן גם לעצמך בתוך כל העומס 🌿",
    "שתרגישי גאווה בכל התקדמות קטנה 🌟",
    "מאחלת לך שלווה, הצלחה ובריאות 🌺",
    "שתזכי להערכה שמגיעה לך 👑",
    "מאחלת לך ימים קלים ולילות רגועים 🌙",
    "שתמשיכי לזהור כמו שאת יודעת ✨",
    "שתהיי חזקה מול כל מכשול 💪",
    "מאחלת לך שפע והזדמנויות חדשות 💎",
    "שתחייכי יותר ותדאגי פחות 😄",
    "שתקבלי החלטות בלב שלם 💖",
    "מאחלת לך יום מלא השראה 🌼",
    "שתמשיכי לגדול ולהתפתח בכל תחום 🌱",
    "מאחלת לך הצלחות קטנות וגדולות כאחד 🎯",
    "שתרגישי בטוחה בדרך שלך 🌷",
    "שתפגשי אנשים שמרימים אותך למעלה 💛",
    "מאחלת לך רגעים יפים ומרגשים 🌅",
    "שתדעי שאת מסוגלת ליותר ממה שאת חושבת 💫",
    "שתגשימי חלום אחד לפחות בקרוב ✨",
    "מאחלת לך אושר אמיתי ופשוט 💖",
    "שתהיה לך בהירות מחשבתית והחלטות חכמות 🧠",
    "שתרגישי שלמה עם עצמך 🌸",
    "מאחלת לך ימים של התקדמות ושקט 🌿",
    "שתחווי הפתעה טובה היום 🎁",
    
]

GREETINGS_M = [
    "שתמיד תזכור שהחיים לא קורים לך — הם קורים בשבילך.",
    "שתבחר בעצמך גם בימים שאתה שוכח כמה אתה שווה.",
    "שתהיה אמיץ מספיק להתחיל וחכם מספיק לא לוותר.",
    "שתמצא את הדרך שלך גם כשכולם הולכים בכיוון אחר.",
    "שתמיד תזכור: הפחד הוא לפעמים רק סימן שאתה בכיוון הנכון.",
    "שתבין יום אחד שהכוח שחיפשת בחוץ תמיד היה בתוכך.",
    "שתעשה לפחות דבר אחד ביום שמקרב אותך לחיים שאתה באמת רוצה.",
    "שתדע לעצור לפעמים ולהגיד: וואלה… אני גאה בעצמי.",
    "שהקפה שלך יהיה חזק כמו הביטחון העצמי שלך בבוקר.",
    "שתמיד יהיה לך מקום חניה… גם בתל אביב.",
    "שהמקרר שלך יהיה מלא גם כשלא עשית קניות.",
    "שתשלח הודעה חשובה… וכולם יענו רק עם אימוג'י.",
    "שתכתוב משהו בקבוצה… וכולם יחשבו שזה חכם.",
    "מאחלים לך שאראלה תתקשר אליך ושנה טובה.",
    "מה קשור התגובה הזו? התפלפלת על כל הראש.",
    "אתה לא מצחיק, אתה לא מעניין — תחכה לי במיטה עכשיו!",
    "שתמיד יהיה לך מישהו שמאמין בך גם כשאתה קצת שוכח להאמין בעצמך.",
    "שתפגוש אנשים טובים בדיוק בזמן שאתה צריך אותם.",
    "שתזכור שגם ימים קשים הם רק פרק — לא כל הסיפור.",
    "שתמיד יהיה לך מקום שבו אתה יכול להיות פשוט אתה.",
    "שתמצא רגעים קטנים של אושר גם בימים רגילים לגמרי.",
    "תמשיך להיות אגדה ולא הגדה יא תחת.",
    "שתפסיק יום אחד לחכות לזמן הנכון — ופשוט תתחיל.",
    "שתעז לחלום בגדול גם אם זה מפחיד אחרים.",
    "שתבחר בדרך שלך גם אם היא פחות נוחה.",
    "שתזכור שהחיים קצרים מדי בשביל לחיות על אוטומט.",
    "שתהיה הגרסה של עצמך שאנשים עוד לא פגשו.",
    "שתיכנס לקבוצה לרגע… ומישהו כבר מפלרטט איתך.",
    "שתכתוב 'מי ערה?'… ורק גברים יענו לך.",
    "שתהיה לך הצלחה גדולה בכל מה שאתה נוגע בו ✨",
    "מאחל לך יום מלא באנרגיה טובה וחיוכים 😄",
    "שתגשים את כל המטרות שלך צעד אחרי צעד 💪",
    "מאחל לך ביטחון עצמי ושקט פנימי 🔥",
    "שתקבל בשורות טובות ומשמחות 💛",
    "שתהיה מוקף באנשים שעושים לך טוב 🤝",
    "מאחל לך כוח להתמודד עם כל אתגר 💫",
    "שתמצא זמן גם לעצמך בתוך כל העומס 🌿",
    "שתרגיש גאווה בכל התקדמות קטנה 🌟",
    "מאחל לך שלווה, הצלחה ובריאות 🕊️",
    "שתזכה להערכה שמגיעה לך 👑",
    "מאחל לך ימים קלים ולילות רגועים 🌙",
    "שתמשיך לזהור כמו שאתה יודע ✨",
    "שתהיה חזק מול כל מכשול 💪",
    "מאחל לך שפע והזדמנויות חדשות 💎",
    "שתחייך יותר ותדאג פחות 😄",
    "שתקבל החלטות בלב שלם ❤️",
    "מאחל לך יום מלא השראה 🌞",
    "שתמשיך לגדול ולהתפתח בכל תחום 🌱",
    "מאחל לך הצלחות קטנות וגדולות כאחד 🎯",
    "שתרגיש בטוח בדרך שלך 🚀",
    "שתפגוש אנשים שמרימים אותך למעלה 💛",
    "מאחל לך רגעים יפים ומרגשים 🌅",
    "שתדע שאתה מסוגל ליותר ממה שאתה חושב 💫",
    "שתגשים חלום אחד לפחות בקרוב ✨",
    "מאחל לך אושר אמיתי ופשוט ❤️",
    "שתהיה לך בהירות מחשבתית והחלטות חכמות 🧠",
    "שתרגיש שלם עם עצמך 🌿",
    "מאחל לך ימים של התקדמות ושקט 🕊️",
    "שתחווה הפתעה טובה היום 🎁",
]

# --------------------
# /set_time config (סטיקי)
# --------------------
DEFAULT_ACTIVE_MINUTES = 5
MIN_ACTIVE_MINUTES = 1
MAX_ACTIVE_MINUTES = 20

# --------------------
# /clear_media config
# --------------------
DEFAULT_MEDIA_DELETE_MINUTES = 5
MIN_MEDIA_DELETE_MINUTES = 1
MAX_MEDIA_DELETE_MINUTES = 60  # אפשר לשנות אם תרצה

# --------------------
# מצב זיכרון לסטיקי
# --------------------
# chat_id -> {
#   "mode": "text" | "copy",
#   "text": Optional[str],
#   "src_chat_id": Optional[int],
#   "src_msg_id": Optional[int],
#   "current_msg_id": Optional[int],
#   "active_until": Optional[float],  # epoch seconds; אם עבר - מפסיקים להזיז + מוחקים את ההודעה המודבקת
# }
sticky_state: Dict[int, Dict] = {}
repost_tasks: Dict[int, asyncio.Task] = {}

# --------------------
# מצב למחיקת מדיה (תמונות)
# --------------------
# chat_id -> {
#   "enabled": bool,
#   "delete_after_minutes": int
# }
media_policy: Dict[int, Dict] = {}

# --------------------
# FastAPI + Telegram
# --------------------
api = FastAPI()
application = Application.builder().token(BOT_TOKEN).build()


# ====== Helpers ======

def pick_random_h_greeting() -> str:
    return random.choice(GREETINGS_H)


def get_replied_user(update: Update) -> Optional[User]:
    msg = update.effective_message
    if not msg or not getattr(msg, "reply_to_message", None):
        return None
    return msg.reply_to_message.from_user


def is_special_user(user: Optional[User]) -> bool:
    return bool(user and user.id == SPECIAL_USER_ID)

def pick_random_greeting(is_female: bool) -> str:
    pool = GREETINGS_F if is_female else GREETINGS_M
    return random.choice(pool)


def get_reply_to_message_id(update: Update) -> Optional[int]:
    """
    אם הפקודה נשלחה כ-Reply להודעה של מישהו:
    מחזיר את message_id של ההודעה המקורית כדי שהבוט יעשה Reply אליה.
    אם לא נשלח כ-Reply -> מחזיר None.
    """
    msg = update.effective_message
    if not msg or not getattr(msg, "reply_to_message", None):
        return None
    return msg.reply_to_message.message_id


async def notify_and_autodelete(chat_id: int, text: str, context: ContextTypes.DEFAULT_TYPE):
    """שולח הודעה קצרה ומוחק אותה אוטומטית אחרי AUTO_DELETE_SECONDS (אם >0)."""
    try:
        sent = await context.bot.send_message(chat_id=chat_id, text=text)
        if AUTO_DELETE_SECONDS > 0:
            async def _later():
                await asyncio.sleep(AUTO_DELETE_SECONDS)
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=sent.message_id)
                except Exception:
                    pass
            asyncio.create_task(_later())
    except Exception:
        pass


async def is_user_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat = update.effective_chat
    user = update.effective_user
    msg = update.effective_message

    if not chat:
        return False

    # אדמין אנונימי: אם ההודעה נשלחת בשם הקבוצה/ערוץ (sender_chat קיים)
    if msg and getattr(msg, "sender_chat", None):
        try:
            if msg.sender_chat.id == chat.id:
                return True
        except Exception:
            pass

    if not user:
        return False
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


def clamp_minutes(value: int, min_v: int, max_v: int) -> int:
    return max(min_v, min(max_v, value))


def compute_active_until(minutes: int) -> float:
    return time.time() + (minutes * 60)


def is_sticky_active(st: Dict) -> bool:
    active_until = st.get("active_until")
    if not active_until:
        return False
    return time.time() <= float(active_until)


async def schedule_delete_message(chat_id: int, message_id: int, delay_seconds: int, context: ContextTypes.DEFAULT_TYPE):
    """מתזמן מחיקת הודעה לאחר delay_seconds. לא זורק חריגות החוצה."""
    async def _later():
        await asyncio.sleep(max(0, int(delay_seconds)))
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            pass
    asyncio.create_task(_later())


async def delete_current_sticky(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """מוחק את ההודעה המודבקת הנוכחית (אם קיימת) ומנקה current_msg_id."""
    st = sticky_state.get(chat_id)
    if not st:
        return
    cur = st.get("current_msg_id")
    if cur:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=cur)
        except Exception:
            pass
        st["current_msg_id"] = None


# ====== Core sticky functions ======

async def post_or_repost_sticky(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    st = sticky_state.get(chat_id)
    if not st:
        return

    # למחוק הודעת סטיקי קודמת אם קיימת
    prev_id = st.get("current_msg_id")
    if prev_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=prev_id)
        except Exception as e:
            logging.debug(f"Delete previous sticky failed (maybe already gone): {e}")

    # לשלוח מחדש בהתאם למצב (טקסט או copy_message)
    try:
        if st["mode"] == "text":
            sent = await context.bot.send_message(chat_id=chat_id, text=st["text"])
        else:
            sent = await context.bot.copy_message(
                chat_id=chat_id,
                from_chat_id=st["src_chat_id"],
                message_id=st["src_msg_id"]
            )
        st["current_msg_id"] = sent.message_id
    except Exception as e:
        logging.error(f"Failed to post sticky: {e}")


# ====== Command Handlers ======

async def greet_female(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if not chat:
        return

    # אם המשתמש המיוחד מנסה להפעיל את הבוט בעצמו - לא לעשות כלום
    if is_special_user(user):
        try:
            if update.message:
                await context.bot.delete_message(chat_id=chat.id, message_id=update.message.message_id)
        except Exception:
            pass
        return

    reply_to_id = get_reply_to_message_id(update)
    replied_user = get_replied_user(update)

    # אם הפקודה הופעלה על הודעה של המשתמש המיוחד
    if is_special_user(replied_user):
        text = pick_random_h_greeting()
    else:
        text = pick_random_greeting(is_female=True)

    await context.bot.send_message(
        chat_id=chat.id,
        text=text,
        reply_to_message_id=reply_to_id,
        disable_web_page_preview=True
    )

    try:
        if update.message:
            await context.bot.delete_message(chat_id=chat.id, message_id=update.message.message_id)
    except Exception:
        pass


async def greet_male(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if not chat:
        return

    # אם המשתמש המיוחד מנסה להפעיל את הבוט בעצמו - לא לעשות כלום
    if is_special_user(user):
        try:
            if update.message:
                await context.bot.delete_message(chat_id=chat.id, message_id=update.message.message_id)
        except Exception:
            pass
        return

    reply_to_id = get_reply_to_message_id(update)
    replied_user = get_replied_user(update)

    # אם הפקודה הופעלה על הודעה של המשתמש המיוחד
    if is_special_user(replied_user):
        text = pick_random_h_greeting()
    else:
        text = pick_random_greeting(is_female=False)

    await context.bot.send_message(
        chat_id=chat.id,
        text=text,
        reply_to_message_id=reply_to_id,
        disable_web_page_preview=True
    )

    try:
        if update.message:
            await context.bot.delete_message(chat_id=chat.id, message_id=update.message.message_id)
    except Exception:
        pass


async def set_sticky(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat or chat.type not in (Chat.SUPERGROUP, Chat.GROUP):
        try:
            if update.message:
                await context.bot.delete_message(chat_id=chat.id, message_id=update.message.message_id)
        except Exception:
            pass
        return

    if not await is_user_admin(update, context):
        try:
            if update.message:
                await context.bot.delete_message(chat_id=chat.id, message_id=update.message.message_id)
        except Exception:
            pass
        return

    args_text = " ".join(context.args).strip() if context.args else ""
    reply: Optional[Message] = update.message.reply_to_message if update.message else None

    active_until = compute_active_until(DEFAULT_ACTIVE_MINUTES)

    if args_text:
        sticky_state[chat.id] = {
            "mode": "text",
            "text": args_text,
            "src_chat_id": None,
            "src_msg_id": None,
            "current_msg_id": None,
            "active_until": active_until,
        }
    elif reply:
        sticky_state[chat.id] = {
            "mode": "copy",
            "text": None,
            "src_chat_id": reply.chat_id,
            "src_msg_id": reply.message_id,
            "current_msg_id": None,
            "active_until": active_until,
        }
    else:
        try:
            if update.message:
                await context.bot.delete_message(chat_id=chat.id, message_id=update.message.message_id)
        except Exception:
            pass
        return

    await post_or_repost_sticky(chat.id, context)

    try:
        if update.message:
            await context.bot.delete_message(chat_id=chat.id, message_id=update.message.message_id)
    except Exception:
        pass


async def clear_sticky(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /unsticky:
    מבטל את הסטיקי + מוחק את ההודעה המודבקת מיידית.
    """
    chat = update.effective_chat
    if not chat:
        return

    if not await is_user_admin(update, context):
        try:
            if update.message:
                await context.bot.delete_message(chat_id=chat.id, message_id=update.message.message_id)
        except Exception:
            pass
        return

    st = sticky_state.get(chat.id)
    if st:
        await delete_current_sticky(chat.id, context)
        sticky_state.pop(chat.id, None)

    try:
        if update.message:
            await context.bot.delete_message(chat_id=chat.id, message_id=update.message.message_id)
    except Exception:
        pass


async def set_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /set_time <minutes>
    קובע לכמה זמן (בדקות) הבוט ימשיך "להזיז" את הסטיקי בקבוצה.
    1..20 דקות. ברירת מחדל: 5
    """
    chat = update.effective_chat
    if not chat or chat.type not in (Chat.GROUP, Chat.SUPERGROUP):
        return

    if not await is_user_admin(update, context):
        try:
            if update.message:
                await context.bot.delete_message(chat_id=chat.id, message_id=update.message.message_id)
        except Exception:
            pass
        return

    st = sticky_state.get(chat.id)
    if not st:
        try:
            if update.message:
                await context.bot.delete_message(chat_id=chat.id, message_id=update.message.message_id)
        except Exception:
            pass
        return

    minutes = DEFAULT_ACTIVE_MINUTES
    if context.args:
        try:
            minutes = int(context.args[0])
        except Exception:
            minutes = DEFAULT_ACTIVE_MINUTES

    minutes = clamp_minutes(minutes, MIN_ACTIVE_MINUTES, MAX_ACTIVE_MINUTES)
    st["active_until"] = compute_active_until(minutes)

    try:
        if update.message:
            await context.bot.delete_message(chat_id=chat.id, message_id=update.message.message_id)
    except Exception:
        pass


async def clear_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /clear_media <mins>
    מפעיל מחיקה אוטומטית של תמונות שיישלחו מעתה והלאה.
    כל תמונה תימחק X דקות מרגע שליחתה.
    ברירת מחדל: 5 דקות
    """
    chat = update.effective_chat
    if not chat or chat.type not in (Chat.GROUP, Chat.SUPERGROUP):
        return

    if not await is_user_admin(update, context):
        try:
            if update.message:
                await context.bot.delete_message(chat_id=chat.id, message_id=update.message.message_id)
        except Exception:
            pass
        return

    mins = DEFAULT_MEDIA_DELETE_MINUTES
    if context.args:
        try:
            mins = int(context.args[0])
        except Exception:
            mins = DEFAULT_MEDIA_DELETE_MINUTES

    mins = clamp_minutes(mins, MIN_MEDIA_DELETE_MINUTES, MAX_MEDIA_DELETE_MINUTES)

    media_policy[chat.id] = {
        "enabled": True,
        "delete_after_minutes": mins
    }

    try:
        if update.message:
            await context.bot.delete_message(chat_id=chat.id, message_id=update.message.message_id)
    except Exception:
        pass


async def allow_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /allow_media
    מבטל מחיקה אוטומטית של תמונות.
    """
    chat = update.effective_chat
    if not chat or chat.type not in (Chat.GROUP, Chat.SUPERGROUP):
        return

    if not await is_user_admin(update, context):
        try:
            if update.message:
                await context.bot.delete_message(chat_id=chat.id, message_id=update.message.message_id)
        except Exception:
            pass
        return

    pol = media_policy.get(chat.id)
    if pol:
        pol["enabled"] = False

    try:
        if update.message:
            await context.bot.delete_message(chat_id=chat.id, message_id=update.message.message_id)
    except Exception:
        pass


# ====== Message Handler ======

async def on_any_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    לכל הודעה בקבוצה (לא של הבוט עצמו):
    1) אם הופעלה מדיניות clear_media — כל תמונה שנשלחת תמחק אחרי X דקות.
    2) אם יש סטיקי:
       - אם הטיימר נגמר: נמחק את ההודעה המודבקת ונבטל את הסטיקי.
       - אם הטיימר פעיל: נעשה repost עם דיבאונס.
    """
    chat = update.effective_chat
    msg = update.message
    if not chat or not msg or chat.type not in (Chat.SUPERGROUP, Chat.GROUP):
        return

    bot_user: User = await context.bot.get_me()
    if msg.from_user and msg.from_user.id == bot_user.id:
        return  # לא להגיב לעצמנו

    # ---- (1) Auto-delete photos if enabled ----
    pol = media_policy.get(chat.id)
    if pol and pol.get("enabled"):
        if getattr(msg, "photo", None):
            mins = int(pol.get("delete_after_minutes", DEFAULT_MEDIA_DELETE_MINUTES))
            mins = clamp_minutes(mins, MIN_MEDIA_DELETE_MINUTES, MAX_MEDIA_DELETE_MINUTES)
            await schedule_delete_message(chat.id, msg.message_id, mins * 60, context)

    # ---- (2) Sticky handling ----
    st = sticky_state.get(chat.id)
    if not st:
        return

    # אם הזמן נגמר — למחוק את ההודעה המודבקת ולבטל סטיקי לגמרי
    if not is_sticky_active(st):
        # גם לבטל task ממתין אם קיים
        t = repost_tasks.get(chat.id)
        if t and not t.done():
            t.cancel()
        await delete_current_sticky(chat.id, context)
        sticky_state.pop(chat.id, None)
        return

    # דיבאונס repost
    if chat.id in repost_tasks and not repost_tasks[chat.id].done():
        repost_tasks[chat.id].cancel()

    async def task():
        await asyncio.sleep(DEBOUNCE_SECONDS)

        st2 = sticky_state.get(chat.id)
        if not st2:
            return

        # אם הזמן נגמר בזמן ההמתנה — למחוק ולבטל
        if not is_sticky_active(st2):
            await delete_current_sticky(chat.id, context)
            sticky_state.pop(chat.id, None)
            return

        await post_or_repost_sticky(chat.id, context)

    repost_tasks[chat.id] = asyncio.create_task(task())


# ====== FastAPI lifecycle & routes ======

@api.on_event("startup")
async def on_startup():
    application.add_handler(CommandHandler("at", greet_female))
    application.add_handler(CommandHandler("ata", greet_male))

    application.add_handler(CommandHandler("sticky", set_sticky))
    application.add_handler(CommandHandler("unsticky", clear_sticky))
    application.add_handler(CommandHandler("set_time", set_time))

    application.add_handler(CommandHandler("clear_media", clear_media))
    application.add_handler(CommandHandler("allow_media", allow_media))

    application.add_handler(MessageHandler(filters.ALL, on_any_message))

    await application.initialize()
    await application.start()

    if PUBLIC_URL:
        webhook_url = f"{PUBLIC_URL.rstrip('/')}/webhook/{WEBHOOK_SECRET}"
        await application.bot.set_webhook(
            url=webhook_url,
            allowed_updates=["message", "edited_message", "channel_post", "callback_query"]
        )
        logging.info(f"Webhook set to: {webhook_url}")
    else:
        logging.warning("PUBLIC_URL not set yet; deploy once, set PUBLIC_URL env, and redeploy to set webhook.")


@api.on_event("shutdown")
async def on_shutdown():
    await application.stop()
    await application.shutdown()


@api.get("/")
async def healthcheck():
    return {"ok": True, "service": "telegram-sticky-bot"}


@api.post("/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request):
    if secret != WEBHOOK_SECRET:
        return {"ok": False}

    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return {"ok": True}
