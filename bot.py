import os
import sqlite3
import logging
from datetime import datetime, timedelta
from telegram import Update, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
)
from yt_dlp import YoutubeDL

# --- CONFIGURATION ---
ADMIN_ID = 1421439076  # Replace with your Telegram ID
STATS_COOLDOWN_HOURS = 24

# --- LOGGING ---
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- DB SETUP ---
conn = sqlite3.connect('users.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        blocked INTEGER DEFAULT 0,
        last_online TEXT
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS stats_log (
        key TEXT PRIMARY KEY,
        last_sent TEXT
    )
''')
conn.commit()

# --- YTDLP CONFIG ---
YDL_OPTS = {
    'format': 'mp4',
    'outtmpl': 'downloads/%(id)s.%(ext)s',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
}

if not os.path.exists('downloads'):
    os.makedirs('downloads')


# --- COMMAND HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    cursor.execute(
        'INSERT OR IGNORE INTO users (user_id, username, blocked, last_online) VALUES (?, ?, 0, ?)',
        (user.id, user.username, datetime.utcnow().isoformat())
    )
    cursor.execute(
        'UPDATE users SET last_online=? WHERE user_id=?',
        (datetime.utcnow().isoformat(), user.id)
    )
    conn.commit()
    await update.message.reply_text("Send me a video link from TikTok, Twitter, Facebook, etc. I’ll download it for you!")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    cursor.execute("SELECT last_sent FROM stats_log WHERE key='last'")
    result = cursor.fetchone()
    now = datetime.utcnow()

    if result:
        last_sent = datetime.fromisoformat(result[0])
        if now - last_sent < timedelta(hours=STATS_COOLDOWN_HOURS):
            await update.message.reply_text("Stats were sent recently. Try again later.")
            return
        cursor.execute("UPDATE stats_log SET last_sent=? WHERE key='last'", (now.isoformat(),))
    else:
        cursor.execute("INSERT INTO stats_log (key, last_sent) VALUES ('last', ?)", (now.isoformat(),))

    conn.commit()

    cursor.execute("SELECT COUNT(*) FROM users")
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users WHERE blocked=1")
    blocked = cursor.fetchone()[0]
    active = total - blocked

    # Estimate online users: active in the last 10 minutes
    cursor.execute("SELECT COUNT(*) FROM users WHERE last_online >= ?", ((now - timedelta(minutes=10)).isoformat(),))
    online = cursor.fetchone()[0]
    offline = active - online

    message = (
        f"📊 User Stats:\n"
        f"👥 Total: {total}\n"
        f"✅ Active: {active}\n"
        f"🚫 Blocked: {blocked}\n"
        f"🟢 Online: {online}\n"
        f"🔴 Offline: {offline}"
    )
    await update.message.reply_text(message)


async def download_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Check blocked
    cursor.execute("SELECT blocked FROM users WHERE user_id=?", (user.id,))
    result = cursor.fetchone()
    if result and result[0] == 1:
        await update.message.reply_text("⛔ You are blocked from using this bot.")
        return

    # Update user info
    cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, username, blocked, last_online)
        VALUES (?, ?, 0, ?)
    ''', (user.id, user.username, datetime.utcnow().isoformat()))
    cursor.execute("UPDATE users SET last_online=? WHERE user_id=?", (datetime.utcnow().isoformat(), user.id))
    conn.commit()

    url = update.message.text.strip()
    await update.message.reply_text("⏳ Downloading... Please wait.")

    try:
        with YoutubeDL(YDL_OPTS) as ydl:
            info = ydl.extract_info(url, download=True)
            filepath = ydl.prepare_filename(info)

        with open(filepath, 'rb') as f:
            await context.bot.send_video(chat_id=update.effective_chat.id, video=InputFile(f))

        os.remove(filepath)
    except Exception as e:
        logging.error(f"Download failed: {e}")
        await update.message.reply_text("⚠️ Failed to download. Check the link and try again.")


# --- MAIN ---

def main():
    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN:
        print("❌ BOT_TOKEN not set.")
        return

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_video))

    print("🚀 Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
