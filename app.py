# requirements:
# python-telegram-bot>=21.0

import asyncio
import logging
import os
from typing import Dict, Optional, Tuple

from telegram import Update, Message, Chat, User
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)

logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.getenv("BOT_TOKEN")  # שים את הטוקן שלך כאן או במשתנה סביבה

# נשמור לכל צ'אט את הסטיקי:
# chat_id -> dict with:
#   "mode": "text" | "copy"
#   "text": Optional[str]
#   "src_chat_id": Optional[int]
#   "src_msg_id": Optional[int]
#   "current_msg_id": Optional[int]
sticky_state: Dict[int, Dict] = {}

# דיבאונס כדי לא להציף בשיח ער: chat_id -> asyncio.Task
repost_tasks: Dict[int, asyncio.Task] = {}

DEBOUNCE_SECONDS = 1  # התאמה לפי קצב התעבורה בקבוצה

async def set_sticky(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """פקודת /sticky:
    - אם יש טקסט אחרי הפקודה: קובע סטיקי טקסט.
    - אם עונים עם /sticky על הודעה: קובע סטיקי כהעתקת ההודעה.
    """
    chat = update.effective_chat
    if not chat or chat.type not in (Chat.SUPERGROUP, Chat.GROUP):
        await update.message.reply_text("הפקודה עובדת רק בקבוצות/סופרגרופ.")
        return

    # נאתר מצב: טקסט אחרי הפקודה או תשובה להודעה
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
        await update.message.reply_text("סטיקי עודכן לטקסט הנתון. יפורסם אוטומטית בסוף בכל פעילות.")
    elif reply:
        # נשמור הודעת מקור כדי שנוכל לשכפל אותה כל פעם מחדש
        sticky_state[chat.id] = {
            "mode": "copy",
            "text": None,
            "src_chat_id": reply.chat_id,
            "src_msg_id": reply.message_id,
            "current_msg_id": None,
        }
        await update.message.reply_text("סטיקי עודכן להודעה שעליה ענית. יפורסם אוטומטית בסוף בכל פעילות.")
    else:
        await update.message.reply_text("שלח טקסט אחרי /sticky או ענה עם /sticky על הודעה קיימת.")

    # פרסום ראשוני מידי
    await post_or_repost_sticky(chat.id, context)

async def clear_sticky(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    """עבור כל הודעה בקבוצה – אם יש סטיקי, נמחוק את הקודם ונפרסם חדש בתחתית.
       נתעלם מהודעות הבוט עצמו כדי שלא ניכנס ללולאה.
    """
    chat = update.effective_chat
    msg = update.message
    bot_user: User = await context.bot.get_me()

    if not chat or not msg or chat.type not in (Chat.SUPERGROUP, Chat.GROUP):
        return

    if msg.from_user and msg.from_user.id == bot_user.id:
        return  # לא מגיבים לעצמנו

    if chat.id not in sticky_state:
        return  # אין סטיקי בקבוצה הזו

    # דיבאונס — אם יש כבר טסק בדרך, נבטל ונקבע חדש
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

    # מחיקת הסטיקי הקודם אם קיים
    prev_id = st.get("current_msg_id")
    if prev_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=prev_id)
        except Exception as e:
            logging.debug(f"Delete previous sticky failed (maybe already gone): {e}")

    # שליחה מחדש לפי מצב
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

def main():
    if not BOT_TOKEN:
        raise RuntimeError("Please set BOT_TOKEN in environment.")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("sticky", set_sticky))
    app.add_handler(CommandHandler("unsticky", clear_sticky))
    app.add_handler(MessageHandler(filters.ALL, on_any_message))

    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
