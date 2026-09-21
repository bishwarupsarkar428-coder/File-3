"""Telegram file share bot for @TG_HINDI_ANIME69.

Admins send files to the bot -> the bot returns a shareable link.
Anyone who opens the link receives the files.
"""
import asyncio
import logging
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from telegram import Update
from telegram.error import RetryAfter, TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from db import Database

try:  # optional: load variables from a local .env file
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

GREETING = "Hello, I am a file share bot of @TG_HINDI_ANIME69"
CODE_RE = re.compile(r"[A-Za-z0-9_-]{6,64}")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("file-share-bot")


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
def parse_admin_ids(raw: str) -> set:
    ids = set()
    for part in re.split(r"[,\s]+", raw or ""):
        if part.lstrip("-").isdigit():
            ids.add(int(part))
    return ids


ADMIN_IDS = parse_admin_ids(os.getenv("ADMIN_IDS", ""))
DATA_DIR = os.getenv("DATA_DIR", "data")
DB_PATH = os.path.join(DATA_DIR, "files.db")


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# --------------------------------------------------------------------------- #
# Health-check server (needed by Render / Koyeb / Railway web services)
# --------------------------------------------------------------------------- #
class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"OK"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):  # keep logs clean
        pass


def start_health_server():
    port = os.getenv("PORT")
    if not port:
        return
    try:
        server = ThreadingHTTPServer(("0.0.0.0", int(port)), _HealthHandler)
    except (ValueError, OSError) as exc:
        log.warning("Could not start health server: %s", exc)
        return
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log.info("Health server listening on port %s", port)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def extract_media(message):
    """Return (file_type, file_id) for a message, or None."""
    # Animations also carry a `document`, so check them first.
    if message.animation:
        return "animation", message.animation.file_id
    if message.document:
        return "document", message.document.file_id
    if message.video:
        return "video", message.video.file_id
    if message.audio:
        return "audio", message.audio.file_id
    if message.voice:
        return "voice", message.voice.file_id
    if message.video_note:
        return "video_note", message.video_note.file_id
    if message.photo:
        return "photo", message.photo[-1].file_id
    return None


async def send_one(bot, chat_id, file_type, file_id, caption):
    """Send a stored file, retrying once if Telegram asks us to slow down."""
    kwargs = {file_type: file_id}
    if caption and file_type != "video_note":
        kwargs["caption"] = caption
    method = getattr(bot, f"send_{file_type}")
    for attempt in range(2):
        try:
            await method(chat_id=chat_id, **kwargs)
            return True
        except RetryAfter as exc:
            if attempt == 1:
                return False
            delay = getattr(exc.retry_after, "total_seconds", lambda: exc.retry_after)()
            await asyncio.sleep(delay + 1)
        except TelegramError as exc:
            log.warning("Could not send %s: %s", file_type, exc)
            return False
    return False


def make_link(context: ContextTypes.DEFAULT_TYPE, code: str) -> str:
    return f"https://t.me/{context.bot.username}?start={code}"


# --------------------------------------------------------------------------- #
# Handlers
# --------------------------------------------------------------------------- #
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    await message.reply_text(GREETING)

    if not context.args:
        return

    code = context.args[0]
    items = []
    if CODE_RE.fullmatch(code):
        items = context.application.bot_data["db"].get_files(code)
    if not items:
        await message.reply_text("This link is invalid or has expired.")
        return

    chat_id = update.effective_chat.id
    for file_type, file_id, caption in items:
        await send_one(context.bot, chat_id, file_type, file_id, caption)
        await asyncio.sleep(0.05)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = GREETING + "\n\nOpen a share link to receive files."
    if is_admin(update.effective_user.id):
        text += (
            "\n\nAdmin commands:\n"
            "• Send me any file to get a share link\n"
            "• /batch – start collecting several files into one link\n"
            "• /done – finish the batch and get the link\n"
            "• /cancel – cancel the current batch\n"
            "• /id – show your Telegram user ID"
        )
    await update.effective_message.reply_text(text)


async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        f"Your Telegram ID: {update.effective_user.id}"
    )


async def batch_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not is_admin(update.effective_user.id):
        await message.reply_text("Only admins can use this command.")
        return
    context.user_data["batch"] = []
    await message.reply_text(
        "Batch started. Send the files now, then send /done to get one link "
        "(or /cancel to abort)."
    )


async def done_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not is_admin(update.effective_user.id):
        await message.reply_text("Only admins can use this command.")
        return
    batch = context.user_data.get("batch")
    if not batch:
        await message.reply_text("No files in the batch. Use /batch first.")
        return
    code = context.application.bot_data["db"].add_files(batch)
    context.user_data["batch"] = None
    await message.reply_text(
        f"Link for {len(batch)} file(s):\n{make_link(context, code)}"
    )


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("Only admins can use this command.")
        return
    context.user_data["batch"] = None
    await update.effective_message.reply_text("Batch cancelled.")


async def on_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not is_admin(update.effective_user.id):
        await message.reply_text(GREETING)
        return

    media = extract_media(message)
    if media is None:
        return
    file_type, file_id = media
    item = (file_type, file_id, message.caption)

    batch = context.user_data.get("batch")
    if batch is not None:
        batch.append(item)
        await message.reply_text(
            f"Added ({len(batch)} in batch). Send more or /done."
        )
        return

    code = context.application.bot_data["db"].add_files([item])
    await message.reply_text(f"Here is your link:\n{make_link(context, code)}")


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(GREETING)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.error("Unhandled error", exc_info=context.error)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def main():
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            "BOT_TOKEN is not set. Get one from @BotFather and set it as an "
            "environment variable (see README.md)."
        )
    if not ADMIN_IDS:
        log.warning(
            "ADMIN_IDS is empty - nobody can upload files yet. "
            "Send /id to the bot and set ADMIN_IDS."
        )

    application = Application.builder().token(token).build()
    application.bot_data["db"] = Database(DB_PATH)

    media_filter = (
        filters.ANIMATION
        | filters.Document.ALL
        | filters.VIDEO
        | filters.AUDIO
        | filters.VOICE
        | filters.VIDEO_NOTE
        | filters.PHOTO
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("id", id_cmd))
    application.add_handler(CommandHandler("batch", batch_cmd))
    application.add_handler(CommandHandler("done", done_cmd))
    application.add_handler(CommandHandler("cancel", cancel_cmd))
    application.add_handler(MessageHandler(media_filter & ~filters.COMMAND, on_media))
    application.add_handler(
        MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, on_text)
    )
    application.add_error_handler(on_error)

    start_health_server()
    log.info("Bot is starting...")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
