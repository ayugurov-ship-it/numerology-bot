import os
import json
import asyncio
import aiohttp
import logging
import random
from datetime import datetime, timedelta
from pathlib import Path
from threading import Thread

try:
    import requests
    from flask import Flask, request, render_template_string
    from aiogram import Bot, Dispatcher, Router, types
    from aiogram.filters import CommandStart
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
# CONFIG
# =====================

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
BASE_URL = os.getenv("BASE_URL", "https://numerology-bot.onrender.com")
ADMIN_IDS = [260219938]  # Ваш ID

MODEL_NAME = "llama-3.1-8b-instant"
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = BASE_URL + WEBHOOK_PATH

# Системные промпты для разных типов анализа
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
# USERS STORAGE
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
# UNIQUE FEATURES
# =====================

class NumerologyCalculator:
    """Калькулятор нумерологических чисел"""
    
    @staticmethod
    def calculate_life_path(date_str: str) -> int:
        """Расчет числа жизненного пути"""
        try:
            digits = date_str.replace('.', '')
            total = sum(int(d) for d in digits)
            
            while total > 9 and total not in [11, 22, 33]:
                total = sum(int(d) for d in str(total))
            
            return total
        except:
            return None
    
    @staticmethod
    def get_compatibility_level(date1: str, date2: str) -> str:
        """Оценка уровня совместимости"""
        num1 = NumerologyCalculator.calculate_life_path(date1)
        num2 = NumerologyCalculator.calculate_life_path(date2)
        
        if not num1 or not num2:
            return "средняя"
        
        compatible_pairs = [(1, 9), (2, 6), (3, 5), (4, 8), (7, 7)]
        pair = (min(num1, num2), max(num1, num2))
        
        if pair in compatible_pairs:
            return "высокая"
        elif abs(num1 - num2) <= 2:
            return "хорошая"
        else:
            return "средняя"
    
    @staticmethod
    def generate_affirmation(date_str: str) -> str:
        """Генерация персональной аффирмации"""
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
        "max_tokens": 1000
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    return "⚠️ Произошла ошибка при обработке запроса. Попробуйте позже."
                    
                result = await resp.json()
                return result["choices"][0]["message"]["content"]

    except Exception as e:
        return "⚠️ Произошла ошибка при обработке запроса. Попробуйте позже."

# =====================
# BOT INIT
# =====================

try:
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()
    router = Router()
    dp.include_router(router)
except Exception as e:
    print(f"❌ ERROR initializing bot: {e}")
    exit(1)

# =====================
# BEAUTIFUL KEYBOARDS
# =====================

def main_menu(user_id: int = None):
    """Главное меню с красивыми кнопками"""
    keyboard = [
        [KeyboardButton(text="✨ Нумеропортрет")],
        [KeyboardButton(text="💞 Совместимость")],
        [KeyboardButton(text="🌟 Гороскоп дня")],
        [KeyboardButton(text="📅 Прогноз на период")],
        [KeyboardButton(text="🔄 Аффирмация")]
    ]
    
    # Кнопка админа только для вас
    if user_id in ADMIN_IDS:
        keyboard.append([KeyboardButton(text="👑 Админ")])
    
    keyboard.append([KeyboardButton(text="ℹ️ Помощь")])
    
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        input_field_placeholder="Выберите действие..."
    )

def period_menu():
    """Инлайн-меню для выбора периода"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📅 На месяц", callback_data="period_month"),
                InlineKeyboardButton(text="📆 На 3 месяца", callback_data="period_quarter")
            ],
            [
                InlineKeyboardButton(text="🎯 На год", callback_data="period_year"),
                InlineKeyboardButton(text="✨ На неделю", callback_data="period_week")
            ]
        ]
    )

def horoscope_menu():
    """Инлайн-меню для гороскопа"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🌞 Сегодня", callback_data="horoscope_today"),
                InlineKeyboardButton(text="🌙 Завтра", callback_data="horoscope_tomorrow")
            ],
            [
                InlineKeyboardButton(text="📅 На неделю", callback_data="horoscope_week"),
                InlineKeyboardButton(text="📆 На месяц", callback_data="horoscope_month")
            ]
        ]
    )

def compatibility_menu():
    """Инлайн-меню для типа совместимости"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💑 Романтика", callback_data="comp_love"),
                InlineKeyboardButton(text="💼 Бизнес", callback_data="comp_business")
            ],
            [
                InlineKeyboardButton(text="👥 Дружба", callback_data="comp_friends"),
                InlineKeyboardButton(text="👨‍👩‍👧‍👦 Семья", callback_data="comp_family")
            ]
        ]
    )

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
            "joined": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_active": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        save_users(users)
    
    stats["total_users"] = len(users)
    save_stats(stats)
    
    # Персонализированное приветствие
    greetings = [
        f"✨ Приветствую, {m.from_user.first_name or 'друг'}! Готовы раскрыть тайны чисел?",
        f"🌟 Добро пожаловать, {m.from_user.first_name or 'путешественник'}! Числа ждут анализа.",
        f"🔮 Здравствуйте, {m.from_user.first_name or 'искатель'}! Давайте исследуем вашу нумерологию."
    ]
    
    await m.answer(
        random.choice(greetings) + "\n\nВыберите действие:",
        reply_markup=main_menu(user_id)
    )

# =====================
# MENU HANDLERS
# =====================

@router.message(lambda m: m.text == "✨ Нумеропортрет")
async def portrait_handler(m: Message):
    await m.answer(
        "✨ *Нумерологический портрет*\n\n"
        "Введите вашу дату рождения в формате ДД.ММ.ГГГГ\n\n"
        "*Пример:* 15.05.1990\n\n"
        "Я создам подробный анализ вашей личности на основе чисел:"
        "\n• Число жизненного пути"
        "\n• Число судьбы"
        "\n• Сильные стороны"
        "\n• Рекомендации для роста",
        parse_mode="Markdown",
        reply_markup=main_menu(m.from_user.id)
    )

@router.message(lambda m: m.text == "💞 Совместимость")
async def compatibility_handler(m: Message):
    await m.answer(
        "💞 *Нумерологическая совместимость*\n\n"
        "Выберите тип отношений для анализа:",
        reply_markup=compatibility_menu()
    )

@router.callback_query(lambda c: c.data.startswith("comp_"))
async def process_compatibility_type(callback: types.CallbackQuery):
    comp_type = callback.data.split("_")[1]
    
    type_names = {
        "love": "романтических отношений 💑",
        "business": "делового партнерства 💼", 
        "friends": "дружбы 👥",
        "family": "семейных отношений 👨‍👩‍👧‍👦"
    }
    
    await callback.message.edit_text(
        f"💞 *Совместимость для {type_names[comp_type]}*\n\n"
        "Введите две даты рождения через пробел:\n\n"
        "*Формат:* ДД.ММ.ГГГГ ДД.ММ.ГГГГ\n"
        "*Пример:* 15.05.1990 20.08.1985\n\n"
        "Я проанализирую энергетическую совместимость.",
        parse_mode="Markdown"
    )
    await callback.answer()

@router.message(lambda m: m.text == "🌟 Гороскоп дня")
async def horoscope_handler(m: Message):
    await m.answer(
        "🌟 *Персональный гороскоп*\n\n"
        "Выберите период для гороскопа:",
        reply_markup=horoscope_menu()
    )

@router.callback_query(lambda c: c.data.startswith("horoscope_"))
async def process_horoscope_period(callback: types.CallbackQuery):
    period = callback.data.split("_")[1]
    
    period_names = {
        "today": "сегодня 🌞",
        "tomorrow": "завтра 🌙", 
        "week": "неделю 📅",
        "month": "месяц 📆"
    }
    
    await callback.message.edit_text(
        f"🌟 *Гороскоп на {period_names[period]}*\n\n"
        "Введите вашу дату рождения:\n\n"
        "*Формат:* ДД.ММ.ГГГГ\n"
        "*Пример:* 15.05.1990\n\n"
        "Я создам персонализированный нумерологический гороскоп.",
        parse_mode="Markdown"
    )
    await callback.answer()

@router.message(lambda m: m.text == "📅 Прогноз на период")
async def forecast_handler(m: Message):
    await m.answer(
        "📅 *Нумерологический прогноз*\n\n"
        "Выберите период для прогноза:",
        reply_markup=period_menu()
    )

@router.callback_query(lambda c: c.data.startswith("period_"))
async def process_forecast_period(callback: types.CallbackQuery):
    period = callback.data.split("_")[1]
    
    period_names = {
        "week": "неделю ✨",
        "month": "месяц 📅", 
        "quarter": "3 месяца 📆",
        "year": "год 🎯"
    }
    
    await callback.message.edit_text(
        f"📅 *Прогноз на {period_names[period]}*\n\n"
        "Введите вашу дату рождения:\n\n"
        "*Формат:* ДД.ММ.ГГГГ\n"
        "*Пример:* 15.05.1990\n\n"
        "Я сделаю нумерологический прогноз для выбранного периода.",
        parse_mode="Markdown"
    )
    await callback.answer()

@router.message(lambda m: m.text == "🔄 Аффирмация")
async def affirmation_handler(m: Message):
    await m.answer(
        "🔄 *Персональная аффирмация*\n\n"
        "Введите вашу дату рождения:\n\n"
        "*Формат:* ДД.ММ.ГГГГ\n"
        "*Пример:* 15.05.1990\n\n"
        "Я создам для вас аффирмацию —\n"
        "утверждение, которое поможет настроиться на удачный день.",
        parse_mode="Markdown",
        reply_markup=main_menu(m.from_user.id)
    )

@router.message(lambda m: m.text == "👑 Админ")
async def admin_handler(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        await m.answer("Эта функция доступна только администраторам")
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

🆔 Ваш ID: {m.from_user.id}

*Последние 5 пользователей:*
"""
    
    # Показываем последних пользователей
    user_items = list(users.items())[-5:]
    for user_id, user_data in user_items:
        admin_text += f"\n• {user_data.get('first_name', 'Неизвестно')} (@{user_data.get('username', 'нет')})"
    
    await m.answer(admin_text, parse_mode="Markdown", reply_markup=main_menu(m.from_user.id))

@router.message(lambda m: m.text == "ℹ️ Помощь")
async def help_handler(m: Message):
    help_text = """
🌟 *Нумерологический бот с AI*

Я — ваш персональный нумеролог, использующий искусственный интеллект.

✨ *Доступные функции:*

1. *✨ Нумеропортрет* — глубокий анализ личности по дате рождения
2. *💞 Совместимость* — анализ отношений для разных сфер жизни
3. *🌟 Гороскоп дня* — нумерологический гороскоп на период
4. *📅 Прогноз на период* — прогноз на неделю/месяц/год
5. *🔄 Аффирмация* — персональное утверждение на день

📋 *Как пользоваться:*
1. Выберите функцию в меню
2. Следуйте инструкциям бота
3. Получите персонализированный анализ

🔮 *Формат даты:* ДД.ММ.ГГГГ (например, 15.05.1990)
💡 *Совет:* Чем точнее данные, тем точнее анализ!

📊 *Статистика:* {} пользователей уже доверили мне свои числа!
""".format(stats['total_users'])
    
    await m.answer(help_text, parse_mode="Markdown", reply_markup=main_menu(m.from_user.id))

# =====================
# ANALYSIS HANDLERS
# =====================

def is_date(text: str) -> bool:
    try:
        datetime.strptime(text, "%d.%m.%Y")
        return True
    except:
        return False

@router.message(lambda m: is_date(m.text))
async def process_date(m: Message):
    """Обработка даты рождения"""
    user_id = m.from_user.id
    date_str = m.text
    
    await m.answer("✨ Анализирую ваш нумерологический портрет...")
    
    # Обновляем статистику
    stats["calculations"] = stats.get("calculations", 0) + 1
    today = datetime.now().strftime("%Y-%m-%d")
    if "daily_stats" not in stats:
        stats["daily_stats"] = {}
    stats["daily_stats"][today] = stats["daily_stats"].get(today, 0) + 1
    save_stats(stats)
    
    # Получаем число жизненного пути
    life_number = NumerologyCalculator.calculate_life_path(date_str)
    
    # Создаем промпт
    prompt = f"""
Создай подробный нумерологический портрет для человека, родившегося {date_str}.
Число жизненного пути: {life_number if life_number else "не определено"}.

Включи:
1. Ключевые числа и их значения
2. Основные черты характера
3. Сильные стороны
4. Зоны для развития
5. Профессиональные рекомендации
6. Советы по отношениям
"""
    
    analysis = await ask_groq(prompt, "portrait")
    
    # Добавляем аффирмацию
    affirmation = NumerologyCalculator.generate_affirmation(date_str)
    
    response = f"""
✨ *Ваш нумерологический портрет* ✨

*Дата рождения:* {date_str}
*Число жизненного пути:* {life_number if life_number else "не определено"}

{analysis}

🔄 *Аффирмация дня:*
{affirmation}
"""
    
    await m.answer(response, parse_mode="Markdown", reply_markup=main_menu(user_id))

@router.message(lambda m: len(m.text.split()) == 2 and all("." in part for part in m.text.split()[:2]))
async def process_compatibility(m: Message):
    """Обработка совместимости"""
    user_id = m.from_user.id
    date1, date2 = m.text.split()[:2]
    
    await m.answer("💞 Анализирую совместимость...")
    
    # Обновляем статистику
    stats["compatibility_checks"] = stats.get("compatibility_checks", 0) + 1
    today = datetime.now().strftime("%Y-%m-%d")
    if "daily_stats" not in stats:
        stats["daily_stats"] = {}
    stats["daily_stats"][today] = stats["daily_stats"].get(today, 0) + 1
    save_stats(stats)
    
    # Получаем уровень совместимости
    compat_level = NumerologyCalculator.get_compatibility_level(date1, date2)
    
    # Создаем промпт
    prompt = f"""
Проанализируй нумерологическую совместимость двух людей:
1. Дата рождения: {date1}
2. Дата рождения: {date2}

Уровень совместимости: {compat_level}

Дайте подробный анализ:
1. Общая оценка совместимости
2. Сильные стороны пары
3. Потенциальные вызовы
4. Рекомендации для гармонии
5. Совместные возможности
"""
    
    analysis = await ask_groq(prompt, "compatibility")
    
    response = f"""
💞 *Анализ совместимости* 💞

*Даты:*
• {date1}
• {date2}

*Уровень совместимости:* {compat_level}

{analysis}

🔢 *Числа жизненного пути:*
• {NumerologyCalculator.calculate_life_path(date1) or '?'}
• {NumerologyCalculator.calculate_life_path(date2) or '?'}
"""
    
    await m.answer(response, parse_mode="Markdown", reply_markup=main_menu(user_id))

# =====================
# FORECAST & HOROSCOPE HANDLERS
# =====================

@router.message(lambda m: m.text and is_date(m.text.split()[0]))
async def process_forecast_or_horoscope(m: Message):
    """Обработка прогнозов и гороскопов"""
    user_id = m.from_user.id
    date_str = m.text
    
    # Определяем тип запроса по контексту
    text_lower = m.text.lower()
    if any(word in text_lower for word in ["завтра", "сегодня", "неделя", "месяц", "гороскоп"]):
        # Это гороскоп
        await process_horoscope_simple(m, date_str, user_id)
    else:
        # Это прогноз
        await process_forecast_simple(m, date_str, user_id)

async def process_horoscope_simple(m: Message, date_str: str, user_id: int):
    """Упрощенный обработчик гороскопа"""
    await m.answer("🌟 Создаю нумерологический гороскоп...")
    
    # Обновляем статистику
    stats["horoscopes"] = stats.get("horoscopes", 0) + 1
    today = datetime.now().strftime("%Y-%m-%d")
    if "daily_stats" not in stats:
        stats["daily_stats"] = {}
    stats["daily_stats"][today] = stats["daily_stats"].get(today, 0) + 1
    save_stats(stats)
    
    # Создаем промпт
    prompt = f"""
Создай нумерологический гороскоп на сегодня для человека, родившегося {date_str}.
Число жизненного пути: {NumerologyCalculator.calculate_life_path(date_str) or 'не определено'}.

Включи:
1. Общую атмосферу дня
2. Сферу удачи
3. Совет от чисел
4. Что следует делать сегодня
5. Чего лучше избегать
"""
    
    horoscope = await ask_groq(prompt, "horoscope")
    
    # Добавляем аффирмацию
    affirmation = NumerologyCalculator.generate_affirmation(date_str)
    
    response = f"""
🌟 *Ваш нумерологический гороскоп* 🌟

*Дата рождения:* {date_str}
*Период:* сегодня

{horoscope}

🔄 *Аффирмация дня:*
{affirmation}

✨ *Число жизненного пути:* {NumerologyCalculator.calculate_life_path(date_str) or '?'}
"""
    
    await m.answer(response, parse_mode="Markdown", reply_markup=main_menu(user_id))

async def process_forecast_simple(m: Message, date_str: str, user_id: int):
    """Упрощенный обработчик прогноза"""
    await m.answer("📅 Создаю нумерологический прогноз...")
    
    # Обновляем статистику
    stats["forecasts"] = stats.get("forecasts", 0) + 1
    today = datetime.now().strftime("%Y-%m-%d")
    if "daily_stats" not in stats:
        stats["daily_stats"] = {}
    stats["daily_stats"][today] = stats["daily_stats"].get(today, 0) + 1
    save_stats(stats)
    
    # Создаем промпт
    prompt = f"""
Создай нумерологический прогноз на месяц для человека, родившегося {date_str}.
Число жизненного пути: {NumerologyCalculator.calculate_life_path(date_str) or 'не определено'}.

Сделай прогноз на ближайший месяц, включив:
1. Общую энергетику периода
2. Благоприятные возможности
3. Возможные вызовы
4. Рекомендации для успеха
5. Фокусные области для развития
"""
    
    forecast = await ask_groq(prompt, "forecast")
    
    # Добавляем аффирмацию
    affirmation = NumerologyCalculator.generate_affirmation(date_str)
    
    response = f"""
📅 *Ваш нумерологический прогноз* 📅

*Дата рождения:* {date_str}
*Период:* ближайший месяц

{forecast}

🔄 *Аффирмация:*
{affirmation}

✨ *Число жизненного пути:* {NumerologyCalculator.calculate_life_path(date_str) or '?'}
"""
    
    await m.answer(response, parse_mode="Markdown", reply_markup=main_menu(user_id))

# =====================
# AFFIRMATION HANDLER
# =====================

@router.message(lambda m: is_date(m.text))
async def process_affirmation(m: Message):
    """Обработка запроса на аффирмацию"""
    user_id = m.from_user.id
    date_str = m.text
    
    # Генерируем аффирмацию
    affirmation = NumerologyCalculator.generate_affirmation(date_str)
    
    # Получаем число жизненного пути для контекста
    life_number = NumerologyCalculator.calculate_life_path(date_str)
    
    response = f"""
🔄 *Ваша персональная аффирмация* 🔄

✨ *{affirmation}* ✨

*Почему именно эта аффирмация:*
Она резонирует с энергией вашего числа жизненного пути ({life_number or '?'}), 
помогая усилить ваши природные качества и привлечь нужные энергии.

*Как использовать:*
1. Повторяйте утром, настраиваясь на день
2. Запишите и разместите на видном месте
3. Используйте как мантру в течение дня
4. Визуализируйте, как это проявляется

🌟 *Число дня:* {random.randint(1, 9)} (энергия сегодняшнего дня)
"""
    
    await m.answer(response, parse_mode="Markdown", reply_markup=main_menu(user_id))

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

@app.route("/health")
def health():
    return {
        "status": "healthy",
        "bot": BOT_TOKEN is not None,
        "users": len(users),
        "timestamp": datetime.now().isoformat()
    }

@app.route("/admin")
def admin():
    """Веб-админка"""
    today = datetime.now().strftime("%Y-%m-%d")
    
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Админ-панель нумерологического бота</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {
                font-family: Arial, sans-serif;
                max-width: 1000px;
                margin: 0 auto;
                padding: 20px;
                background-color: #f5f5f5;
            }
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px;
                border-radius: 15px;
                margin-bottom: 30px;
                text-align: center;
            }
            .stats-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }
            .stat-card {
                background: white;
                padding: 20px;
                border-radius: 10px;
                box-shadow: 0 4px 15px rgba(0,0,0,0.1);
                text-align: center;
                transition: transform 0.3s;
            }
            .stat-card:hover {
                transform: translateY(-5px);
            }
            .stat-number {
                font-size: 42px;
                font-weight: bold;
                color: #667eea;
                margin: 10px 0;
            }
            .stat-label {
                color: #666;
                font-size: 14px;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            table {
                width: 100%;
                background: white;
                border-radius: 10px;
                overflow: hidden;
                box-shadow: 0 4px 15px rgba(0,0,0,0.1);
                margin-top: 20px;
            }
            th {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 15px;
                text-align: left;
            }
            td {
                padding: 15px;
                border-bottom: 1px solid #eee;
            }
            tr:hover {
                background-color: #f9f9f9;
            }
            .status {
                display: inline-block;
                padding: 5px 15px;
                background: #4CAF50;
                color: white;
                border-radius: 20px;
                font-size: 14px;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>👑 Админ-панель нумерологического бота</h1>
            <p>Статус: <span class="status">● Активен</span> | Обновлено: """ + datetime.now().strftime("%d.%m.%Y %H:%M") + """</p>
            <p>Админ ID: """ + str(ADMIN_IDS[0]) + """ | Webhook: """ + WEBHOOK_URL + """</p>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number">""" + str(stats.get('total_users', 0)) + """</div>
                <div class="stat-label">Пользователей</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">""" + str(stats.get('calculations', 0)) + """</div>
                <div class="stat-label">Анализов портретов</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">""" + str(stats.get('compatibility_checks', 0)) + """</div>
                <div class="stat-label">Проверок совместимости</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">""" + str(stats.get('forecasts', 0)) + """</div>
                <div class="stat-label">Прогнозов</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">""" + str(stats.get('horoscopes', 0)) + """</div>
                <div class="stat-label">Гороскопов</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">""" + str(stats['daily_stats'].get(today, 0)) + """</div>
                <div class="stat-label">Запросов сегодня</div>
            </div>
        </div>
        
        <h2>👥 Последние пользователи</h2>
        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Имя</th>
                    <th>Username</th>
                    <th>Дата регистрации</th>
                </tr>
            </thead>
            <tbody>
    """
    
    # Добавляем пользователей
    user_items = list(users.items())[-15:]
    for user_id, user_data in user_items:
        html += f"""
                <tr>
                    <td>{user_id}</td>
                    <td>{user_data.get('first_name', 'Неизвестно')}</td>
                    <td>@{user_data.get('username', 'нет')}</td>
                    <td>{user_data.get('joined', '')}</td>
                </tr>
        """
    
    html += """
            </tbody>
        </table>
        
        <div style="margin-top: 30px; padding: 20px; background: white; border-radius: 10px; box-shadow: 0 4px 15px rgba(0,0,0,0.1);">
            <h3>📈 Активность за последние 7 дней</h3>
            <p>
    """
    
    # Показываем статистику за неделю
    for i in range(6, -1, -1):
        date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        count = stats['daily_stats'].get(date, 0)
        html += f"{date}: {count} запросов<br>"
    
    html += """
            </p>
        </div>
    </body>
    </html>
    """
    
    return html

@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    try:
        data = request.get_json()
        update = types.Update(**data)

        asyncio.run_coroutine_threadsafe(
            dp.feed_update(bot, update),
            loop
        )
        return "ok"
    except:
        return "error", 500

# =====================
# EVENT LOOP
# =====================

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# =====================
# WEBHOOK SETUP
# =====================

def set_webhook():
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
        requests.post(url, json={"url": WEBHOOK_URL})
        print("✅ Webhook set:", WEBHOOK_URL)
    except Exception as e:
        print(f"⚠️ Webhook error: {e}")

# =====================
# START
# =====================

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)

if __name__ == "__main__":
    print("🚀 Starting Numerology Bot...")
    
    # Проверка переменных
    if not BOT_TOKEN:
        print("❌ ERROR: BOT_TOKEN is not set!")
        exit(1)
    if not GROQ_API_KEY:
        print("⚠️ WARNING: GROQ_API_KEY is not set! AI features will not work.")
    if not BASE_URL:
        print("❌ ERROR: BASE_URL is not set!")
        exit(1)
    
    print(f"✅ BOT_TOKEN: {'Set' if BOT_TOKEN else 'Not set'}")
    print(f"✅ GROQ_API_KEY: {'Set' if GROQ_API_KEY else 'Not set'}")
    print(f"✅ BASE_URL: {BASE_URL}")
    print(f"✅ ADMIN_IDS: {ADMIN_IDS}")
    
    # Создаем файлы если их нет
    if not USERS_FILE.exists():
        save_users({})
    if not STATS_FILE.exists():
        save_stats(load_stats())
    
    set_webhook()

    Thread(target=run_flask, daemon=True).start()

    print("✨ Нумерологический бот запущен!")
    print(f"🌐 Админ-панель: {BASE_URL}/admin")
    print(f"👑 Админ ID: {ADMIN_IDS[0]}")
    print("\n" + "="*50)
    print("🎯 Ключевые функции:")
    print("1. ✨ Нумеропортрет - глубокий анализ личности")
    print("2. 💞 Совместимость - 4 типа отношений") 
    print("3. 🌟 Гороскоп дня - на разные периоды")
    print("4. 📅 Прогноз на период - неделя/месяц/год")
    print("5. 🔄 Аффирмация - персональные утверждения")
    print("="*50)
    print("\n📊 Статус: Ожидание запросов...")
    
    loop.run_forever()
