import os
import json
import asyncio
import aiohttp
import logging
import random
from datetime import datetime, timedelta
from pathlib import Path
from threading import Thread
from concurrent.futures import ThreadPoolExecutor

try:
    import requests
    from flask import Flask, request
    from aiogram import Bot, Dispatcher, Router, types
    from aiogram.filters import CommandStart, Command
    from aiogram.types import (
        ReplyKeyboardMarkup,
        KeyboardButton,
        Message,
        InlineKeyboardMarkup,
        InlineKeyboardButton
    )
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print("📦 Устанавливаем зависимости...")
    print("Запустите: pip install -r requirements.txt")
    exit(1)

# =====================
# НАСТРОЙКА ЛОГИРОВАНИЯ
# =====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =====================
# CONFIG
# =====================

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
BASE_URL = os.getenv("BASE_URL", "https://numerology-bot-m48t.onrender.com")
ADMIN_IDS = [260219938]

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = BASE_URL + WEBHOOK_PATH

# Системные промпты
SYSTEM_PROMPTS = {
    "portrait": """Ты — профессиональный нумеролог с 20-летним опытом.
Создай подробный нумерологический портрет по дате рождения.
Формат:
1. Число жизненного пути и его значение
2. Число судьбы  
3. Сильные стороны личности
4. Зоны для развития
5. Профессиональные рекомендации
6. Советы по отношениям

Будь вдохновляющим и практичным. Не упоминай, что ты ИИ.""",
    
    "compatibility": """Ты — эксперт по нумерологической совместимости.
Проанализируй совместимость двух людей по датам рождения.
Включи:
1. Общую оценку совместимости
2. Сильные стороны пары
3. Потенциальные вызовы
4. Рекомендации для гармонии
5. Совместные возможности

Будь дипломатичным и конструктивным.""",
    
    "forecast": """Ты — аналитик по нумерологическим циклам.
Создай прогноз на указанный период по дате рождения.
Включи:
1. Общую энергетику периода
2. Благоприятные возможности
3. Возможные вызовы
4. Рекомендации для успеха
5. Фокусные области

Будь конкретным и практичным.""",
    
    "horoscope": """Ты — нумеролог-астролог.
Создай вдохновляющий гороскоп на указанный период.
Включи:
1. Общую атмосферу дня/периода
2. Сферу удачи
3. Совет от чисел
4. Что следует делать
5. Чего лучше избегать

Будь креативным и мотивирующим."""
}

# =====================
# ХРАНИЛИЩЕ ДАННЫХ
# =====================

USERS_FILE = Path("users.json")
STATS_FILE = Path("stats.json")

def load_users():
    if USERS_FILE.exists():
        try:
            return json.loads(USERS_FILE.read_text(encoding="utf-8"))
        except:
            return {}
    return {}

def save_users(data):
    try:
        USERS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except:
        pass

def load_stats():
    if STATS_FILE.exists():
        try:
            return json.loads(STATS_FILE.read_text(encoding="utf-8"))
        except:
            return {
                "total_users": 0,
                "calculations": 0,
                "compatibility_checks": 0,
                "forecasts": 0,
                "horoscopes": 0,
                "daily_stats": {}
            }
    return {
        "total_users": 0,
        "calculations": 0,
        "compatibility_checks": 0,
        "forecasts": 0,
        "horoscopes": 0,
        "daily_stats": {}
    }

def save_stats(data):
    try:
        STATS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except:
        pass

users = load_users()
stats = load_stats()

# =====================
# НУМЕРОЛОГИЧЕСКИЙ КАЛЬКУЛЯТОР
# =====================

class NumerologyCalculator:
    @staticmethod
    def calculate_life_path(date_str: str) -> int:
        try:
            digits = date_str.replace('.', '')
            total = sum(int(d) for d in digits)
            
            while total > 9 and total not in [11, 22, 33]:
                total = sum(int(d) for d in str(total))
            
            return total
        except:
            return None
    
    @staticmethod
    def generate_affirmation(date_str: str) -> str:
        life_number = NumerologyCalculator.calculate_life_path(date_str)
        
        affirmations = {
            1: "Я — лидер своей жизни, уверенно иду к целям",
            2: "Я открыт гармоничным отношениям и сотрудничеству",
            3: "Я творчески выражаю себя и несу радость в мир",
            4: "Я строю прочный фундамент для своего будущего",
            5: "Я свободен в своих выборах и открыт переменам",
            6: "Я создаю гармонию и заботу в отношениях",
            7: "Я доверяю интуиции и ищу мудрость",
            8: "Я привлекаю изобилие и достигаю успеха",
            9: "Я завершаю циклы с благодарностью",
            11: "Я вдохновляю других своим видением",
            22: "Я воплощаю великие идеи в реальность",
            33: "Я несу свет и исцеление через служение"
        }
        
        return affirmations.get(life_number, "Я принимаю день с благодарностью и открытостью")

# =====================
# GROQ API
# =====================

async def ask_groq(prompt: str, prompt_type: str = "portrait") -> str:
    if not GROQ_API_KEY:
        return "⚠️ Сервис временно недоступен. Пожалуйста, попробуйте позже."
    
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPTS.get(prompt_type, SYSTEM_PROMPTS["portrait"])},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 800
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data, timeout=30) as resp:
                if resp.status != 200:
                    return "⚠️ Ошибка при обработке запроса."
                result = await resp.json()
                return result["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"GROQ API error: {e}")
        return "⚠️ Произошла ошибка. Попробуйте позже."

# =====================
# ИНИЦИАЛИЗАЦИЯ БОТА
# =====================

try:
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    router = Router()
    dp.include_router(router)
    logger.info("✅ Бот инициализирован")
except Exception as e:
    logger.error(f"❌ Ошибка инициализации бота: {e}")
    exit(1)

# =====================
# КЛАВИАТУРЫ
# =====================

def main_menu(user_id: int = None):
    keyboard = [
        [KeyboardButton(text="✨ Нумеропортрет")],
        [KeyboardButton(text="💞 Совместимость")],
        [KeyboardButton(text="🌟 Гороскоп дня")],
        [KeyboardButton(text="📅 Прогноз на период")],
        [KeyboardButton(text="🔄 Аффирмация")]
    ]
    
    if user_id in ADMIN_IDS:
        keyboard.append([KeyboardButton(text="👑 Админ")])
    
    keyboard.append([KeyboardButton(text="ℹ️ Помощь")])
    
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        input_field_placeholder="Выберите действие..."
    )

def horoscope_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🌞 Сегодня", callback_data="horoscope_today"),
            InlineKeyboardButton(text="🌙 Завтра", callback_data="horoscope_tomorrow")
        ],
        [
            InlineKeyboardButton(text="📅 На неделю", callback_data="horoscope_week"),
            InlineKeyboardButton(text="📆 На месяц", callback_data="horoscope_month")
        ]
    ])

def period_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 На месяц", callback_data="period_month"),
            InlineKeyboardButton(text="📆 На 3 месяца", callback_data="period_quarter")
        ],
        [
            InlineKeyboardButton(text="🎯 На год", callback_data="period_year"),
            InlineKeyboardButton(text="✨ На неделю", callback_data="period_week")
        ]
    ])

def compatibility_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💑 Романтика", callback_data="comp_love"),
            InlineKeyboardButton(text="💼 Бизнес", callback_data="comp_business")
        ],
        [
            InlineKeyboardButton(text="👥 Дружба", callback_data="comp_friends"),
            InlineKeyboardButton(text="👨‍👩‍👧‍👦 Семья", callback_data="comp_family")
        ]
    ])

# =====================
# ОБРАБОТЧИКИ СООБЩЕНИЙ
# =====================

@router.message(CommandStart())
async def start_command(message: Message):
    user_id = message.from_user.id
    
    if str(user_id) not in users:
        users[str(user_id)] = {
            "username": message.from_user.username or "",
            "first_name": message.from_user.first_name or "",
            "last_name": message.from_user.last_name or "",
            "joined": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_active": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        save_users(users)
        stats["total_users"] = len(users)
        save_stats(stats)
    
    greetings = [
        f"✨ Приветствую, {message.from_user.first_name or 'друг'}! Готовы раскрыть тайны чисел?",
        f"🌟 Добро пожаловать, {message.from_user.first_name or 'путешественник'}! Числа ждут анализа.",
        f"🔮 Здравствуйте, {message.from_user.first_name or 'искатель'}! Давайте исследуем вашу нумерологию."
    ]
    
    await message.answer(
        random.choice(greetings) + "\n\nВыберите действие:",
        reply_markup=main_menu(user_id)
    )
    logger.info(f"Пользователь {user_id} запустил бота")

@router.message(lambda m: m.text == "✨ Нумеропортрет")
async def portrait_handler(message: Message):
    await message.answer(
        "✨ *Нумерологический портрет*\n\n"
        "Введите вашу дату рождения в формате ДД.ММ.ГГГГ\n\n"
        "*Пример:* 15.05.1990\n\n"
        "Я создам подробный анализ вашей личности на основе чисел.",
        parse_mode="Markdown",
        reply_markup=main_menu(message.from_user.id)
    )

@router.message(lambda m: m.text == "💞 Совместимость")
async def compatibility_handler(message: Message):
    await message.answer(
        "💞 *Нумерологическая совместимость*\n\n"
        "Выберите тип отношений для анализа:",
        reply_markup=compatibility_menu()
    )

@router.message(lambda m: m.text == "🌟 Гороскоп дня")
async def horoscope_handler(message: Message):
    await message.answer(
        "🌟 *Персональный гороскоп*\n\n"
        "Выберите период для гороскопа:",
        reply_markup=horoscope_menu()
    )

@router.message(lambda m: m.text == "📅 Прогноз на период")
async def forecast_handler(message: Message):
    await message.answer(
        "📅 *Нумерологический прогноз*\n\n"
        "Выберите период для прогноза:",
        reply_markup=period_menu()
    )

@router.message(lambda m: m.text == "🔄 Аффирмация")
async def affirmation_handler(message: Message):
    await message.answer(
        "🔄 *Персональная аффирмация*\n\n"
        "Введите вашу дату рождения:\n\n"
        "*Формат:* ДД.ММ.ГГГГ\n"
        "*Пример:* 15.05.1990\n\n"
        "Я создам для вас аффирмацию.",
        parse_mode="Markdown",
        reply_markup=main_menu(message.from_user.id)
    )

@router.message(lambda m: m.text == "ℹ️ Помощь")
async def help_handler(message: Message):
    help_text = f"""
🌟 *Нумерологический бот с AI*

✨ *Доступные функции:*
1. ✨ Нумеропортрет — анализ личности
2. 💞 Совместимость — анализ отношений  
3. 🌟 Гороскоп дня — нумерологический гороскоп
4. 📅 Прогноз на период — прогноз на период
5. 🔄 Аффирмация — персональное утверждение

📋 *Как пользоваться:*
1. Выберите функцию в меню
2. Следуйте инструкциям
3. Получите анализ

🔮 *Формат даты:* ДД.ММ.ГГГГ

📊 *Статистика:* {stats['total_users']} пользователей уже доверили мне свои числа!
"""
    await message.answer(help_text, parse_mode="Markdown", reply_markup=main_menu(message.from_user.id))

@router.message(lambda m: m.text == "👑 Админ")
async def admin_handler(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("Эта функция доступна только администраторам")
        return
    
    today = datetime.now().strftime("%Y-%m-%d")
    admin_text = f"""
👑 *Панель администратора*

📊 Статистика:
• Пользователей: {stats['total_users']}
• Анализов портретов: {stats.get('calculations', 0)}
• Проверок совместимости: {stats.get('compatibility_checks', 0)}
• Прогнозов: {stats.get('forecasts', 0)}
• Гороскопов: {stats.get('horoscopes', 0)}
• Запросов сегодня: {stats['daily_stats'].get(today, 0)}

🌐 Веб-админка: {BASE_URL}/admin
🆔 Ваш ID: {message.from_user.id}
"""
    await message.answer(admin_text, parse_mode="Markdown", reply_markup=main_menu(message.from_user.id))

# =====================
# ОБРАБОТЧИКИ CALLBACK КНОПОК
# =====================

@router.callback_query(lambda c: c.data.startswith("horoscope_"))
async def process_horoscope_callback(callback: types.CallbackQuery):
    """Обработка выбора периода для гороскопа - ИСПРАВЛЕННЫЙ ВАРИАНТ"""
    period = callback.data.split("_")[1]
    
    period_names = {
        "today": "сегодня 🌞",
        "tomorrow": "завтра 🌙", 
        "week": "неделю 📅",
        "month": "месяц 📆"
    }
    
    logger.info(f"Пользователь {callback.from_user.id} выбрал гороскоп на {period}")
    
    # Отправляем новое сообщение вместо редактирования
    await callback.message.answer(
        f"🌟 *Гороскоп на {period_names[period]}*\n\n"
        "Введите вашу дату рождения:\n\n"
        "*Формат:* ДД.ММ.ГГГГ\n"
        "*Пример:* 15.05.1990\n\n"
        "Я создам персонализированный нумерологический гороскоп.",
        parse_mode="Markdown"
    )
    
    # Обязательно отвечаем на callback
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("period_"))
async def process_forecast_callback(callback: types.CallbackQuery):
    """Обработка выбора периода для прогноза"""
    period = callback.data.split("_")[1]
    
    period_names = {
        "week": "неделю ✨",
        "month": "месяц 📅", 
        "quarter": "3 месяца 📆",
        "year": "год 🎯"
    }
    
    await callback.message.answer(
        f"📅 *Прогноз на {period_names[period]}*\n\n"
        "Введите вашу дату рождения:\n\n"
        "*Формат:* ДД.ММ.ГГГГ\n"
        "*Пример:* 15.05.1990\n\n"
        "Я сделаю нумерологический прогноз.",
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("comp_"))
async def process_compatibility_callback(callback: types.CallbackQuery):
    """Обработка выбора типа совместимости"""
    comp_type = callback.data.split("_")[1]
    
    type_names = {
        "love": "романтических отношений 💑",
        "business": "делового партнерства 💼", 
        "friends": "дружбы 👥",
        "family": "семейных отношений 👨‍👩‍👧‍👦"
    }
    
    await callback.message.answer(
        f"💞 *Совместимость для {type_names[comp_type]}*\n\n"
        "Введите две даты рождения через пробел:\n\n"
        "*Формат:* ДД.ММ.ГГГГ ДД.ММ.ГГГГ\n"
        "*Пример:* 15.05.1990 20.08.1985\n\n"
        "Я проанализирую энергетическую совместимость.",
        parse_mode="Markdown"
    )
    await callback.answer()

# =====================
# ОБРАБОТЧИКИ ДАТ
# =====================

def is_valid_date(text: str) -> bool:
    try:
        datetime.strptime(text, "%d.%m.%Y")
        return True
    except:
        return False

@router.message(lambda m: m.text and is_valid_date(m.text))
async def process_date(message: Message):
    """Обработка введенной даты"""
    date_str = message.text
    user_id = message.from_user.id
    
    await message.answer("✨ Анализирую данные...")
    
    # Обновляем статистику
    stats["calculations"] = stats.get("calculations", 0) + 1
    today = datetime.now().strftime("%Y-%m-%d")
    stats["daily_stats"][today] = stats["daily_stats"].get(today, 0) + 1
    save_stats(stats)
    
    # Получаем число жизненного пути
    life_number = NumerologyCalculator.calculate_life_path(date_str)
    affirmation = NumerologyCalculator.generate_affirmation(date_str)
    
    # Простой ответ для теста
    response = f"""
✨ *Анализ для {date_str}*

*Число жизненного пути:* {life_number or 'не определено'}

*Значение числа {life_number}:*
{await get_number_meaning(life_number)}

🔄 *Ваша аффирмация:*
{affirmation}

*Совет на сегодня:*
{random.choice([
    "Сфокусируйтесь на главных целях",
    "Будьте открыты новым знакомствам",
    "Проявите творческий подход",
    "Слушайте свою интуицию",
    "Заботьтесь о близких"
])}
"""
    
    await message.answer(response, parse_mode="Markdown", reply_markup=main_menu(user_id))

async def get_number_meaning(number: int) -> str:
    meanings = {
        1: "Лидерство, независимость, инновации",
        2: "Дипломатия, сотрудничество, гармония", 
        3: "Творчество, общение, оптимизм",
        4: "Стабильность, практичность, организация",
        5: "Свобода, перемены, адаптивность",
        6: "Ответственность, забота, гармония",
        7: "Анализ, интуиция, духовность",
        8: "Успех, изобилие, власть",
        9: "Завершение, мудрость, гуманизм",
        11: "Интуиция, озарение, вдохновение",
        22: "Мастер-строитель, реализация идей",
        33: "Мастер-учитель, служение человечеству"
    }
    return meanings.get(number, "Особое число с уникальной энергией")

# =====================
# FLASK APP
# =====================

app = Flask(__name__)

@app.route("/")
def home():
    return """
    <html>
        <head>
            <title>🔮 Нумерологический Бот</title>
            <meta charset="utf-8">
            <style>
                body {
                    font-family: Arial, sans-serif;
                    max-width: 800px;
                    margin: 50px auto;
                    padding: 20px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    text-align: center;
                    border-radius: 20px;
                }
                h1 {
                    font-size: 3em;
                    margin-bottom: 20px;
                }
                .status {
                    background: rgba(255,255,255,0.2);
                    padding: 20px;
                    border-radius: 10px;
                    margin: 20px 0;
                }
                a {
                    color: white;
                    background: rgba(255,255,255,0.3);
                    padding: 10px 20px;
                    border-radius: 5px;
                    text-decoration: none;
                    margin: 10px;
                    display: inline-block;
                }
                a:hover {
                    background: rgba(255,255,255,0.5);
                }
            </style>
        </head>
        <body>
            <h1>🔮 Нумерологический Бот</h1>
            <div class="status">
                <p>✅ Бот работает и готов к запросам!</p>
                <p>👥 Пользователей: {}</p>
                <p>🕐 Запущен: {}</p>
            </div>
            <div>
                <a href="/admin">👑 Админ-панель</a>
                <a href="/ping">📡 Ping</a>
                <a href="/health">❤️ Health Check</a>
            </div>
            <p style="margin-top: 30px; opacity: 0.8;">
                Откройте Telegram и найдите бота для использования
            </p>
        </body>
    </html>
    """.format(stats['total_users'], datetime.now().strftime("%d.%m.%Y %H:%M:%S"))

@app.route("/ping")
def ping():
    return "pong"

@app.route("/health")
def health():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "bot": BOT_TOKEN is not None,
        "users": stats['total_users'],
        "requests_today": stats['daily_stats'].get(datetime.now().strftime("%Y-%m-%d"), 0)
    }

@app.route("/admin")
def admin():
    today = datetime.now().strftime("%Y-%m-%d")
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Админ-панель</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ font-family: Arial, sans-serif; max-width: 1000px; margin: 0 auto; padding: 20px; background: #f5f5f5; }}
            .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 15px; margin-bottom: 30px; text-align: center; }}
            .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }}
            .stat-card {{ background: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); text-align: center; }}
            .stat-number {{ font-size: 36px; font-weight: bold; color: #667eea; margin: 10px 0; }}
            .stat-label {{ color: #666; font-size: 14px; text-transform: uppercase; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>👑 Админ-панель нумерологического бота</h1>
            <p>Статус: <span style="background: #4CAF50; color: white; padding: 5px 15px; border-radius: 20px;">● Активен</span></p>
            <p>Обновлено: {datetime.now().strftime("%d.%m.%Y %H:%M")}</p>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card"><div class="stat-number">{stats.get('total_users', 0)}</div><div class="stat-label">Пользователей</div></div>
            <div class="stat-card"><div class="stat-number">{stats.get('calculations', 0)}</div><div class="stat-label">Анализов</div></div>
            <div class="stat-card"><div class="stat-number">{stats.get('compatibility_checks', 0)}</div><div class="stat-label">Совместимостей</div></div>
            <div class="stat-card"><div class="stat-number">{stats.get('horoscopes', 0)}</div><div class="stat-label">Гороскопов</div></div>
            <div class="stat-card"><div class="stat-number">{stats.get('forecasts', 0)}</div><div class="stat-label">Прогнозов</div></div>
            <div class="stat-card"><div class="stat-number">{stats['daily_stats'].get(today, 0)}</div><div class="stat-label">Запросов сегодня</div></div>
        </div>
        
        <div style="background: white; padding: 20px; border-radius: 10px; margin-top: 30px;">
            <h3>📊 Информация</h3>
            <p><strong>Webhook URL:</strong> {WEBHOOK_URL}</p>
            <p><strong>Админ ID:</strong> {ADMIN_IDS[0]}</p>
            <p><strong>База URL:</strong> {BASE_URL}</p>
        </div>
    </body>
    </html>
    """
    return html

@app.route(WEBHOOK_PATH, methods=["POST", "GET"])
def webhook():
    if request.method == "GET":
        return "✅ Webhook готов к работе!", 200
    
    try:
        data = request.get_json()
        
        # Логируем входящие запросы
        if 'message' in data and 'text' in data['message']:
            logger.info(f"📨 Сообщение от {data['message']['from'].get('id')}: {data['message']['text']}")
        elif 'callback_query' in data:
            logger.info(f"🔘 Callback от {data['callback_query']['from']['id']}: {data['callback_query']['data']}")
        
        update = types.Update(**data)
        
        # Запускаем обработку в event loop
        asyncio.run_coroutine_threadsafe(
            dp.feed_update(bot, update),
            loop
        )
        return "ok"
    except Exception as e:
        logger.error(f"❌ Ошибка webhook: {e}")
        return "error", 500

# =====================
# WEBHOOK SETUP
# =====================

def setup_webhook():
    try:
        logger.info("🔄 Настройка webhook...")
        
        # Удаляем старый webhook
        delete_url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook"
        requests.post(delete_url, json={"drop_pending_updates": True})
        logger.info("✅ Старый webhook удален")
        
        # Устанавливаем новый
        set_url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
        data = {
            "url": WEBHOOK_URL,
            "drop_pending_updates": True,
            "allowed_updates": ["message", "callback_query"]
        }
        response = requests.post(set_url, json=data)
        
        if response.status_code == 200:
            logger.info(f"✅ Webhook установлен: {WEBHOOK_URL}")
            logger.info(f"✅ Ответ Telegram: {response.json()}")
        else:
            logger.error(f"❌ Ошибка установки webhook: {response.text}")
    except Exception as e:
        logger.error(f"❌ Ошибка настройки webhook: {e}")

# =====================
# ЗАПУСК
# =====================

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"🚀 Запуск Flask на порту {port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)

if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("🚀 ЗАПУСК НУМЕРОЛОГИЧЕСКОГО БОТА")
    logger.info("=" * 50)
    
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN не установлен!")
        exit(1)
    
    logger.info(f"✅ BOT_TOKEN: {'Установлен' if BOT_TOKEN else 'Нет'}")
    logger.info(f"✅ GROQ_API_KEY: {'Установлен' if GROQ_API_KEY else 'Нет'}")
    logger.info(f"✅ BASE_URL: {BASE_URL}")
    logger.info(f"✅ ADMIN_IDS: {ADMIN_IDS}")
    
    # Создаем файлы если их нет
    if not USERS_FILE.exists():
        save_users({})
        logger.info("✅ Файл users.json создан")
    if not STATS_FILE.exists():
        save_stats(load_stats())
        logger.info("✅ Файл stats.json создан")
    
    # Настраиваем event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Настраиваем webhook
    setup_webhook()
    
    # Запускаем Flask в отдельном потоке
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    logger.info("✨ Нумерологический бот запущен!")
    logger.info(f"🌐 Админ-панель: {BASE_URL}/admin")
    logger.info(f"👑 Админ ID: {ADMIN_IDS[0]}")
    logger.info("📱 Откройте Telegram и найдите вашего бота")
    
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        logger.info("⏹️ Остановка бота...")
    finally:
        loop.close()
