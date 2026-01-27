import os
import json
import asyncio
import requests
import aiohttp
import logging
logging.basicConfig(level=logging.INFO)
from pathlib import Path
from datetime import datetime, timedelta
from flask import Flask, request, render_template_string
from threading import Thread
from collections import defaultdict
import random

from aiogram import Bot, Dispatcher, Router, types
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

# =====================
# FLASK APP CREATION (ДОЛЖНО БЫТЬ ПЕРВЫМ!)
# =====================
app = Flask(__name__)

# =====================
# CONFIG
# =====================

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
BASE_URL = os.getenv("BASE_URL")
ADMIN_IDS = [260219938]  # ЗАМЕНИТЕ НА СВОЙ ID

MODEL_NAME = "llama-3.1-8b-instant"
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = BASE_URL + WEBHOOK_PATH
ADMIN_PATH = "/admin"

# Расширенный промпт для разных типов анализа
GROQ_SYSTEM_PROMPTS = {
    "default": """Ты — профессиональный нумеролог-консультант с 20-летним опытом.
Твоя задача — рассчитывать нумерологические значения и давать практические рекомендации.
Пиши дружелюбно, уверенно, без мистического фанатизма.
Язык: русский. Не упоминай, что ты ИИ.""",
    
    "detailed": """Ты — эксперт по нумерологии и психологии личности.
Анализируй даты рождения, давая глубокие, персонализированные инсайты.
Формат: 1) Ключевое число, 2) Сильные стороны, 3) Зоны роста, 4) Практические советы.
Будь точным, но вдохновляющим.""",
    
    "compatibility": """Ты — специалист по отношениям и совместимости.
Анализируй пары дат рождения, давая рекомендации для разных сфер жизни.
Будь дипломатичным, подчеркивай сильные стороны пары.""",
    
    "forecast": """Ты — аналитик по циклам и прогнозам.
На основе даты рождения делай прогнозы на указанный период.
Сосредоточься на возможностях и вызовах, давай практические рекомендации.""",
    
    "horoscope": """Ты — астролог-нумеролог.
Создавай вдохновляющие, персонализированные гороскопы на основе чисел.
Сочетай нумерологию с позитивной психологией.
Будь креативным, но реалистичным."""
}



# =====================
# USERS STORAGE & PERSONALIZATION
# =====================

USERS_FILE = Path("users.json")
STATS_FILE = Path("stats.json")
PERSONALIZATION_FILE = Path("personalization.json")

def load_users():
    if USERS_FILE.exists():
        return json.loads(USERS_FILE.read_text(encoding="utf-8"))
    return {}

def save_users(data):
    USERS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def load_stats():
    if STATS_FILE.exists():
        return json.loads(STATS_FILE.read_text(encoding="utf-8"))
    return {
        "total_users": 0,
        "active_users": 0,
        "calculations": 0,
        "compatibility_checks": 0,
        "forecasts": 0,
        "horoscopes": 0,
        "daily_stats": defaultdict(int),
        "popular_features": defaultdict(int)
    }

def save_stats(data):
    STATS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def load_personalization():
    if PERSONALIZATION_FILE.exists():
        return json.loads(PERSONALIZATION_FILE.read_text(encoding="utf-8"))
    return {"user_preferences": {}, "user_history": {}}

def save_personalization(data):
    PERSONALIZATION_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

users = load_users()
stats = load_stats()
personalization = load_personalization()

# =====================
# PERSONALIZATION ENGINE
# =====================

class PersonalizationEngine:
    @staticmethod
    def update_user_profile(user_id: int, action: str, data: dict = None):
        """Обновление профиля пользователя для персонализации"""
        user_id_str = str(user_id)
        
        if user_id_str not in personalization["user_history"]:
            personalization["user_history"][user_id_str] = {
                "actions": [],
                "preferences": {},
                "last_interaction": datetime.now().isoformat()
            }
        
        # Записываем действие
        personalization["user_history"][user_id_str]["actions"].append({
            "action": action,
            "timestamp": datetime.now().isoformat(),
            "data": data
        })
        
        # Ограничиваем историю последними 50 действиями
        if len(personalization["user_history"][user_id_str]["actions"]) > 50:
            personalization["user_history"][user_id_str]["actions"] = personalization["user_history"][user_id_str]["actions"][-50:]
        
        save_personalization(personalization)
    
    @staticmethod
    def get_user_preferences(user_id: int) -> dict:
        """Получение предпочтений пользователя"""
        user_id_str = str(user_id)
        return personalization["user_history"].get(user_id_str, {}).get("preferences", {})
    
    @staticmethod
    def personalize_response(user_id: int, base_response: str, feature_type: str) -> str:
        """Персонализация ответа на основе истории пользователя"""
        user_history = personalization["user_history"].get(str(user_id), {})
        actions = user_history.get("actions", [])
        
        if len(actions) < 3:
            return base_response
        
        # Анализируем предыдущие интересы
        recent_actions = [a["action"] for a in actions[-5:]]
        
        # Добавляем персонализированное вступление
        personalized_intros = [
            "Исходя из вашего интереса к саморазвитию, ",
            "Учитывая ваш предыдущий запрос, ",
            "Основываясь на вашей истории обращений, ",
            "С учетом ваших интересов, "
        ]
        
        # Проверяем, есть ли повторяющиеся темы
        action_counts = {}
        for action in recent_actions:
            action_counts[action] = action_counts.get(action, 0) + 1
        
        # Если пользователь часто запрашивает определенный тип анализа
        for action, count in action_counts.items():
            if count >= 2:
                if "relationship" in action:
                    base_response = "?? Замечаю ваш интерес к теме отношений. " + base_response
                elif "career" in action:
                    base_response = "?? Вижу ваш фокус на карьере. " + base_response
        
        return base_response

# =====================
# UNIQUE FEATURES
# =====================

class NumerologyFeatures:
    """Уникальные фичи нумерологического бота"""
    
    @staticmethod
    def calculate_life_path_number(date_str: str) -> int:
        """Расчет числа жизненного пути"""
        try:
            # Убираем точки и получаем цифры
            digits = date_str.replace('.', '')
            total = sum(int(d) for d in digits)
            
            # Сокращаем до одной цифры (кроме мастер-чисел 11, 22, 33)
            while total > 9 and total not in [11, 22, 33]:
                total = sum(int(d) for d in str(total))
            
            return total
        except:
            return None
    
    @staticmethod
    def get_compatibility_type(dates: tuple) -> str:
        """Определение типа совместимости"""
        num1 = NumerologyFeatures.calculate_life_path_number(dates[0])
        num2 = NumerologyFeatures.calculate_life_path_number(dates[1])
        
        if not num1 or not num2:
            return "general"
        
        # Определяем тип совместимости на основе чисел
        
        
        pair = (num1, num2) if num1 <= num2 else (num2, num1)
        
        for comp_type, pairs in compatible_nums.items():
            if pair in pairs:
                return comp_type
        
        return "general"
    
    @staticmethod
    def generate_daily_affirmation(date_str: str) -> str:
        """Генерация персональной аффирмации на день"""
        life_number = NumerologyFeatures.calculate_life_path_number(date_str)
        
        affirmations = {
            1: "Я — лидер своей жизни, уверенно иду к своим целям",
            2: "Я открыт гармоничным отношениям и сотрудничеству",
            3: "Я творчески выражаю себя и несу радость в мир",
            4: "Я строю прочный фундамент для своего будущего",
            5: "Я свободен в своих выборах и открыт переменам",
            6: "Я создаю гармонию и заботу в своих отношениях",
            7: "Я доверяю своей интуиции и ищу мудрость",
            8: "Я привлекаю изобилие и достигаю успеха",
            9: "Я завершаю циклы с благодарностью и открываюсь новому",
            11: "Я вдохновляю других своим видением и чувствительностью",
            22: "Я воплощаю великие идеи в реальность",
            33: "Я несу свет и исцеление через служение другим"
        }
        
        return affirmations.get(life_number, "Я принимаю сегодняшний день с благодарностью и открытостью")
    
    @staticmethod
    def calculate_favorable_days(date_str: str, month: str) -> list:
        """Расчет благоприятных дней на месяц"""
        life_number = NumerologyFeatures.calculate_life_path_number(date_str)
        
        # Логика расчета благоприятных дней на основе числа
        favorable_days = []
        base_days = list(range(1, 31))
        
        if life_number:
            # Фильтруем дни, которые соответствуют вибрации числа
            favorable_days = [day for day in base_days if day % life_number == 0 or str(life_number) in str(day)]
        
        return favorable_days[:5]  # Возвращаем 5 наиболее благоприятных дней

# =====================
# GROK API
# =====================

async def ask_groq(prompt: str, system_prompt_key: str = "default") -> str:
    url = "https://api.groq.com/openai/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": GROQ_SYSTEM_PROMPTS[system_prompt_key]},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.8,
        "max_tokens": 1500
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data, timeout=aiohttp.ClientTimeout(total=90)) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    print(f"GROQ API ERROR {resp.status}: {error_text}")
                    return "?? Произошла ошибка при обработке запроса. Попробуйте позже."
                    
                result = await resp.json()
                return result["choices"][0]["message"]["content"]

    except Exception as e:
        print("GROQ ERROR:", e)
        return "?? Произошла ошибка при обработке запроса. Попробуйте позже."

# =====================
# BOT INIT
# =====================

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# =====================
# BEAUTIFUL KEYBOARDS
# =====================

def main_menu(user_id: int = None):
    """Создает красивое главное меню"""
    # Базовые кнопки для всех пользователей
    keyboard = [
        [KeyboardButton(text="? Мой нумерологический портрет")],
        [KeyboardButton(text="?? Совместимость партнеров")],
        [KeyboardButton(text="?? Прогноз на период")],
        [KeyboardButton(text="?? Персональный гороскоп")],
        [KeyboardButton(text="?? Моя аффирмация дня")]
    ]
    
    # Добавляем кнопку админа если нужно
    if user_id in ADMIN_IDS:
        keyboard.append([KeyboardButton(text="?? Админ-панель")])
    
    keyboard.append([KeyboardButton(text="?? О боте")])
    
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        input_field_placeholder="Выберите действие..."
    )

def admin_menu():
    """Меню админ-панели"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="?? Статистика")],
            [KeyboardButton(text="?? Пользователи")],
            [KeyboardButton(text="?? Рассылка")],
            [KeyboardButton(text="?? В главное меню")]
        ],
        resize_keyboard=True
    )

def forecast_period_menu():
    """Меню выбора периода прогноза"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="?? На месяц", callback_data="forecast_month"),
                InlineKeyboardButton(text="?? На 3 месяца", callback_data="forecast_quarter")
            ],
            [
                InlineKeyboardButton(text="?? На год", callback_data="forecast_year"),
                InlineKeyboardButton(text="? На неделю", callback_data="forecast_week")
            ]
        ]
    )

def horoscope_type_menu():
    """Меню выбора типа гороскопа"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="?? На сегодня", callback_data="horoscope_today"),
                InlineKeyboardButton(text="?? На завтра", callback_data="horoscope_tomorrow")
            ],
            [
                InlineKeyboardButton(text="?? На неделю", callback_data="horoscope_week"),
                InlineKeyboardButton(text="?? На месяц", callback_data="horoscope_month")
            ]
        ]
    )

# =====================
# FLASK ROUTES (ПОСЛЕ СОЗДАНИЯ APP)
# =====================

@app.route(ADMIN_PATH)
def admin_panel():
    """Веб-админка"""
    # Простая проверка (в продакшене нужно добавить аутентификацию)
    return f"""
    <html>
    <head>
        <title>Админ-панель нумеробота</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            .stats {{ background: #f5f5f5; padding: 20px; border-radius: 10px; }}
            h1 {{ color: #333; }}
            .btn {{ display: inline-block; padding: 10px 20px; background: #4CAF50; color: white; text-decoration: none; border-radius: 5px; margin: 5px; }}
        </style>
    </head>
    <body>
        <h1>?? Админ-панель нумеробота</h1>
        
        <div class="stats">
            <h2>?? Статистика:</h2>
            <p><strong>Пользователей:</strong> {stats.get('total_users', 0)}</p>
            <p><strong>Анализов выполнено:</strong> {stats.get('calculations', 0) + stats.get('compatibility_checks', 0) + stats.get('forecasts', 0) + stats.get('horoscopes', 0)}</p>
            <p><strong>Прогнозов:</strong> {stats.get('forecasts', 0)}</p>
            <p><strong>Гороскопов:</strong> {stats.get('horoscopes', 0)}</p>
        </div>
        
        <h2>?? Действия:</h2>
        <a href="/" class="btn">?? Главная</a>
        <a href="/ping" class="btn">?? Ping</a>
        <a href="/admin/stats" class="btn">?? Детальная статистика</a>
        
        <h2>?? Файлы:</h2>
        <p><a href="/admin/users.json" target="_blank">users.json</a> ({len(users)} пользователей)</p>
        <p><a href="/admin/stats.json" target="_blank">stats.json</a></p>
        <p><a href="/admin/personalization.json" target="_blank">personalization.json</a></p>
    </body>
    </html>
    """

@app.route("/admin/stats.json")
def admin_stats_json():
    return json.dumps(stats, ensure_ascii=False, indent=2)

@app.route("/admin/users.json")
def admin_users_json():
    return json.dumps(users, ensure_ascii=False, indent=2)

@app.route("/admin/personalization.json")
def admin_personalization_json():
    return json.dumps(personalization, ensure_ascii=False, indent=2)

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
# UTILITY FUNCTIONS
# =====================

def is_date(text: str) -> bool:
    try:
        datetime.strptime(text, "%d.%m.%Y")
        return True
    except:
        return False

def format_user_name(user: types.User) -> str:
    """Форматирование имени пользователя"""
    name_parts = []
    if user.first_name:
        name_parts.append(user.first_name)
    if user.last_name:
        name_parts.append(user.last_name)
    return " ".join(name_parts) if name_parts else "Дорогой друг"

# =====================
# HANDLERS
# =====================

@router.message(CommandStart())
async def start(m: Message):
    user_id = m.from_user.id
    username = m.from_user.username or ""
    first_name = m.from_user.first_name or ""
    last_name = m.from_user.last_name or ""
    
    # Обновляем информацию о пользователе
    if str(user_id) not in users:
        users[str(user_id)] = {
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "joined": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_active": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        save_users(users)
    
    # Персонализированное приветствие
    user_name = format_user_name(m.from_user)
    
    welcome_messages = [
        f"? Приветствую, {user_name}! Я — ваш личный нумеролог.",
        f"?? Добро пожаловать, {user_name}! Готовы раскрыть тайны чисел?",
        f"?? Здравствуйте, {user_name}! Числа расскажут многое о вашем пути.",
        f"?? Рад видеть вас, {user_name}! Давайте исследуем мир нумерологии вместе."
    ]
    
    welcome_text = random.choice(welcome_messages) + "\n\n" + \
                  "Выберите, что вас интересует:"
    
    await m.answer(
        welcome_text,
        reply_markup=main_menu(user_id)
    )
    
    # Обновляем статистику
    PersonalizationEngine.update_user_profile(user_id, "start")

@router.message(lambda m: m.text == "? Мой нумерологический портрет")
async def numerology_portrait(m: Message):
    user_id = m.from_user.id
    PersonalizationEngine.update_user_profile(user_id, "portrait_request")
    
    await m.answer(
        "? *Нумерологический портрет*\n\n"
        "Введите вашу дату рождения в формате ДД.ММ.ГГГГ\n\n"
        "Например: 15.05.1990\n\n"
        "Я рассчитаю:\n"
        "• Число жизненного пути ???\n"
        "• Число судьбы ??\n"
        "• Число характера ??\n"
        "• Сильные стороны ??\n"
        "• Рекомендации для роста ??",
        parse_mode="Markdown",
        reply_markup=main_menu(user_id)
    )

@router.message(lambda m: m.text == "?? Совместимость партнеров")
async def compatibility_main(m: Message):
    user_id = m.from_user.id
    PersonalizationEngine.update_user_profile(user_id, "compatibility_request_general")
    
    await m.answer(
        "?? *Совместимость партнеров*\n\n"
        "Введите две даты рождения через пробел:\n\n"
        "*Формат:* ДД.ММ.ГГГГ ДД.ММ.ГГГГ\n"
        "*Пример:* 15.05.1990 20.08.1985\n\n"
        "Я проанализирую вашу общую совместимость:\n"
        "• Энергетическую гармонию ?\n"
        "• Эмоциональное соответствие ??\n"
        "• Интеллектуальную связь ??\n"
        "• Практическую совместимость ??\n"
        "• Сильные стороны союза ??\n"
        "• Рекомендации для развития ??",
        parse_mode="Markdown",
        reply_markup=main_menu(user_id)
    )

@router.message(lambda m: m.text == "?? Прогноз на период")
async def forecast_main(m: Message):
    user_id = m.from_user.id
    PersonalizationEngine.update_user_profile(user_id, "forecast_request")
    
    await m.answer(
        "?? *Прогноз на период*\n\n"
        "Выберите период для анализа:",
        parse_mode="Markdown",
        reply_markup=forecast_period_menu()
    )

@router.callback_query(lambda c: c.data.startswith("forecast_"))
async def process_forecast_period(callback: types.CallbackQuery):
    period = callback.data.split("_")[1]
    
    # Сохраняем период в пользовательских данных
    user_id = callback.from_user.id
    if str(user_id) not in users:
        users[str(user_id)] = {}
    
    users[str(user_id)]["last_forecast_period"] = period
    save_users(users)  # Не забудьте сохранить!
    
    period_names = {
        "week": "неделю ?",
        "month": "месяц ??",
        "quarter": "3 месяца ??",
        "year": "год ??"
    }
    
    await callback.message.edit_text(
        f"?? *Прогноз на {period_names[period]}*\n\n"
        "Введите вашу дату рождения в формате ДД.ММ.ГГГГ\n\n"
        "Я сделаю нумерологический прогноз:\n"
        "• Благоприятные периоды ??\n"
        "• Возможные вызовы ??\n"
        "• Рекомендации для успеха ??\n"
        "• Фокусные области ??",
        parse_mode="Markdown"
    )
    
    PersonalizationEngine.update_user_profile(
        callback.from_user.id, 
        f"forecast_{period}"
    )
    
    await callback.answer()
    
@router.message(lambda m: m.text == "?? Персональный гороскоп")
async def horoscope_main(m: Message):
    user_id = m.from_user.id
    PersonalizationEngine.update_user_profile(user_id, "horoscope_request")
    
    await m.answer(
        "?? *Персональный гороскоп*\n\n"
        "Выберите период для гороскопа:",
        parse_mode="Markdown",
        reply_markup=horoscope_type_menu()
    )

@router.callback_query(lambda c: c.data.startswith("horoscope_"))
async def process_horoscope_type(callback: types.CallbackQuery):
    h_type = callback.data.split("_")[1]
    
    type_names = {
        "today": "сегодня ??",
        "tomorrow": "завтра ??",
        "week": "неделю ??",
        "month": "месяц ??"
    }
    
    await callback.message.edit_text(
        f"?? *Гороскоп на {type_names[h_type]}*\n\n"
        "Введите вашу дату рождения в формате ДД.ММ.ГГГГ\n\n"
        "Я создам персонализированный гороскоп:\n"
        "• Общий настрой дня ??\n"
        "• Сфера удачи ??\n"
        "• Совет от чисел ??\n"
        "• Число дня ??",
        parse_mode="Markdown"
    )
    
    PersonalizationEngine.update_user_profile(
        callback.from_user.id, 
        f"horoscope_{h_type}"
    )
    
    await callback.answer()

@router.message(lambda m: m.text == "?? Моя аффирмация дня")
async def daily_affirmation(m: Message):
    user_id = m.from_user.id
    
    await m.answer(
        "?? *Моя аффирмация дня*\n\n"
        "Введите вашу дату рождения в формате ДД.ММ.ГГГГ\n\n"
        "Я создам для вас персональную аффирмацию —\n"
        "утверждение, которое поможет настроиться\n"
        "на удачный день и привлечь позитивную энергию.",
        parse_mode="Markdown",
        reply_markup=main_menu(user_id)
    )
    
    PersonalizationEngine.update_user_profile(user_id, "affirmation_request")

@router.message(lambda m: m.text == "?? Админ-панель")
async def admin_button_handler(m: Message):
    user_id = m.from_user.id
    
    if user_id in ADMIN_IDS:
        await m.answer(
            "?? *Панель администратора*\n\n"
            "Выберите действие:",
            parse_mode="Markdown",
            reply_markup=admin_menu()
        )
    else:
        await m.answer(
            "Эта функция доступна только администраторам",
            reply_markup=main_menu(user_id)
        )

# Добавьте после admin_button_handler:

@router.message(lambda m: m.text == "?? Статистика")
async def admin_stats(m: Message):
    user_id = m.from_user.id
    
    if user_id not in ADMIN_IDS:
        await m.answer("Доступ запрещен", reply_markup=main_menu(user_id))
        return
    
    # Формируем статистику
    total_calculations = (
        stats.get("calculations", 0) + 
        stats.get("compatibility_checks", 0) + 
        stats.get("forecasts", 0) + 
        stats.get("horoscopes", 0)
    )
    
    stats_text = f"""
?? *Статистика бота*

?? Пользователей всего: {stats.get("total_users", 0)}
?? Активных пользователей: {stats.get("active_users", 0)}

?? *Анализов выполнено:*
• Нумерологических портретов: {stats.get("calculations", 0)}
• Проверок совместимости: {stats.get("compatibility_checks", 0)}
• Прогнозов на периоды: {stats.get("forecasts", 0)}
• Персональных гороскопов: {stats.get("horoscopes", 0)}
• *Всего анализов:* {total_calculations}

?? *За сегодня ({datetime.now().strftime("%d.%m.%Y")}):*
• Новых пользователей: {stats.get("daily_stats", {}).get("new_users", 0)}
• Выполнено анализов: {stats.get("daily_stats", {}).get("calculations", 0)}

?? *Популярные функции:*
1. {max(stats.get("popular_features", {}), key=stats.get("popular_features", {}).get, default="Нет данных")}
2. {sorted(stats.get("popular_features", {}).items(), key=lambda x: x[1], reverse=True)[1][0] if len(stats.get("popular_features", {})) > 1 else "Нет данных"}
    """
    
    await m.answer(stats_text, parse_mode="Markdown", reply_markup=admin_menu())

@router.message(lambda m: m.text == "?? Пользователи")
async def admin_users(m: Message):
    user_id = m.from_user.id
    
    if user_id not in ADMIN_IDS:
        await m.answer("Доступ запрещен", reply_markup=main_menu(user_id))
        return
    
    total_users = len(users)
    recent_users = []
    
    # Получаем последних 5 пользователей
    for uid, user_data in list(users.items())[-5:]:
        username = user_data.get("username", "без username")
        first_name = user_data.get("first_name", "")
        last_name = user_data.get("last_name", "")
        name = f"{first_name} {last_name}".strip() or f"Пользователь {uid[-4:]}"
        joined = user_data.get("joined", "неизвестно")
        
        recent_users.append(f"• {name} (@{username}) - {joined}")
    
    users_text = f"""
?? *Информация о пользователях*

?? Всего пользователей: {total_users}

?? *Последние 5 пользователей:*
{chr(10).join(recent_users) if recent_users else "• Нет данных"}

?? Файл с пользователями: `users.json`
?? Размер файла: {Path("users.json").stat().st_size if Path("users.json").exists() else 0} байт
    """
    
    await m.answer(users_text, parse_mode="Markdown", reply_markup=admin_menu())

@router.message(lambda m: m.text == "?? Рассылка")
async def admin_broadcast(m: Message):
    user_id = m.from_user.id
    
    if user_id not in ADMIN_IDS:
        await m.answer("Доступ запрещен", reply_markup=main_menu(user_id))
        return
    
    await m.answer(
        "?? *Функция рассылки*\n\n"
        "Эта функция находится в разработке.\n\n"
        "Скоро вы сможете отправлять сообщения всем пользователям бота.",
        parse_mode="Markdown",
        reply_markup=admin_menu()
    )

@router.message(lambda m: m.text == "?? В главное меню")
async def back_to_main(m: Message):
    user_id = m.from_user.id
    await m.answer(
        "Возвращаемся в главное меню:",
        reply_markup=main_menu(user_id)
    )

@router.message(lambda m: m.text == "?? О боте")
async def about_bot(m: Message):
    user_id = m.from_user.id
    
    about_text = """
?? *Нумерологический бот с AI*

Я — ваш персональный нумеролог, использующий искусственный интеллект для глубокого анализа.

? *Что я умею:*
• Создавать подробный нумерологический портрет
• Анализировать совместимость для разных типов отношений
• Делать прогнозы на выбранный период
• Генерировать персональные гороскопы
• Создавать аффирмации для вашего дня

?? *Мой подход:*
Я сочетаю древнюю мудрость нумерологии с современными психологическими знаниями. Все анализы уникальны и создаются специально для вас.

?? *Статистика:*
• Пользователей: {total_users}
• Анализов выполнено: {total_analyses}

?? *Совет:* Регулярно обращайтесь за анализом — числа могут раскрывать новые грани вашего пути!

?? *Веб-админка:* {base_url}{admin_path}
""".format(
        total_users=stats["total_users"],
        total_analyses=stats["calculations"] + stats["compatibility_checks"] + stats["forecasts"],
        base_url=BASE_URL,
        admin_path=ADMIN_PATH
    )
    
    await m.answer(about_text, parse_mode="Markdown", reply_markup=main_menu(user_id))

@router.message(lambda m: m.text == "?? В главное меню")
async def back_to_main(m: Message):
    user_id = m.from_user.id
    await m.answer(
        "Возвращаемся в главное меню:",
        reply_markup=main_menu(user_id)
    )

# =====================
# MAIN ANALYZERS
# =====================

@router.message(lambda m: is_date(m.text))
async def date_analysis_handler(m: Message):
    """Универсальный обработчик дат с маршрутизацией"""
    user_id = m.from_user.id
    date_str = m.text
    
    print(f"=== ОБРАБОТКА ДАТЫ ===")
    print(f"Пользователь: {user_id}")
    print(f"Введенная дата: {date_str}")
    
    # Получаем историю действий пользователя
    user_history = personalization["user_history"].get(str(user_id), {"actions": []})
    
    print(f"История действий: {user_history.get('actions', [])}")
    
    if not user_history["actions"]:
        print("Нет истории действий > портрет")
        await process_portrait(m, date_str)
        return
    
    # Получаем последнее действие
    last_action = user_history["actions"][-1]["action"]
    print(f"Последнее действие: {last_action}")
    
    # Маршрутизация по последнему действию
    if "forecast" in last_action:
        print("Маршрутизация > прогноз")
        await forecast_handler(m, date_str, last_action)
    elif "horoscope" in last_action:
        print("Маршрутизация > гороскоп")
        await horoscope_handler(m, date_str, last_action)
    elif last_action == "affirmation_request":
        print("Маршрутизация > аффирмация")
        await affirmation_handler(m, date_str)
    elif last_action == "portrait_request":
        print("Маршрутизация > портрет")
        await process_portrait(m, date_str)
    else:
        print("Маршрутизация > портрет (по умолчанию)")
        await process_portrait(m, date_str)

async def process_portrait(m: Message, date_str: str):
    """Обработка нумерологического портрета"""
    user_id = m.from_user.id
    
    await m.answer("? Анализирую ваш нумерологический портрет...")
    
    # Обновляем статистику
    if "calculations" in stats:
        stats["calculations"] += 1
    save_stats(stats)
    
    # Получаем число жизненного пути
    life_number = NumerologyFeatures.calculate_life_path_number(date_str)
    
    # Создаем промпт для AI
    prompt = f"""
Ты — профессиональный нумеролог-консультант премиум-уровня. Создай подробный нумерологический портрет для человека, родившегося {date_str}.
Число жизненного пути: {life_number if life_number else "расчет не удался"}.

Включи следующие разделы:
1. Ключевое число и его значение
2. Основные черты характера
3. Сильные стороны личности
4. Зоны для развития
5. Профессиональные рекомендации
6. Советы по отношениям

Будь вдохновляющим, но реалистичным. Пиши от первого лица, как если бы это был личный отчет.
"""
    
    # Получаем анализ от AI
    analysis = await ask_groq(prompt, "detailed")
    
    # Персонализируем ответ
    personalized_analysis = PersonalizationEngine.personalize_response(user_id, analysis, "portrait")
    
    # Добавляем аффирмацию в конце
    affirmation = NumerologyFeatures.generate_daily_affirmation(date_str)
    
    final_response = f"""
? *Ваш нумерологический портрет* ?

{personalized_analysis}

?? *Аффирмация дня:*
{affirmation}

?? *Число жизненного пути:* {life_number if life_number else "не определено"}
?? *Дата анализа:* {datetime.now().strftime("%d.%m.%Y")}
"""
    
    await m.answer(final_response, parse_mode="Markdown", reply_markup=main_menu(user_id))
    
    # Обновляем профиль пользователя
    PersonalizationEngine.update_user_profile(user_id, "portrait_analysis", {"date": date_str})

async def forecast_handler(m: Message, date_str: str, last_action: str):
    """Обработчик для прогнозов"""
    user_id = m.from_user.id
    
    # Извлекаем период из последнего действия (например: "forecast_month")
    if "_" in last_action:
        period = last_action.split("_")[1]
    else:
        period = "month"  # По умолчанию месяц
    
    period_names = {
        "week": "неделю",
        "month": "месяц",
        "quarter": "3 месяца", 
        "year": "год"
    }
    
    period_display = period_names.get(period, "месяц")
    
    await m.answer(f"?? Анализирую ваш прогноз на {period_display}...")
    
    # Обновляем статистику
    if "forecasts" in stats:
        stats["forecasts"] += 1
    save_stats(stats)
    
    # Получаем число жизненного пути
    life_number = NumerologyFeatures.calculate_life_path_number(date_str)
    
    # Текущая дата для контекста
    current_date = datetime.now().strftime("%d.%m.%Y")
    
    # Создаем промпт для прогноза
    prompt = f"""
Ты — профессиональный нумеролог-консультант премиум-уровня.
Создай подробный нумерологический прогноз на {period_display} для человека, родившегося {date_str}.
Текущая дата: {current_date}.

Число жизненного пути: {life_number if life_number else "не определено"}.

Включи следующие разделы:
1. Общая энергетика предстоящего периода ({period_display})
2. Конкретные благоприятные даты и периоды
3. Возможные вызовы и как их преодолеть
4. Рекомендации для достижения успеха
5. Сферы жизни, на которые стоит обратить особое внимание
6. Числовые вибрации, влияющие на этот период

Укажи конкретные временные рамки в своем ответе.
"""
    
    # Получаем прогноз от AI
    forecast = await ask_groq(prompt, "forecast")
    
    # Формируем финальный ответ
    final_response = f"""
?? *Ваш нумерологический прогноз* ??
*Период: {period_display.capitalize()}*
*Начало анализа: {current_date}*

{forecast}

?? *Число жизненного пути:* {life_number if life_number else "не определено"}
"""
    
    await m.answer(final_response, parse_mode="Markdown", reply_markup=main_menu(user_id))
    
    # Обновляем профиль пользователя
    PersonalizationEngine.update_user_profile(
        user_id, 
        f"forecast_generated_{period}",
        {"date": date_str, "period": period}
    )

@router.message(lambda m: len(m.text.split()) == 2 and all("." in part for part in m.text.split()))
async def compatibility_analysis_handler(m: Message):
    """Обработчик для анализа совместимости"""
    user_id = m.from_user.id
    date1, date2 = m.text.split()
    
    if not (is_date(date1) and is_date(date2)):
        await m.answer("Пожалуйста, введите даты в правильном формате: ДД.ММ.ГГГГ ДД.ММ.ГГГГ")
        return
    
    await m.answer("?? Анализирую совместимость...")
    
    # Обновляем статистику
    if "compatibility_checks" in stats:
        stats["compatibility_checks"] += 1
    save_stats(stats)
    
    # Определяем тип совместимости для внутренней логики (можно оставить)

# Создаем промпт для общего анализа
    prompt = f"""
Проанализируй общую совместимость двух людей по датам рождения:
1. {date1}
2. {date2}

Сделай комплексный анализ совместимости, включая:
- Энергетическую и эмоциональную гармонию
- Интеллектуальное соответствие
- Практические аспекты взаимоотношений
- Потенциал для долгосрочных отношений

Включи следующие разделы:
1. Общая оценка совместимости (в процентах или уровне)
2. Сильные стороны этого союза
3. Потенциальные вызовы и точки роста
4. Рекомендации для укрепления отношений
5. Совместные возможности развития
6. Сфера, где пара наиболее гармонична

Будь дипломатичным, конструктивным и давай практические, реалистичные советы.
Акцент на отношения в целом, без разделения на романтику/дружбу/бизнес.
"""

# Получаем анализ
    analysis = await ask_groq(prompt, "compatibility")
    
    # Персонализируем
    personalized_analysis = PersonalizationEngine.personalize_response(user_id, analysis, "compatibility")
    
    final_response = f"""
?? *Анализ совместимости* ??

*Даты:*
• {date1}
• {date2}

{personalized_analysis}

?? *Числа жизненного пути:*
• {NumerologyFeatures.calculate_life_path_number(date1) or '?'}
• {NumerologyFeatures.calculate_life_path_number(date2) or '?'}
"""
    await m.answer(final_response, parse_mode="Markdown", reply_markup=main_menu(user_id))
    
    PersonalizationEngine.update_user_profile(user_id, "compatibility_analysis", {"dates": [date1, date2]})
    
async def horoscope_handler(m: Message, date_str: str, last_action: str):
    """Обработчик для гороскопов"""
    user_id = m.from_user.id
    
    # Извлекаем тип гороскопа из последнего действия
    if "_" in last_action:
        h_type = last_action.split("_")[1]
    else:
        h_type = "today"
    
    type_names = {
        "today": "сегодня",
        "tomorrow": "завтра", 
        "week": "неделю",
        "month": "месяц"
    }
    
    period_display = type_names.get(h_type, "сегодня")
    
    # Рассчитываем дату в зависимости от типа гороскопа
    today = datetime.now()
    if h_type == "today":
        target_date = today
        date_description = f"{today.strftime('%d.%m.%Y')} (сегодня)"
    elif h_type == "tomorrow":
        target_date = today + timedelta(days=1)
        date_description = f"{target_date.strftime('%d.%m.%Y')} (завтра)"
    elif h_type == "week":
        target_date_start = today
        target_date_end = today + timedelta(days=6)
        date_description = f"с {target_date_start.strftime('%d.%m.%Y')} по {target_date_end.strftime('%d.%m.%Y')} (на неделю)"
    elif h_type == "month":
        # Текущий месяц
        year = today.year
        month = today.month
        # Первый день месяца
        target_date_start = datetime(year, month, 1)
        # Последний день месяца
        if month == 12:
            target_date_end = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            target_date_end = datetime(year, month + 1, 1) - timedelta(days=1)
        date_description = f"с {target_date_start.strftime('%d.%m.%Y')} по {target_date_end.strftime('%d.%m.%Y')} (на месяц)"
    else:
        target_date = today
        date_description = f"{today.strftime('%d.%m.%Y')} (сегодня)"
    
    await m.answer(f"?? Создаю гороскоп на {period_display}...")
    
    # Обновляем статистику
    if "horoscopes" in stats:
        stats["horoscopes"] += 1
    save_stats(stats)
    
    # Получаем число жизненного пути
    life_number = NumerologyFeatures.calculate_life_path_number(date_str)
    
    # Формируем заголовок с датой
    period_header = f"{period_display.capitalize()} ({date_description})"
    
    # Создаем промпт для гороскопа
    prompt = f"""
Ты — профессиональный нумеролог-консультант премиум-уровня. 
Создай персональный нумерологический гороскоп на {period_header} для человека, родившегося {date_str}.

Текущая дата: {today.strftime("%d.%m.%Y")}.
Период анализа: {period_header}.

Число жизненного пути: {life_number if life_number else 'не определено'}.

Стиль: литературный русский, как у психолога-консультанта.
Без повторов.
Без канцелярита.

ВАЖНО:
- Не описывай расчёты.
- Не упоминай формулы и сложение чисел.
- Пиши как личный эксперт-консультант.
- Стиль: уверенный, спокойный, интеллектуальный, без мистического фанатизма.
- Обращайся к человеку на «вы».
- Без слов «дорогой человек».

Структура ответа:

1. Короткое персональное вступление (1–2 предложения) с упоминанием периода {period_header}

2. Энергия периода  
(1 абзац: общий настрой, внутреннее состояние, ритм периода с привязкой к датам)

3. Ключевые сферы периода:
- Работа и финансы (с конкретными датами или периодами внутри {period_header})
- Отношения и общение  
- Внутреннее состояние и энергия  

(по 2–3 предложения на каждую сферу с временной привязкой)

4. Возможные риски или ошибки периода  
(конкретно и практично, с привязкой к датам)

5. Совет от чисел  
(прикладной, применимый в реальной жизни)

6. Число удачи на период + его значение (1–2 предложения)

7. Короткое итоговое резюме с акцентом на период {period_header}

Запрещено использовать:
- английские слова
- транслитерацию
- слова today, period и т.п.

Обязательно:
- Для "сегодня" и "завтра" указывай конкретную дату
- Для "недели" разбивай на первую/вторую половину или по дням
- Для "месяца" разбивай на декады или недели
- Всегда упоминай временные рамки

Объём: 200–300 слов.
Без эмодзи внутри текста.
"""
    
    # Получаем гороскоп
    horoscope = await ask_groq(prompt, "horoscope")
    
    # Добавляем персональную аффирмацию
    affirmation = NumerologyFeatures.generate_daily_affirmation(date_str)
    
    final_response = f"""
?? *Ваш персональный гороскоп* ??
*На {period_header}*

{horoscope}

?? *Аффирмация дня:*
{affirmation}

? *Число жизненного пути:* {life_number if life_number else '?'}
? *Дата создания гороскопа:* {today.strftime("%d.%m.%Y %H:%M")}
"""
    
    await m.answer(final_response, parse_mode="Markdown", reply_markup=main_menu(user_id))
    
    # Обновляем профиль пользователя
    PersonalizationEngine.update_user_profile(
        user_id, 
        f"horoscope_generated_{h_type}",
        {"date": date_str, "period": h_type, "target_date": target_date.strftime("%Y-%m-%d") if h_type in ["today", "tomorrow"] else date_description}
    )

async def affirmation_handler(m: Message, date_str: str):
    """Обработчик для аффирмаций"""
    user_id = m.from_user.id
    
    # Генерируем аффирмацию
    affirmation = NumerologyFeatures.generate_daily_affirmation(date_str)
    
    # Получаем число жизненного пути для контекста
    life_number = NumerologyFeatures.calculate_life_path_number(date_str)
    
    # Создаем красивый ответ
    affirmation_text = f"""
?? *Ваша персональная аффирмация* ??

? {affirmation} ?

*Почему эта аффирмация для вас:*
Эта утверждение резонирует с энергией вашего числа жизненного пути ({life_number or '?'}).

*Как использовать:*
1. Повторяйте утром, настраиваясь на день
2. Запишите в дневник или на стикер
3. Используйте как мантру в течение дня
4. Визуализируйте, как это проявляется в вашей жизни

*Энергия на сегодня:*
Каждый день приносит новые возможности. Эта аффирмация поможет вам привлечь позитивные вибрации и оставаться в потоке.

?? *Число дня:* {random.randint(1, 9)} (символизирует энергию сегодняшнего дня)
"""
    
    await m.answer(affirmation_text, parse_mode="Markdown", reply_markup=main_menu(user_id))
    
    PersonalizationEngine.update_user_profile(user_id, "affirmation_generated", {"date": date_str})

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
    
    # Создаем необходимые файлы, если их нет
    if not USERS_FILE.exists():
        save_users({})
    if not STATS_FILE.exists():
        save_stats(load_stats())
    if not PERSONALIZATION_FILE.exists():
        save_personalization(load_personalization())
    
    set_webhook()

    Thread(target=run_flask, daemon=True).start()

    print("? Нумерологический бот запущен!")
    print(f"?? Админ-панель: {BASE_URL}{ADMIN_PATH}")
    print(f"?? Админ ID: {ADMIN_IDS[0] if ADMIN_IDS else 'Не задан'}")
    print("\n" + "="*50)
    print("?? Уникальные фичи включены:")
    print("• Нумерологический портрет с AI")
    print("• Совместимость по типам отношений")
    print("• Прогнозы на разные периоды")
    print("• Персональные гороскопы")
    print("• Аффирмации дня")
    print("• Система персонализации")
    print("="*50)
    
    loop.run_forever()
