import os
import json
import asyncio
import requests
import aiohttp
import logging
logging.basicConfig(level=logging.INFO)
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
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
BASE_URL = os.getenv("BASE_URL")
ADMIN_IDS = [260219938]  # Ваш ID

MODEL_NAME = "llama-3.1-8b-instant"
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = BASE_URL + WEBHOOK_PATH

GROQ_SYSTEM_PROMPT = """
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

Язык: русский. Не упоминай, что ты ИИ.
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

async def ask_groq(prompt: str) -> str:
    url = "https://api.groq.com/openai/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": GROQ_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data, timeout=aiohttp.ClientTimeout(total=90)) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    print(f"GROQ API ERROR {resp.status}: {error_text}")
                    return "⚠️ Произошла ошибка при обработке запроса. Попробуйте позже."
                    
                result = await resp.json()
                return result["choices"][0]["message"]["content"]

    except Exception as e:
        print("GROQ ERROR:", e)
        return "⚠️ Произошла ошибка при обработке запроса. Попробуйте позже."

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

def main_menu(user_id: int = None):
    """Создает меню с учетом прав пользователя"""
    keyboard = [
        [KeyboardButton(text="✨ Мой нумеропортрет")],
        [KeyboardButton(text="💞 Совместимость пар")],
        [KeyboardButton(text="📅 Гороскоп на период")],
        [KeyboardButton(text="🌟 Аффирмация дня")],
        [KeyboardButton(text="ℹ️ О боте")]
    ]
    
    # Добавляем кнопку админа только для вашего ID
    if user_id in ADMIN_IDS:
        keyboard.insert(0, [KeyboardButton(text="👑 Админ-панель")])
    
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True
    )

from datetime import datetime

def is_date(text: str) -> bool:
    try:
        datetime.strptime(text, "%d.%m.%Y")
        return True
    except:
        return False

# =====================
# HANDLERS
# =====================

@router.message(CommandStart())
async def start(m: Message):
    user_id = m.from_user.id
    
    # Сохраняем пользователя
    if str(user_id) not in users:
        users[str(user_id)] = {
            "username": m.from_user.username or "",
            "first_name": m.from_user.first_name or "",
            "last_name": m.from_user.last_name or "",
            "joined": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        save_users(users)
    
    await m.answer(
        f"✨ Приветствую, {m.from_user.first_name or 'друг'}! Я — ваш персональный нумеролог.\n\n"
        "Выберите действие:",
        reply_markup=main_menu(user_id)
    )

@router.message(lambda m: m.text == "👑 Админ-панель")
async def admin_panel(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        await m.answer("У вас нет прав доступа к админ-панели", reply_markup=main_menu(m.from_user.id))
        return
    
    stats_text = f"""
📊 *Статистика бота*

👥 Пользователей: {len(users)}
🌐 Админ-панель: {BASE_URL}/admin
🆔 Ваш ID: {m.from_user.id}

*Последние пользователи:*
"""
    
    # Показываем последних 5 пользователей
    user_items = list(users.items())[-5:]
    for user_id, user_data in user_items:
        stats_text += f"\n• {user_data.get('first_name', 'Неизвестно')} (ID: {user_id})"
    
    await m.answer(stats_text, parse_mode="Markdown", reply_markup=main_menu(m.from_user.id))

@router.message(lambda m: m.text == "✨ Мой нумеропортрет")
async def numerology_portrait(m: Message):
    await m.answer(
        "✨ *Нумерологический портрет*\n\n"
        "Введите вашу дату рождения в формате ДД.ММ.ГГГГ\n\n"
        "Например: 15.05.1990\n\n"
        "Я проанализирую:\n"
        "• Число жизненного пути 🛤️\n"
        "• Число судьбы 🌟\n"
        "• Сильные стороны 💪\n"
        "• Рекомендации 📈",
        parse_mode="Markdown",
        reply_markup=main_menu(m.from_user.id)
    )

@router.message(lambda m: m.text == "💞 Совместимость пар")
async def compatibility(m: Message):
    await m.answer(
        "💞 *Совместимость партнеров*\n\n"
        "Введите две даты рождения через пробел:\n\n"
        "*Формат:* ДД.ММ.ГГГГ ДД.ММ.ГГГГ\n"
        "*Пример:* 15.05.1990 20.08.1985\n\n"
        "Я проанализирую совместимость по числам судьбы.",
        parse_mode="Markdown",
        reply_markup=main_menu(m.from_user.id)
    )

@router.message(lambda m: m.text == "📅 Гороскоп на период")
async def horoscope(m: Message):
    await m.answer(
        "📅 *Гороскоп на период*\n\n"
        "Введите дату рождения и период:\n\n"
        "*Формат:* ДД.ММ.ГГГГ период\n"
        "*Примеры:*\n15.05.1990 сегодня\n15.05.1990 неделя\n15.05.1990 месяц\n\n"
        "Доступные периоды: сегодня, завтра, неделя, месяц",
        parse_mode="Markdown",
        reply_markup=main_menu(m.from_user.id)
    )

@router.message(lambda m: m.text == "🌟 Аффирмация дня")
async def affirmation(m: Message):
    await m.answer(
        "🌟 *Аффирмация дня*\n\n"
        "Введите вашу дату рождения в формате ДД.ММ.ГГГГ\n\n"
        "Я создам для вас персональную аффирмацию —\n"
        "позитивное утверждение на сегодняшний день.",
        parse_mode="Markdown",
        reply_markup=main_menu(m.from_user.id)
    )

@router.message(lambda m: m.text == "ℹ️ О боте")
async def about(m: Message):
    about_text = """
🌟 *Нумерологический бот с AI*

Я — ваш персональный нумеролог, использующий искусственный интеллект для глубокого анализа.

✨ *Что я умею:*
• Создавать нумерологический портрет по дате рождения
• Анализировать совместимость партнеров
• Генерировать гороскопы на период
• Создавать персональные аффирмации

🔮 *Мой подход:*
Я сочетаю древнюю мудрость нумерологии с современными психологическими знаниями.

📊 *Статистика:*
• Пользователей: {}

💡 *Совет:* Регулярно обращайтесь за анализом — числа могут раскрывать новые грани вашего пути!
""".format(len(users))
    
    await m.answer(about_text, parse_mode="Markdown", reply_markup=main_menu(m.from_user.id))

@router.message(lambda m: is_date(m.text))
async def date_handler(m: Message):
    await m.answer("🔮 Анализирую дату...")

    prompt = f"Сделай нумерологический анализ даты рождения {m.text}. Дай подробный портрет личности."
    result = await ask_groq(prompt)

    await m.answer(result, reply_markup=main_menu(m.from_user.id))

@router.message(lambda m: len(m.text.split()) == 2 and all("." in part for part in m.text.split()[:2]))
async def compatibility_handler(m: Message):
    parts = m.text.split()
    if len(parts) >= 2 and is_date(parts[0]) and is_date(parts[1]):
        d1, d2 = parts[0], parts[1]
        await m.answer("💞 Анализирую совместимость...")

        prompt = f"Совместимость по датам рождения: {d1} и {d2}. Проанализируй их нумерологическую совместимость."
        result = await ask_groq(prompt)

        await m.answer(result, reply_markup=main_menu(m.from_user.id))
    else:
        await m.answer("Пожалуйста, введите две даты в формате: ДД.ММ.ГГГГ ДД.ММ.ГГГГ")

@router.message(lambda m: len(m.text.split()) == 2 and is_date(m.text.split()[0]))
async def horoscope_handler(m: Message):
    parts = m.text.split()
    date_str = parts[0]
    period = parts[1].lower()
    
    if period in ["сегодня", "завтра", "неделя", "месяц"]:
        await m.answer(f"🌟 Создаю гороскоп на {period}...")

        prompt = f"Создай нумерологический гороскоп на {period} для человека, родившегося {date_str}. Будь вдохновляющим."
        result = await ask_groq(prompt)

        await m.answer(result, reply_markup=main_menu(m.from_user.id))
    else:
        await m.answer("Пожалуйста, укажите период: сегодня, завтра, неделя или месяц")

# =====================
# FLASK WEBHOOK SERVER
# =====================

app = Flask(__name__)

@app.route("/")
def home():
    return "🔮 Нумерологический бот работает! Напишите /start в Telegram"

@app.route("/ping")
def ping():
    return "pong"

@app.route("/admin")
def admin():
    """Простая админ-панель"""
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Админ-панель нумерологического бота</title>
        <style>
            body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
            .header {{ background: #667eea; color: white; padding: 20px; border-radius: 10px; }}
            .stat {{ background: #f5f5f5; padding: 15px; margin: 10px 0; border-radius: 5px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>👑 Админ-панель нумерологического бота</h1>
            <p>Статус: <span style="color: green;">●</span> Активен</p>
        </div>
        
        <div class="stat">
            <h3>📊 Статистика</h3>
            <p>👥 Пользователей: {len(users)}</p>
            <p>🆔 Админ ID: {ADMIN_IDS[0]}</p>
            <p>🌐 Webhook: {WEBHOOK_URL}</p>
        </div>
        
        <div class="stat">
            <h3>👥 Последние пользователи</h3>
    """
    
    user_items = list(users.items())[-10:]
    for user_id, user_data in user_items:
        html += f"<p>• {user_data.get('first_name', 'Неизвестно')} (ID: {user_id})</p>"
    
    html += """
        </div>
        
        <div class="stat">
            <h3>ℹ️ Информация</h3>
            <p>Бот успешно работает и обрабатывает запросы.</p>
            <p>Для доступа к полной статистике используйте кнопку "👑 Админ-панель" в боте.</p>
        </div>
    </body>
    </html>
    """
    
    return html

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
    
    # Проверка наличия необходимых переменных окружения
    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN is not set!")
        exit(1)
    if not GROQ_API_KEY:
        print("ERROR: GROQ_API_KEY is not set!")
        exit(1)
    if not BASE_URL:
        print("ERROR: BASE_URL is not set!")
        exit(1)
    
    set_webhook()

    Thread(target=run_flask, daemon=True).start()

    print("✨ Нумерологический бот запущен!")
    print(f"🌐 Админ-панель: {BASE_URL}/admin")
    print(f"👑 Админ ID: {ADMIN_IDS[0]}")
    print("🎯 Ключевые функции:")
    print("• Нумерологический портрет")
    print("• Совместимость партнеров")
    print("• Гороскоп на период")
    print("• Аффирмация дня")
    
    loop.run_forever()
