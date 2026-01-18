import os
import json
import time
import requests
import asyncio
from pathlib import Path
from threading import Thread
from flask import Flask, request

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
# AI (Groq)
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
            [KeyboardButton(text="ℹ️ Помощь")],
        ],
        resize_keyboard=True
    )

@dp.message(CommandStart())
async def start(m: types.Message):
    await m.answer(
        "Привет 👋\n\nВведи дату рождения в формате:\n\n📅 ДД.ММ.ГГГГ",
        reply_markup=keyboard()
    )

@dp.message(lambda m: m.text == "ℹ️ Помощь")
async def help_cmd(m: types.Message):
    await m.answer("Введите дату рождения в формате ДД.ММ.ГГГГ")

@dp.message(lambda m: "." in m.text and len(m.text) >= 8)
async def numerology(m: types.Message):
    users[str(m.from_user.id)] = m.text
    save_users(users)

    await m.answer("🔮 Считаю нумерологический разбор...")

    result = ask_groq(
        f"Сделай подробный нумерологический разбор по дате {m.text}",
        m.from_user.first_name or "друг"
    )

    await m.answer(result)

# =====================
# FLASK
# =====================

app = Flask(__name__)

@app.route("/")
def home():
    return "🟢 Bot is alive"

@app.route("/ping")
def ping():
    return "pong"

@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    update = types.Update(**request.json)
    asyncio.run(dp.feed_update(bot, update))
    return "ok"

# =====================
# KEEP ALIVE
# =====================

def keep_alive():
    while True:
        try:
            requests.get(BASE_URL + "/ping", timeout=10)
        except:
            pass
        time.sleep(240)

# =====================
# WEBHOOK SETUP
# =====================

def set_webhook():
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
    r = requests.post(url, json={"url": WEBHOOK_URL})
    print("Webhook:", r.text)

# =====================
# START
# =====================

if __name__ == "__main__":
    Thread(target=keep_alive, daemon=True).start()
    set_webhook()

    port = int(os.environ.get("PORT", 8080))
    print("Running on port", port)
    print("Webhook URL:", WEBHOOK_URL)

    app.run(host="0.0.0.0", port=port)