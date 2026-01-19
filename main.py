import os
import json
import asyncio
import threading
from flask import Flask, request

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# ========================
# CONFIG
# ========================

BOT_TOKEN = os.getenv("BOT_TOKEN") or "ВСТАВЬ_ТОКЕН"
BASE_URL = "https://numerology-bot-m48t.onrender.com"
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = BASE_URL + WEBHOOK_PATH

PORT = int(os.getenv("PORT", 10000))

# ========================
# BOT INIT
# ========================

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ========================
# HANDLERS
# ========================

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("Привет 👋\nВведи дату рождения в формате ДД.ММ.ГГГГ")

@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    await message.answer("Введите дату рождения в формате ДД.ММ.ГГГГ")

@dp.message()
async def fallback(message: types.Message):
    await message.answer("Введите дату рождения в формате ДД.ММ.ГГГГ")

# ========================
# EVENT LOOP (GLOBAL)
# ========================

loop = asyncio.new_event_loop()

def start_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

threading.Thread(target=start_loop, args=(loop,), daemon=True).start()

# ========================
# FLASK
# ========================

app = Flask(__name__)

@app.route("/")
def home():
    return "OK"

@app.route("/ping")
def ping():
    return "pong"

@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True)
        update = types.Update(**data)

        asyncio.run_coroutine_threadsafe(
            dp.feed_update(bot, update),
            loop
        )

    except Exception as e:
        print("WEBHOOK ERROR:", e)

    return "ok"

# ========================
# STARTUP
# ========================

async def on_startup():
    await bot.set_webhook(WEBHOOK_URL)
    print("Webhook set:", WEBHOOK_URL)

if __name__ == "__main__":
    asyncio.run(on_startup())
    app.run(host="0.0.0.0", port=PORT)