import os
import time
import asyncio
import logging
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

DEBOUNCE_SECONDS = float(os.environ.get("DEBOUNCE_SECONDS", "1"))
AUTO_DELETE_SECONDS = int(os.environ.get("AUTO_DELETE_SECONDS", "0"))

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
