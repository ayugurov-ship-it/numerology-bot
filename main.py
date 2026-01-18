import os
import json
import requests
from pathlib import Path
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

SYSTEM_PROMPT = """
Ты профессиональный нумеролог и психолог.
Пиши на русском языке.
Обращайся к пользователю по имени.
Давай структурированные ответы с эмодзи.
"""

BASE_URL = os.getenv("BASE_URL")  # Render даст домен
WEBHOOK_PATH = "/webhook"

# =====================
# USERS STORAGE
# =====================

USERS_FILE = Path("users.json")

def load_users():
    if USERS_FILE.exists():
        return json.loads(USERS_FILE.read_text())
    return {}

def save_users(data):
    USERS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))

users = load_users()

# =====================
# GROQ
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
            {"role": "user", "content": f"Имя пользователя: {name}\n\n{prompt}"}
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
            [KeyboardButton(text="🌙 Гороскоп на сегодня")],
            [KeyboardButton(text="💞 Совместимость")],
            [KeyboardButton(text="🔮 Моя дата рождения")]
        ],
        resize_keyboard=True
    )

@dp.message(CommandStart())
async def start(m: types.Message):
    await m.answer("Привет! Введи дату рождения в формате ДД.ММ.ГГГГ", reply_markup=keyboard())

@dp.message(lambda m: m.text == "🔮 Моя дата рождения")
async def my_date(m: types.Message):
    uid = str(m.from_user.id)
    if uid in users:
        await m.answer(f"Твоя дата рождения: {users[uid]}")
    else:
        await m.answer("Ты ещё не вводил дату рождения.")

@dp.message(lambda m: "." in m.text)
async def numerology(m: types.Message):
    users[str(m.from_user.id)] = m.text
    save_users(users)

    await m.answer("🔮 Анализирую...")
    result = ask_groq(f"Сделай нумерологический разбор для даты {m.text}", m.from_user.first_name)
    await m.answer(result)

# =====================
# FLASK
# =====================

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running"

@app.route(WEBHOOK_PATH, methods=["POST"])
async def webhook():
    update = types.Update(**request.json)
    await dp.feed_update(bot, update)
    return "ok"

# =====================
# WEBHOOK SETUP
# =====================

def set_webhook():
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
    webhook_url = BASE_URL + WEBHOOK_PATH
    requests.post(url, json={"url": webhook_url})
    print("Webhook set:", webhook_url)

# =====================
# START
# =====================

if __name__ == "__main__":
    set_webhook()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
