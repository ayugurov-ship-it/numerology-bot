import os
import json
import asyncio
import requests
import aiohttp
from pathlib import Path
from flask import Flask, request
from threading import Thread

from aiogram import Bot, Dispatcher, Router, types
from aiogram.filters import CommandStart
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    Message
)

# =====================
# CONFIG
# =====================

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROK_API_KEY = os.getenv("GROK_API_KEY")
BASE_URL = os.getenv("BASE_URL")

MODEL_NAME = "llama-3.1-8b-instant"
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = BASE_URL + WEBHOOK_PATH

SYSTEM_PROMPT = """
Ты — профессиональный нумеролог-консультант с 20-летним опытом.

Твоя задача:
— рассчитывать нумерологические значения по дате рождения;
— объяснять результаты простым и понятным языком;
— давать практические рекомендации;
— писать дружелюбно, уверенно, без мистического фанатизма;
— избегать запугивания и категоричных утверждений.

Формат ответа:
1. Краткий вывод
2. Основные числа
3. Расшифровка
4. Сильные стороны
5. Зоны роста
6. Совет на год

Язык: русский.
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
# GROK API
# =====================

async def ask_grok(prompt: str) -> str:
    url = "https://api.groq.com/openai/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {GROK_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers, timeout=60) as r:
            data = await r.json()
            return data["choices"][0]["message"]["content"]

# =====================
# BOT INIT
# =====================

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# =====================
# KEYBOARD
# =====================

def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🧮 Расчет по дате")],
            [KeyboardButton(text="📊 Совместимость")],
            [KeyboardButton(text="🔮 Прогноз на год")],
            [KeyboardButton(text="ℹ️ Помощь")]
        ],
        resize_keyboard=True
    )
# =====================
# HANDLERS
# =====================

@router.message(CommandStart())
async def start(m: Message):
    await m.answer(
        "Привет! Я нумерологический бот 🔢\nВыбери действие:",
        reply_markup=main_menu()
    )

@router.message(lambda m: m.text in ["🧮 Расчет по дате", "📊 Совместимость", "🔮 Прогноз на год", "ℹ️ Помощь"])
async def menu_handler(m: Message):
    if m.text == "🧮 Расчет по дате":
        await m.answer("Введите дату рождения в формате ДД.ММ.ГГГГ")

    elif m.text == "📊 Совместимость":
        await m.answer("Введите две даты через пробел\nПример: 12.03.1995 10.05.1993")

    elif m.text == "🔮 Прогноз на год":
        await m.answer("Введите дату рождения для прогноза на год")

    elif m.text == "ℹ️ Помощь":
        await m.answer("Я рассчитываю нумерологию, совместимость и прогнозы 🔮")

@router.message(lambda m: m.text.count(".") == 2 and len(m.text) == 10)
async def numerology(m: Message):
    users[str(m.from_user.id)] = m.text
    save_users(users)

    await m.answer("🔮 Анализирую дату...")

    result = await ask_grok(f"Дата рождения: {m.text}")
    await m.answer(result, reply_markup=main_menu())

@router.message(lambda m: len(m.text.split()) == 2 and "." in m.text)
async def compatibility(m: Message):
    d1, d2 = m.text.split()
    await m.answer("💞 Анализирую совместимость...")

    result = await ask_grok(f"Совместимость дат: {d1} и {d2}")
    await m.answer(result, reply_markup=main_menu())

# =====================
# FLASK WEBHOOK SERVER
# =====================

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running"

@app.route("/ping")
def ping():
    return "pong"

@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    data = request.get_json()
    update = types.Update(**data)

    asyncio.run_coroutine_threadsafe(
        dp.feed_update(bot, update),
        loop
    )
    return "ok"

# =====================
# EVENT LOOP
# =====================

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# =====================
# WEBHOOK SETUP
# =====================

def set_webhook():
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
    requests.post(url, json={"url": WEBHOOK_URL})
    print("Webhook set:", WEBHOOK_URL)

# =====================
# START
# =====================

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    print("Starting bot...")

    set_webhook()

    Thread(target=run_flask, daemon=True).start()

    print("Bot started")
    loop.run_forever()
