import os
import asyncio
import threading
from flask import Flask, request

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

BOT_TOKEN = os.getenv("BOT_TOKEN")
BASE_URL = "https://numerology-bot-m48t.onrender.com"
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = BASE_URL + WEBHOOK_PATH
PORT = int(os.getenv("PORT", 10000))

app = Flask(__name__)

bot: Bot = None
dp: Dispatcher = None
loop: asyncio.AbstractEventLoop = None

# ======================
# BOT SETUP
# ======================

async def setup_bot():
    global bot, dp

    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()

    @dp.message(Command("start"))
    async def start_cmd(message: types.Message):
        await message.answer("Привет 👋\nВведи дату рождения в формате ДД.ММ.ГГГГ")

    @dp.message(Command("help"))
    async def help_cmd(message: types.Message):
        await message.answer("Введите дату рождения в формате ДД.ММ.ГГГГ")

    @dp.message()
    async def fallback(message: types.Message):
        await message.answer("Введите дату рождения в формате ДД.ММ.ГГГГ")

    await bot.set_webhook(WEBHOOK_URL)
    print("Webhook set:", WEBHOOK_URL)

# ======================
# LOOP THREAD
# ======================

def run_loop():
    global loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(setup_bot())
    loop.run_forever()

threading.Thread(target=run_loop, daemon=True).start()

# ======================
# FLASK
# ======================

@app.route("/")
def home():
    return "OK"

@app.route("/ping")
def ping():
    return "pong"

@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    update = types.Update(**data)

    asyncio.run_coroutine_threadsafe(
        dp.feed_update(bot, update),
        loop
    )

    return "ok"

# ======================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)