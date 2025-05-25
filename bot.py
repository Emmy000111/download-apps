import os
import logging
import sqlite3
from datetime import datetime, timedelta
from telegram import Update, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)
from yt_dlp import YoutubeDL

# --- CONFIG ---
ADMIN_ID = 1421439076  # Replace with your actual Telegram user ID
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN environment variable not set")

# --- LOGGING ---
logging.basicConfig(
    format='[%(asctime)s] %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- DATABASE ---
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        blocked INTEGER DEFAULT 0,
        last_active TIMESTAMP
    )
''')
conn.commit()

# --- YT-DLP SETTINGS ---
YDL_OPTS = {
    "format": "mp4",
    "outtmpl": "downloads/%(id)s.%(ext)s",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
}

if not os.path.exists("downloads"):
    os.makedirs("downloads")


# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    now = datetime.utcnow()
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, username, blocked, last_active)
        VALUES (?, ?, COALESCE((SELECT blocked FROM users WHERE user_id = ?), 0), ?)
    ''', (user.id, user.username, user.id, now))
    conn.commit()
    await update.message.reply_text("🎬 Send me any video link from TikTok, Twitter, Snapchat, Facebook and I’ll fetch it for you!")


async def download_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    cursor.execute('SELECT blocked FROM users WHERE user_id = ?', (user.id,))
    res = cursor.fetchone()

    if res and res[0] == 1:
        return await update.message.reply_text("🚫 You're blocked from using this bot.")

    url = update.message.text.strip()
    cursor.execute('UPDATE users SET last_active = ? WHERE user_id = ?', (datetime.utcnow(), user.id))
    conn.commit()

    await update.message.reply_text("📥 Downloading your video... Please wait.")

    try:
        with YoutubeDL(YDL_OPTS) as ydl:
            info = ydl.extract_info(url, download=True)
            filepath = ydl.prepare_filename(info)

        with open(filepath, "rb") as file:
            await context.bot.send_video(chat_id=update.effective_chat.id, video=InputFile(file))

        os.remove(filepath)
    except Exception as e:
        logger.error(f"Download error: {e}")
        await update.message.reply_text("❌ Could not download the video. Please check the link and try again.")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("❌ Admin access only.")

    now = datetime.utcnow()
    cursor.execute("SELECT COUNT(*) FROM users")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM users WHERE blocked = 1")
    blocked = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM users WHERE blocked = 0")
    active = cursor.fetchone()[0]

    # Online if active in last 5 minutes
    cursor.execute("SELECT COUNT(*) FROM users WHERE last_active >= ?", (now - timedelta(minutes=5),))
    online = cursor.fetchone()[0]
    offline = active - online

    cursor.execute("SELECT user_id, username FROM users")
    user_rows = cursor.fetchall()
    user_info = "\n".join(
        [f"{uid} — @{uname or 'NoUsername'}" for uid, uname in user_rows]
    ) or "No users yet."

    message = (
        f"📊 <b>User Statistics</b>\n"
        f"👥 Total users: <b>{total}</b>\n"
        f"✅ Active users: <b>{active}</b>\n"
        f"🟢 Online now: <b>{online}</b>\n"
        f"🔘 Offline: <b>{offline}</b>\n"
        f"🚫 Blocked: <b>{blocked}</b>\n\n"
        f"🧾 <b>User List</b>:\n<code>{user_info}</code>"
    )
    await update.message.reply_html(message)


# --- MAIN ---
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), download_video))
    logger.info("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
