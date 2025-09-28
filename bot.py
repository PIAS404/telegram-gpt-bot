# bot.py
import os
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI

# load env
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_TOKEN or not OPENAI_API_KEY:
    raise RuntimeError("Set TELEGRAM_BOT_TOKEN and OPENAI_API_KEY in .env")

# init clients
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# in-memory storages (dev). Production -> use DB (sqlite/redis)
chat_histories = {}   # chat_id -> list of {"role":"user"/"assistant", "content": "..."}
system_prompts = {}   # chat_id -> custom system prompt (if user set)

# logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# helpers
def add_user_message(chat_id: int, text: str):
    chat_histories.setdefault(chat_id, [])
    chat_histories[chat_id].append({"role": "user", "content": text})
    # keep last 12 messages to limit tokens
    chat_histories[chat_id] = chat_histories[chat_id][-12:]

def add_assistant_message(chat_id: int, text: str):
    chat_histories.setdefault(chat_id, [])
    chat_histories[chat_id].append({"role": "assistant", "content": text})
    chat_histories[chat_id] = chat_histories[chat_id][-12:]

def build_messages(chat_id: int, user_text: str):
    msgs = []
    # optional system prompt
    if chat_id in system_prompts:
        msgs.append({"role": "system", "content": system_prompts[chat_id]})
    # include recent history
    history = chat_histories.get(chat_id, [])
    msgs.extend(history)
    # current user message
    msgs.append({"role": "user", "content": user_text})
    return msgs

# command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Salam! Ami ChatGPT-bot. /help dekhো commands gula jannar jonno."
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (
        "/start - greeting\n"
        "/help - this help\n"
        "/setprompt <text> - set system prompt for this chat (e.g. 'You are a helpful assistant...')\n"
        "/clearprompt - remove system prompt\n"
        "/clear - clear conversation history\n\n"
        "Just send a message to chat with GPT."
    )
    await update.message.reply_text(txt)

async def setprompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args
    if not args:
        await update.message.reply_text("Use: /setprompt <your instruction>")
        return
    prompt = " ".join(args)
    system_prompts[chat_id] = prompt
    await update.message.reply_text("System prompt set for this chat.")

async def clearprompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in system_prompts:
        del system_prompts[chat_id]
    await update.message.reply_text("System prompt removed (if any).")

async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat_histories.pop(chat_id, None)
    await update.message.reply_text("Conversation history cleared.")

# message handler -> forward to OpenAI
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_text = update.message.text
    await update.message.chat.send_action("typing")

    # add to history
    add_user_message(chat_id, user_text)

    # build messages for API (role style used by chat completions)
    messages = build_messages(chat_id, user_text)

    try:
        # call OpenAI Chat Completions (adjust model to your account & cost)
        resp = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=800,
            temperature=0.6
        )
        # extract reply (standard: choices[0].message.content)
        reply = resp.choices[0].message.content.strip()
    except Exception as e:
        logger.exception("OpenAI error")
        reply = "দুঃখিত, সার্ভার error হলো: " + str(e)

    # save assistant reply to history and send back
    add_assistant_message(chat_id, reply)
    # Telegram message (split if too long)
    for chunk in [reply[i:i+3900] for i in range(0, len(reply), 3900)]:
        await update.message.reply_text(chunk)

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("setprompt", setprompt))
    app.add_handler(CommandHandler("clearprompt", clearprompt))
    app.add_handler(CommandHandler("clear", clear_history))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot is running (polling). Ctrl-C to stop.")
    app.run_polling()

if __name__ == "__main__":
    main()
