import os
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
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]     # מחרוזת אקראית לנתיב ה-webhook (למשל: xYz123)
PUBLIC_URL = os.environ.get("PUBLIC_URL")         # ימולא אחרי הדיפלוי הראשון (למשל: https://my-bot.onrender.com)

DEBOUNCE_SECONDS = float(os.environ.get("DEBOUNCE_SECONDS", "0.6"))

# --------------------
# מצב זיכרון לסטיקי
# --------------------
# מבנה:
# chat_id -> {
#   "mode": "text" | "copy",
#   "text": Optional[str],
#   "src_chat_id": Optional[int],
#   "src_msg_id": Optional[int],
#   "current_msg_id": Optional[int],
# }
sticky_state: Dict[int, Dict] = {}
repost_tasks: Dict[int, asyncio.Task] = {}

# --------------------
# FastAPI + Telegram
# --------------------
api = FastAPI()
application = Application.builder().token(BOT_TOKEN).build()


# ====== Handlers ======

async def set_sticky(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /sticky <טקסט>  -> יוצר סטיקי מטקסט
    או: לענות עם /sticky על הודעה -> יוצר סטיקי כהעתקת ההודעה (כולל מדיה)
    """
    chat = update.effective_chat
    if not chat or chat.type not in (Chat.SUPERGROUP, Chat.GROUP):
        await update.message.reply_text("הפקודה עובדת רק בקבוצות/סופרגרופ.")
        return

    args_text = " ".join(context.args).strip() if context.args else ""
    reply: Optional[Message] = update.message.reply_to_message if update.message else None

    if args_text:
        sticky_state[chat.id] = {
            "mode": "text",
            "text": args_text,
            "src_chat_id": None,
            "src_msg_id": None,
            "current_msg_id": None,
        }
        await update.message.reply_text("סטיקי עודכן לטקסט הנתון. יפורסם תמיד אחרון.")
    elif reply:
        sticky_state[chat.id] = {
            "mode": "copy",
            "text": None,
            "src_chat_id": reply.chat_id,
            "src_msg_id": reply.message_id,
            "current_msg_id": None,
        }
        await update.message.reply_text("סטיקי עודכן להודעה שעליה ענית. יפורסם תמיד אחרון.")
    else:
        await update.message.reply_text("שלח טקסט אחרי /sticky או ענה עם /sticky על הודעה קיימת.")
        return

    # פרסום ראשוני מיד
    await post_or_repost_sticky(chat.id, context)


async def clear_sticky(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ /unsticky -> מבטל סטיקי ומוחק את ההודעה הנוכחית של הסטיקי אם קיימת """
    chat = update.effective_chat
    if not chat:
        return
    st = sticky_state.pop(chat.id, None)
    if st and st.get("current_msg_id"):
        try:
            await context.bot.delete_message(chat_id=chat.id, message_id=st["current_msg_id"])
        except Exception as e:
            logging.warning(f"Failed to delete current sticky: {e}")
    await update.message.reply_text("הסטיקי בוטל.")


async def on_any_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    לכל הודעה בקבוצה (לא של הבוט עצמו):
    נמחק את הסטיקי הקודם ונפרסם אותו מחדש כדי שיהיה בתחתית.
    עם דיבאונס כדי לא להציף בקבוצות פעילות.
    """
    chat = update.effective_chat
    msg = update.message
    if not chat or not msg or chat.type not in (Chat.SUPERGROUP, Chat.GROUP):
        return

    bot_user: User = await context.bot.get_me()
    if msg.from_user and msg.from_user.id == bot_user.id:
        return  # לא להגיב לעצמנו

    if chat.id not in sticky_state:
        return  # אין סטיקי בקבוצה הזו

    # דיבאונס
    if chat.id in repost_tasks and not repost_tasks[chat.id].done():
        repost_tasks[chat.id].cancel()

    async def task():
        await asyncio.sleep(DEBOUNCE_SECONDS)
        await post_or_repost_sticky(chat.id, context)

    repost_tasks[chat.id] = asyncio.create_task(task())


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


# ====== FastAPI lifecycle & routes ======

@api.on_event("startup")
async def on_startup():
    # לרשום handlers
    application.add_handler(CommandHandler("sticky", set_sticky))
    application.add_handler(CommandHandler("unsticky", clear_sticky))
    application.add_handler(MessageHandler(filters.ALL, on_any_message))

    # להפעיל את אפליקציית הטלגרם (ללא polling)
    await application.initialize()
    await application.start()

    # אם PUBLIC_URL קיים — נגדיר webhook אוטומטית
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
