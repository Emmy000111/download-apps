import os
import logging
import sqlite3
from telegram import Update, InputFile
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from yt_dlp import YoutubeDL

# --- Config ---
ADMIN_ID = 1421439076  # Put your Telegram user ID here

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# YTDLP options
YDL_OPTS = {
    'format': 'mp4',
    'outtmpl': 'downloads/%(id)s.%(ext)s',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
}

if not os.path.exists('downloads'):
    os.makedirs('downloads')

# SQLite DB setup
conn = sqlite3.connect('users.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, 
        username TEXT, 
        blocked INTEGER DEFAULT 0
    )
''')
conn.commit()

# --- Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    cursor.execute(
        'INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)',
        (user.id, user.username)
    )
    conn.commit()
    await update.message.reply_text(
        "Welcome! Send me a video link from TikTok, Twitter, Snapchat, Facebook, and I'll download it for you."
    )

async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Unauthorized: Admins only.")
        return
    cursor.execute('SELECT user_id, username, blocked FROM users')
    rows = cursor.fetchall()
    if not rows:
        await update.message.reply_text("No users found.")
        return
    msg = "Users:\n"
    for user_id, username, blocked in rows:
        status = "Blocked" if blocked else "Active"
        msg += f"{user_id} — @{username or 'NoUsername'} — {status}\n"
    await update.message.reply_text(msg)

async def block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Unauthorized: Admins only.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /block <user_id>")
        return
    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("User ID must be a number.")
        return
    cursor.execute('UPDATE users SET blocked=1 WHERE user_id=?', (user_id,))
    conn.commit()
    await update.message.reply_text(f"User {user_id} blocked.")

async def unblock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Unauthorized: Admins only.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /unblock <user_id>")
        return
    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("User ID must be a number.")
        return
    cursor.execute('UPDATE users SET blocked=0 WHERE user_id=?', (user_id,))
    conn.commit()
    await update.message.reply_text(f"User {user_id} unblocked.")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Unauthorized: Admins only.")
        return
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM users WHERE blocked=1')
    blocked_users = cursor.fetchone()[0]
    active_users = total_users - blocked_users
    msg = (
        f"User stats:\n"
        f"Total users: {total_users}\n"
        f"Active users: {active_users}\n"
        f"Blocked users: {blocked_users}"
    )
    await update.message.reply_text(msg)

async def download_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # Admin can always use the bot regardless of block status
    if user_id != ADMIN_ID:
        cursor.execute('SELECT blocked FROM users WHERE user_id=?', (user_id,))
        res = cursor.fetchone()
        if res and res[0] == 1:
            await update.message.reply_text("You are blocked from using this bot.")
            return

    url = update.message.text.strip()
    await update.message.reply_text("Downloading your video... Please wait.")

    try:
        with YoutubeDL(YDL_OPTS) as ydl:
            info = ydl.extract_info(url, download=True)
            filepath = ydl.prepare_filename(info)

        with open(filepath, 'rb') as video_file:
            await context.bot.send_video(chat_id=update.effective_chat.id, video=InputFile(video_file))

        os.remove(filepath)
    except Exception as e:
        logger.error(f"Error downloading video: {e}")
        await update.message.reply_text("Sorry, I couldn't download the video. Please check the link and try again.")

# --- Main ---

def main():
    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN:
        print("Error: BOT_TOKEN environment variable not set")
        return

    app = ApplicationBuilder().token(TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("users", users))
    app.add_handler(CommandHandler("block", block))
    app.add_handler(CommandHandler("unblock", unblock))
    app.add_handler(CommandHandler("stats", stats))

    # Handle all text messages (video download)
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), download_video))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
