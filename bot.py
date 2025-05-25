import os
import logging
import sqlite3
import time
from telegram import Update, InputFile
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from yt_dlp import YoutubeDL

# === CONFIG ===
ADMIN_ID = 1421439076  # <-- Replace with your Telegram ID
DB_PATH = 'users.db'
DOWNLOAD_DIR = 'downloads'
USER_ONLINE_WINDOW = 600  # 10 minutes

# === LOGGING ===
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === YTDLP OPTIONS ===
YDL_OPTS = {
    'format': 'mp4',
    'outtmpl': f'{DOWNLOAD_DIR}/%(id)s.%(ext)s',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
}

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# === DATABASE SETUP ===
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        blocked INTEGER DEFAULT 0,
        last_seen INTEGER
    )
''')
conn.commit()

# === HANDLERS ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    timestamp = int(time.time())
    cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, username, last_seen)
        VALUES (?, ?, ?)
    ''', (user.id, user.username, timestamp))
    cursor.execute('''
        UPDATE users SET last_seen=? WHERE user_id=?
    ''', (timestamp, user.id))
    conn.commit()
    await update.message.reply_text(
        "👋 Send me a video link from TikTok, Twitter, Facebook, or Snapchat and I'll download it for you!"
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Unauthorized access.")
        return

    current_time = int(time.time())
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM users WHERE blocked=1')
    blocked_users = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM users WHERE blocked=0')
    active_users = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM users WHERE last_seen >= ?', (current_time - USER_ONLINE_WINDOW,))
    online_users = cursor.fetchone()[0]
    offline_users = active_users - online_users

    msg = (
        "📊 <b>User Statistics</b>\n\n"
        f"👥 Total Users: <b>{total_users}</b>\n"
        f"✅ Active Users: <b>{active_users}</b>\n"
        f"🟢 Online: <b>{online_users}</b>\n"
        f"🟡 Offline: <b>{offline_users}</b>\n"
        f"⛔ Blocked Users: <b>{blocked_users}</b>"
    )
    await update.message.reply_html(msg)

async def download_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username
    timestamp = int(time.time())

    cursor.execute('SELECT blocked FROM users WHERE user_id=?', (user_id,))
    res = cursor.fetchone()

    if res and res[0] == 1:
        await update.message.reply_text("🚫 You are blocked from using this bot.")
        return

    cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, username, last_seen)
        VALUES (?, ?, ?)
    ''', (user_id, username, timestamp))
    cursor.execute('''
        UPDATE users SET last_seen=? WHERE user_id=?
    ''', (timestamp, user_id))
    conn.commit()

    url = update.message.text.strip()
    await update.message.reply_text("⏳ Downloading... Please wait.")

    try:
        with YoutubeDL(YDL_OPTS) as ydl:
            info = ydl.extract_info(url, download=True)
            filepath = ydl.prepare_filename(info)

        with open(filepath, 'rb') as video_file:
            await context.bot.send_video(chat_id=update.effective_chat.id, video=InputFile(video_file))

        os.remove(filepath)
    except Exception as e:
        logger.error(f"Download error: {e}")
        await update.message.reply_text("❌ Failed to download. Please check the link and try again.")

# === MAIN ===

def main():
    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN:
        print("❌ Error: BOT_TOKEN environment variable not set.")
        return

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), download_video))

    print("✅ Bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()
