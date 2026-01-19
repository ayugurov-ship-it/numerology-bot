import os
import json
import asyncio
import threading
from flask import Flask, request

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_PATH = "/webhook"
BASE_URL = "https://numerology-bot-m48t.onrender.com"

bot = Bot(token=TOKEN)
dp = Dispatcher()

app = Flask(__name__)

# =======================
# AIROGRAM HANDLERS
# =======================

@dp.message(Command("start"))
async def start_cmd(m: types.Message):
    await m.answer("Привет 👋\nВведите дату рождения в формате ДД.ММ.ГГГГ")

@dp.message(Command("help"))
async def help_cmd(m: types.Message):
    await m.answer("Введите дату рождения в формате ДД.ММ.ГГГГ")

@dp.message()
async def fallback(m: types.Message):
    await m.answer("Введите дату рождения в формате ДД.ММ.ГГГГ")

# =======================
# EVENT LOOP (IMPORTANT)
# =======================

loop = asyncio.new_event_loop()

def start_loop():
    asyncio.set_event_loop(loop)
    loop.run_forever()

threading.Thread(target=start_loop, daemon=True).start()

# =======================
# FLASK ROUTES
# =======================

@app.route("/")
def home():
    return "OK"

@app.route("/ping")
def ping():
    return "pong"

@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    if request.headers.get("content-type") != "application/json":
        return "unsupported", 415

    data = request.get_json()
    update = types.Update(**data)

    asyncio.run_coroutine_threadsafe(
        dp.feed_update(bot, update),
        loop
    )

    return "ok"

# =======================
# STARTUP
# =======================

def set_webhook():
    url = BASE_URL + WEBHOOK_PATH
    result = asyncio.run(bot.set_webhook(url))
    print("Webhook set:", result)

if __name__ == "__main__":
    print("Starting bot...")
    set_webhook()
    app.run(host="0.0.0.0", port=10000)