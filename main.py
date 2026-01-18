import os
import json
import time
import requests
from pathlib import Path
from flask import Flask, request, abort

import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# =====================
# CONFIG
# =====================

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

MODEL_NAME = "llama-3.1-8b-instant"

BASE_URL = "https://numerology-bot-m48t.onrender.com"
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = BASE_URL + WEBHOOK_PATH

SYSTEM_PROMPT = """
Ты профессиональный нумеролог и психолог.
Пиши на русском языке.
Обращайся к пользователю по имени.
Давай структурированные ответы с эмодзи.
"""

# =====================
# USERS STORAGE
# =====================

USERS_FILE = Path("users.json")

def load_users():
    if USERS_FILE.exists():
        return json.loads(USERS_FILE.read_text(encoding="utf-8"))
    return {}

def save_users(data):
    USERS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

users = load_users()

# =====================
# AI
# =====================

def ask_groq(prompt, name):
    url = "https://api.groq.com/openai/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Имя: {name}\n{prompt}"}
        ]
    }

    r = requests.post(url, headers=headers, json=data, timeout=60)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

# =====================
# BOT
# =====================

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

def keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔮 Моя дата рождения")],
            [KeyboardButton(text="💞 Совместимость")],
            [KeyboardButton(text="ℹ️ Помощь")]
        ],
        resize_keyboard=True
    )

@dp.message(CommandStart())
async def start(m: types.Message):
    await m.answer(
        "Привет 👋\nВведи дату рождения в формате:\nДД.ММ.ГГГГ",
        reply_markup=keyboard()
    )

@dp.message(lambda m: m.text and "." in m.text)
async def numerology(m: types.Message):
    users[str(m.from_user.id)] = m.text
    save_users(users)

    await m.answer("🔮 Считаю твою нумерологию...")

    result = ask_groq(
        f"Сделай подробный нумерологический разбор для даты {m.text}",
        m.from_user.first_name
    )

    await m.answer(result)

@dp.message()
async def fallback(m: types.Message):
    await m.answer("Напиши дату рождения в формате ДД.ММ.ГГГГ")

# =====================
# FLASK
# =====================

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is alive"

@app.route("/ping")
def ping():
    return "pong"

@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    if request.headers.get("content-type") != "application/json":
        abort(403)

    data = request.get_json()
    update = types.Update(**data)

    loop = asyncio.get_event_loop()
    loop.create_task(dp.feed_update(bot, update))

    return "ok"

# =====================
# WEBHOOK SETUP
# =====================

def set_webhook():
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
    r = requests.post(url, json={"url": WEBHOOK_URL})
    print("Webhook set:", r.text)

# =====================
# START
# =====================

if __name__ == "__main__":
    print("Starting bot...")

    set_webhook()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)