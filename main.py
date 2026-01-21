import os
import json
import asyncio
import requests
import aiohttp
import logging
from pathlib import Path
from datetime import datetime, timedelta
from flask import Flask, request, render_template_string
from threading import Thread
from collections import defaultdict
import random
import sys

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

try:
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
    logger.error(f"Import error: {e}")
    print("Устанавливаем зависимости...")
    print("Запустите: pip install aiogram aiohttp flask")
    sys.exit(1)

# =====================
# CONFIG
# =====================

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
BASE_URL = os.getenv("BASE_URL", "https://numerology-bot-m48t.onrender.com")
ADMIN_IDS = os.getenv("ADMIN_IDS", "260219938")  # Укажите ваш ID через переменную окружения

# Обработка ADMIN_IDS
try:
    ADMIN_IDS = [int(id.strip()) for id in ADMIN_IDS.split(",") if id.strip()]
except:
    ADMIN_IDS = [123456789]  # Fallback на ваш ID

logger.info(f"Admin IDs: {ADMIN_IDS}")

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
    try:
        if USERS_FILE.exists():
            return json.loads(USERS_FILE.read_text(encoding="utf-8"))
        return {}
    except Exception as e:
        logger.error(f"Error loading users: {e}")
        return {}

def save_users(data):
    try:
        USERS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.error(f"Error saving users: {e}")

def load_stats():
    try:
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
    except Exception as e:
        logger.error(f"Error loading stats: {e}")
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
    try:
        STATS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.error(f"Error saving stats: {e}")

def load_personalization():
    try:
        if PERSONALIZATION_FILE.exists():
            return json.loads(PERSONALIZATION_FILE.read_text(encoding="utf-8"))
        return {"user_preferences": {}, "user_history": {}}
    except Exception as e:
        logger.error(f"Error loading personalization: {e}")
        return {"user_preferences": {}, "user_history": {}}

def save_personalization(data):
    try:
        PERSONALIZATION_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.error(f"Error saving personalization: {e}")

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
        try:
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
        except Exception as e:
            logger.error(f"Error updating user profile: {e}")
    
    @staticmethod
    def get_user_preferences(user_id: int) -> dict:
        """Получение предпочтений пользователя"""
        try:
            user_id_str = str(user_id)
            return personalization["user_history"].get(user_id_str, {}).get("preferences", {})
        except Exception as e:
            logger.error(f"Error getting user preferences: {e}")
            return {}
    
    @staticmethod
    def personalize_response(user_id: int, base_response: str, feature_type: str) -> str:
        """Персонализация ответа на основе истории пользователя"""
        try:
            user_history = personalization["user_history"].get(str(user_id), {})
            actions = user_history.get("actions", [])
            
            if len(actions) < 3:
                return base_response
            
            # Анализируем предыдущие интересы
            recent_actions = [a["action"] for a in actions[-5:]]
            
            # Проверяем, есть ли повторяющиеся темы
            action_counts = {}
            for action in recent_actions:
                action_counts[action] = action_counts.get(action, 0) + 1
            
            # Если пользователь часто запрашивает определенный тип анализа
            for action, count in action_counts.items():
                if count >= 2:
                    if "relationship" in action:
                        base_response = "💖 Замечаю ваш интерес к теме отношений. " + base_response
                    elif "career" in action:
                        base_response = "💼 Вижу ваш фокус на карьере. " + base_response
            
            return base_response
        except Exception as e:
            logger.error(f"Error personalizing response: {e}")
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
        except Exception as e:
            logger.error(f"Error calculating life path number: {e}")
            return None
    
    @staticmethod
    def get_compatibility_type(dates: tuple) -> str:
        """Определение типа совместимости"""
        try:
            num1 = NumerologyFeatures.calculate_life_path_number(dates[0])
            num2 = NumerologyFeatures.calculate_life_path_number(dates[1])
            
            if not num1 or not num2:
                return "general"
            
            # Определяем тип совместимости на основе чисел
            compatible_nums = {
                "romantic": [(2, 6), (3, 5), (1, 9), (4, 8)],
                "business": [(1, 8), (4, 4), (3, 9), (6, 6)],
                "friendship": [(5, 7), (2, 2), (9, 9), (1, 3)],
                "creative": [(3, 3), (7, 5), (9, 6), (2, 8)]
            }
            
            pair = (num1, num2) if num1 <= num2 else (num2, num1)
            
            for comp_type, pairs in compatible_nums.items():
                if pair in pairs:
                    return comp_type
            
            return "general"
        except Exception as e:
            logger.error(f"Error getting compatibility type: {e}")
            return "general"
    
    @staticmethod
    def generate_daily_affirmation(date_str: str) -> str:
        """Генерация персональной аффирмации на день"""
        try:
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
        except Exception as e:
            logger.error(f"Error generating affirmation: {e}")
            return "Я принимаю сегодняшний день с благодарностью и открытостью"

# =====================
# GROK API
# =====================

async def ask_groq(prompt: str, system_prompt_key: str = "default") -> str:
    if not GROQ_API_KEY:
        logger.error("GROQ_API_KEY is not set!")
        return "🔮 Извините, сервис временно недоступен. Попробуйте позже."
    
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
        "max_tokens": 1000
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"GROQ API ERROR {resp.status}: {error_text}")
                    return "🔮 Произошла ошибка при обработке запроса. Попробуйте позже."
                    
                result = await resp.json()
                return result["choices"][0]["message"]["content"]

    except asyncio.TimeoutError:
        logger.error("GROQ API timeout")
        return "🔮 Сервис временно недоступен. Попробуйте позже."
    except Exception as e:
        logger.error(f"GROQ ERROR: {e}")
        return "🔮 Произошла ошибка при обработке запроса. Попробуйте позже."

# =====================
# BOT INIT
# =====================

try:
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()
    router = Router()
    dp.include_router(router)
except Exception as e:
    logger.error(f"Error initializing bot: {e}")
    print(f"ERROR: {e}")
    sys.exit(1)

# =====================
# BEAUTIFUL KEYBOARDS
# =====================

def main_menu(user_id: int = None):
    """Создает красивое главное меню"""
    # Базовые кнопки для всех пользователей
    keyboard = [
        [KeyboardButton(text="✨ Мой нумерологический портрет")],
        [KeyboardButton(text="💞 Совместимость партнеров")],
        [KeyboardButton(text="📅 Прогноз на период")],
        [KeyboardButton(text="🌟 Персональный гороскоп")],
        [KeyboardButton(text="🔄 Моя аффирмация дня")]
    ]
    
    # Добавляем кнопку админа если нужно
    if user_id in ADMIN_IDS:
        keyboard.append([KeyboardButton(text="👑 Админ-панель")])
    
    keyboard.append([KeyboardButton(text="ℹ️ О боте")])
    
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        input_field_placeholder="Выберите действие..."
    )

def admin_menu():
    """Меню админ-панели"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="👥 Пользователи")],
            [KeyboardButton(text="📢 Рассылка")],
            [KeyboardButton(text="🔙 В главное меню")]
        ],
        resize_keyboard=True
    )

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
    
    # Обновляем статистику
    stats["total_users"] = len(users)
    save_stats(stats)
    
    # Персонализированное приветствие
    user_name = format_user_name(m.from_user)
    
    welcome_messages = [
        f"✨ Приветствую, {user_name}! Я — ваш личный нумеролог.",
        f"🌟 Добро пожаловать, {user_name}! Готовы раскрыть тайны чисел?",
        f"🔮 Здравствуйте, {user_name}! Числа расскажут многое о вашем пути.",
        f"💫 Рад видеть вас, {user_name}! Давайте исследуем мир нумерологии вместе."
    ]
    
    welcome_text = random.choice(welcome_messages) + "\n\n" + \
                  "Выберите, что вас интересует:"
    
    await m.answer(
        welcome_text,
        reply_markup=main_menu(user_id)
    )
    
    # Обновляем профиль
    PersonalizationEngine.update_user_profile(user_id, "start")

@router.message(lambda m: m.text == "✨ Мой нумерологический портрет")
async def numerology_portrait(m: Message):
    user_id = m.from_user.id
    PersonalizationEngine.update_user_profile(user_id, "portrait_request")
    
    await m.answer(
        "✨ *Нумерологический портрет*\n\n"
        "Введите вашу дату рождения в формате ДД.ММ.ГГГГ\n\n"
        "Например: 15.05.1990\n\n"
        "Я рассчитаю:\n"
        "• Число жизненного пути 🛤️\n"
        "• Число судьбы 🌟\n"
        "• Число характера 🔥\n"
        "• Сильные стороны 💪\n"
        "• Рекомендации для роста 📈",
        parse_mode="Markdown",
        reply_markup=main_menu(user_id)
    )

@router.message(lambda m: m.text == "💞 Совместимость партнеров")
async def compatibility_main(m: Message):
    user_id = m.from_user.id
    PersonalizationEngine.update_user_profile(user_id, "compatibility_request")
    
    await m.answer(
        "💞 *Совместимость партнеров*\n\n"
        "Введите две даты рождения через пробел:\n\n"
        "*Формат:* ДД.ММ.ГГГГ ДД.ММ.ГГГГ\n"
        "*Пример:* 15.05.1990 20.08.1985\n\n"
        "Я проанализирую:\n"
        "• Энергетическую совместимость ⚡\n"
        "• Сильные стороны пары 💪\n"
        "• Зоны для гармонизации 🔄\n"
        "• Практические рекомендации 📋",
        parse_mode="Markdown",
        reply_markup=main_menu(user_id)
    )

@router.message(lambda m: m.text == "📅 Прогноз на период")
async def forecast_main(m: Message):
    user_id = m.from_user.id
    PersonalizationEngine.update_user_profile(user_id, "forecast_request")
    
    await m.answer(
        "📅 *Прогноз на период*\n\n"
        "Введите дату рождения и период (неделя/месяц/год):\n\n"
        "*Формат:* ДД.ММ.ГГГГ период\n"
        "*Примеры:*\n15.05.1990 месяц\n15.05.1990 год\n15.05.1990 неделя\n\n"
        "Я сделаю нумерологический прогноз для выбранного периода.",
        parse_mode="Markdown",
        reply_markup=main_menu(user_id)
    )

@router.message(lambda m: m.text == "🌟 Персональный гороскоп")
async def horoscope_main(m: Message):
    user_id = m.from_user.id
    PersonalizationEngine.update_user_profile(user_id, "horoscope_request")
    
    await m.answer(
        "🌟 *Персональный гороскоп*\n\n"
        "Введите дату рождения и период для гороскопа:\n\n"
        "*Формат:* ДД.ММ.ГГГГ период\n"
        "*Примеры:*\n15.05.1990 сегодня\n15.05.1990 завтра\n15.05.1990 неделя\n\n"
        "Я создам персонализированный гороскоп на выбранный период.",
        parse_mode="Markdown",
        reply_markup=main_menu(user_id)
    )

@router.message(lambda m: m.text == "🔄 Моя аффирмация дня")
async def daily_affirmation(m: Message):
    user_id = m.from_user.id
    
    await m.answer(
        "🔄 *Моя аффирмация дня*\n\n"
        "Введите вашу дату рождения в формате ДД.ММ.ГГГГ\n\n"
        "Я создам для вас персональную аффирмацию —\n"
        "утверждение, которое поможет настроиться\n"
        "на удачный день и привлечь позитивную энергию.",
        parse_mode="Markdown",
        reply_markup=main_menu(user_id)
    )
    
    PersonalizationEngine.update_user_profile(user_id, "affirmation_request")

@router.message(lambda m: m.text == "👑 Админ-панель")
async def admin_button_handler(m: Message):
    user_id = m.from_user.id
    
    if user_id in ADMIN_IDS:
        await m.answer(
            "👑 *Панель администратора*\n\n"
            "Выберите действие:",
            parse_mode="Markdown",
            reply_markup=admin_menu()
        )
    else:
        await m.answer(
            "Эта функция доступна только администраторам",
            reply_markup=main_menu(user_id)
        )

@router.message(lambda m: m.text == "📊 Статистика")
async def show_stats(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        await m.answer("У вас нет прав для просмотра статистики", reply_markup=main_menu(m.from_user.id))
        return
    
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    stats_text = f"""
📊 *Статистика бота*

👥 Пользователи:
• Всего: {stats['total_users']}
• Активных сегодня: {stats.get('active_users', 0)}

📈 Активность:
• Расчетов портретов: {stats.get('calculations', 0)}
• Проверок совместимости: {stats.get('compatibility_checks', 0)}
• Прогнозов: {stats.get('forecasts', 0)}
• Гороскопов: {stats.get('horoscopes', 0)}

📅 За сегодня ({today}):
• Запросов: {stats['daily_stats'].get(today, 0)}
• Вчера ({yesterday}): {stats['daily_stats'].get(yesterday, 0)}

🌐 Админ-панель: {BASE_URL}{ADMIN_PATH}
"""
    
    await m.answer(stats_text, parse_mode="Markdown", reply_markup=admin_menu())

@router.message(lambda m: m.text == "👥 Пользователи")
async def show_users(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        await m.answer("У вас нет прав для просмотра пользователей", reply_markup=main_menu(m.from_user.id))
        return
    
    if not users:
        await m.answer("Нет данных о пользователях", reply_markup=admin_menu())
        return
    
    # Показываем последних 10 пользователей
    user_list = list(users.items())[-10:]
    users_text = "👥 *Последние 10 пользователей:*\n\n"
    
    for user_id, user_data in user_list:
        users_text += f"• {user_data.get('first_name', 'Неизвестно')}"
        if user_data.get('username'):
            users_text += f" (@{user_data['username']})"
        users_text += f"\n   ID: {user_id}\n   Зарегистрирован: {user_data.get('joined', 'N/A')}\n\n"
    
    users_text += f"\nВсего пользователей: {len(users)}"
    
    await m.answer(users_text, parse_mode="Markdown", reply_markup=admin_menu())

@router.message(lambda m: m.text == "📢 Рассылка")
async def broadcast_info(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        await m.answer("У вас нет прав для рассылки", reply_markup=main_menu(m.from_user.id))
        return
    
    await m.answer(
        f"Для массовой рассылки воспользуйтесь веб-панелью:\n{BASE_URL}{ADMIN_PATH}/broadcast\n\n"
        "Там вы можете отправить сообщение всем пользователям.",
        reply_markup=admin_menu()
    )

@router.message(lambda m: m.text == "🔙 В главное меню")
async def back_to_main(m: Message):
    user_id = m.from_user.id
    await m.answer(
        "Возвращаемся в главное меню:",
        reply_markup=main_menu(user_id)
    )

@router.message(lambda m: m.text == "ℹ️ О боте")
async def about_bot(m: Message):
    user_id = m.from_user.id
    
    about_text = f"""
🌟 *Нумерологический бот с AI*

Я — ваш персональный нумеролог, использующий искусственный интеллект для глубокого анализа.

✨ *Что я умею:*
• Создавать подробный нумерологический портрет
• Анализировать совместимость партнеров
• Делать прогнозы на выбранный период
• Генерировать персональные гороскопы
• Создавать аффирмации для вашего дня

🔮 *Мой подход:*
Я сочетаю древнюю мудрость нумерологии с современными психологическими знаниями. Все анализы уникальны и создаются специально для вас.

📊 *Статистика:*
• Пользователей: {stats['total_users']}
• Анализов выполнено: {stats.get('calculations', 0) + stats.get('compatibility_checks', 0) + stats.get('forecasts', 0)}

💡 *Совет:* Регулярно обращайтесь за анализом — числа могут раскрывать новые грани вашего пути!
"""
    
    await m.answer(about_text, parse_mode="Markdown", reply_markup=main_menu(user_id))

# =====================
# MAIN ANALYZERS
# =====================

@router.message(lambda m: is_date(m.text))
async def date_analysis_handler(m: Message):
    """Обработчик для анализа даты рождения"""
    user_id = m.from_user.id
    date_str = m.text
    
    await m.answer("✨ Анализирую ваш нумерологический портрет...")
    
    # Обновляем статистику
    stats["calculations"] = stats.get("calculations", 0) + 1
    stats["daily_stats"][datetime.now().strftime("%Y-%m-%d")] = stats["daily_stats"].get(datetime.now().strftime("%Y-%m-%d"), 0) + 1
    save_stats(stats)
    
    # Получаем число жизненного пути
    life_number = NumerologyFeatures.calculate_life_path_number(date_str)
    
    # Создаем промпт для AI
    prompt = f"""
Создай подробный нумерологический портрет для человека, родившегося {date_str}.
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
✨ *Ваш нумерологический портрет* ✨

{personalized_analysis}

🔄 *Аффирмация дня:*
{affirmation}

🌟 *Число жизненного пути:* {life_number if life_number else "не определено"}
📅 *Дата анализа:* {datetime.now().strftime("%d.%m.%Y")}
"""
    
    await m.answer(final_response, parse_mode="Markdown", reply_markup=main_menu(user_id))
    
    # Обновляем профиль пользователя
    PersonalizationEngine.update_user_profile(user_id, "portrait_analysis", {"date": date_str})

@router.message(lambda m: len(m.text.split()) == 2 and all("." in part for part in m.text.split()[:2]))
async def compatibility_analysis_handler(m: Message):
    """Обработчик для анализа совместимости"""
    user_id = m.from_user.id
    parts = m.text.split()
    
    # Проверяем, что первые две части - даты
    if len(parts) >= 2 and is_date(parts[0]) and is_date(parts[1]):
        date1, date2 = parts[0], parts[1]
        
        await m.answer("💞 Анализирую совместимость...")
        
        # Обновляем статистику
        stats["compatibility_checks"] = stats.get("compatibility_checks", 0) + 1
        stats["daily_stats"][datetime.now().strftime("%Y-%m-%d")] = stats["daily_stats"].get(datetime.now().strftime("%Y-%m-%d"), 0) + 1
        save_stats(stats)
        
        # Определяем тип совместимости
        compat_type = NumerologyFeatures.get_compatibility_type((date1, date2))
        
        # Создаем промпт
        prompt = f"""
Проанализируй совместимость двух людей по датам рождения:
1. {date1}
2. {date2}

Тип совместимости: {compat_type}

Включи следующие разделы:
1. Общая оценка совместимости
2. Сильные стороны пары
3. Потенциальные вызовы
4. Рекомендации для гармонии
5. Совместные возможности

Будь дипломатичным и конструктивным.
"""
        
        # Получаем анализ
        analysis = await ask_groq(prompt, "compatibility")
        
        # Персонализируем
        personalized_analysis = PersonalizationEngine.personalize_response(user_id, analysis, "compatibility")
        
        final_response = f"""
💞 *Анализ совместимости* 💞

*Даты:*
• {date1}
• {date2}

{personalized_analysis}

🔢 *Числа жизненного пути:*
• {NumerologyFeatures.calculate_life_path_number(date1) or '?'}
• {NumerologyFeatures.calculate_life_path_number(date2) or '?'}
"""
        
        await m.answer(final_response, parse_mode="Markdown", reply_markup=main_menu(user_id))
        
        PersonalizationEngine.update_user_profile(user_id, "compatibility_analysis", {"dates": [date1, date2]})
    else:
        await m.answer("Пожалуйста, введите две даты в формате: ДД.ММ.ГГГГ ДД.ММ.ГГГГ")

# =====================
# FORECAST & HOROSCOPE HANDLERS
# =====================

@router.message(lambda m: len(m.text.split()) == 2 and is_date(m.text.split()[0]))
async def forecast_or_horoscope_handler(m: Message):
    """Обработчик для прогнозов и гороскопов"""
    user_id = m.from_user.id
    parts = m.text.split()
    date_str = parts[0]
    period = parts[1].lower()
    
    if not is_date(date_str):
        await m.answer("Пожалуйста, сначала введите дату в формате ДД.ММ.ГГГГ")
        return
    
    # Определяем тип запроса по последнему действию
    user_history = personalization["user_history"].get(str(user_id), {"actions": []})
    last_action = user_history["actions"][-1] if user_history["actions"] else {}
    
    if "forecast" in last_action.get("action", ""):
        # Это прогноз
        await process_forecast(m, date_str, period, user_id)
    elif "horoscope" in last_action.get("action", ""):
        # Это гороскоп
        await process_horoscope(m, date_str, period, user_id)
    else:
        await m.answer("Пожалуйста, сначала выберите 'Прогноз на период' или 'Персональный гороскоп' в меню")

async def process_forecast(m: Message, date_str: str, period: str, user_id: int):
    """Обработка прогноза"""
    period_names = {
        "неделя": "неделю",
        "месяц": "месяц", 
        "год": "год",
        "квартал": "3 месяца"
    }
    
    period_display = period_names.get(period, period)
    
    await m.answer(f"📅 Создаю прогноз на {period_display}...")
    
    # Обновляем статистику
    stats["forecasts"] = stats.get("forecasts", 0) + 1
    stats["daily_stats"][datetime.now().strftime("%Y-%m-%d")] = stats["daily_stats"].get(datetime.now().strftime("%Y-%m-%d"), 0) + 1
    save_stats(stats)
    
    # Создаем промпт
    prompt = f"""
Сделай нумерологический прогноз на {period_display} для человека, родившегося {date_str}.
Число жизненного пути: {NumerologyFeatures.calculate_life_path_number(date_str) or 'не определено'}.

Включи:
1. Общую энергетику периода
2. Благоприятные возможности
3. Возможные вызовы
4. Рекомендации для успеха
5. Фокусные области для развития

Будь конкретным и практичным.
"""
    
    # Получаем прогноз
    forecast = await ask_groq(prompt, "forecast")
    
    final_response = f"""
📅 *Прогноз на {period_display}* 📅

{forecast}

✨ *Число жизненного пути:* {NumerologyFeatures.calculate_life_path_number(date_str) or '?'}
📆 *Период:* {period_display}
"""
    
    await m.answer(final_response, parse_mode="Markdown", reply_markup=main_menu(user_id))
    
    PersonalizationEngine.update_user_profile(user_id, f"forecast_{period}", {"date": date_str, "period": period})

async def process_horoscope(m: Message, date_str: str, period: str, user_id: int):
    """Обработка гороскопа"""
    period_names = {
        "сегодня": "сегодня",
        "завтра": "завтра",
        "неделя": "эту неделю",
        "месяц": "этот месяц"
    }
    
    period_display = period_names.get(period, period)
    
    await m.answer(f"🌟 Создаю гороскоп на {period_display}...")
    
    # Обновляем статистику
    stats["horoscopes"] = stats.get("horoscopes", 0) + 1
    stats["daily_stats"][datetime.now().strftime("%Y-%m-%d")] = stats["daily_stats"].get(datetime.now().strftime("%Y-%m-%d"), 0) + 1
    save_stats(stats)
    
    # Создаем промпт
    prompt = f"""
Создай персональный нумерологический гороскоп на {period_display} для человека, родившегося {date_str}.
Число жизненного пути: {NumerologyFeatures.calculate_life_path_number(date_str) or 'не определено'}.

Включи:
1. Общую энергетику периода
2. Сферу удачи
3. Совет от чисел
4. Число удачи на период
5. Рекомендации для гармонии

Будь вдохновляющим и мотивирующим.
"""
    
    # Получаем гороскоп
    horoscope = await ask_groq(prompt, "horoscope")
    
    # Добавляем аффирмацию
    affirmation = NumerologyFeatures.generate_daily_affirmation(date_str)
    
    final_response = f"""
🌟 *Ваш гороскоп на {period_display}* 🌟

{horoscope}

🔄 *Аффирмация:*
{affirmation}

✨ *Число жизненного пути:* {NumerologyFeatures.calculate_life_path_number(date_str) or '?'}
"""
    
    await m.answer(final_response, parse_mode="Markdown", reply_markup=main_menu(user_id))
    
    PersonalizationEngine.update_user_profile(user_id, f"horoscope_{period}", {"date": date_str, "period": period})

# =====================
# AFFIRMATION HANDLER
# =====================

@router.message(lambda m: is_date(m.text) and personalization["user_history"].get(str(m.from_user.id), {}).get("actions", [])[-1:][0].get("action") == "affirmation_request")
async def affirmation_handler(m: Message):
    """Обработчик для аффирмаций"""
    user_id = m.from_user.id
    date_str = m.text
    
    # Генерируем аффирмацию
    affirmation = NumerologyFeatures.generate_daily_affirmation(date_str)
    
    # Получаем число жизненного пути
    life_number = NumerologyFeatures.calculate_life_path_number(date_str)
    
    # Создаем ответ
    affirmation_text = f"""
🔄 *Ваша персональная аффирмация* 🔄

✨ {affirmation} ✨

*Почему эта аффирмация для вас:*
Эта утверждение резонирует с энергией вашего числа жизненного пути ({life_number or '?'}).

*Как использовать:*
1. Повторяйте утром, настраиваясь на день
2. Запишите в дневник или на стикер
3. Используйте как мантру в течение дня
4. Визуализируйте, как это проявляется в вашей жизни

🌟 *Число дня:* {random.randint(1, 9)} (символизирует энергию сегодняшнего дня)
"""
    
    await m.answer(affirmation_text, parse_mode="Markdown", reply_markup=main_menu(user_id))
    
    PersonalizationEngine.update_user_profile(user_id, "affirmation_generated", {"date": date_str})

# =====================
# FLASK APP
# =====================

app = Flask(__name__)

# HTML шаблон для админки
ADMIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Админ-панель нумерологического бота</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f5f5f5; }
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .stat-card { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .stat-number { font-size: 36px; font-weight: bold; color: #667eea; }
        .stat-label { color: #666; margin-top: 5px; }
        .btn { display: inline-block; padding: 10px 20px; background: #667eea; color: white; text-decoration: none; border-radius: 5px; margin: 10px 5px; }
        .btn:hover { background: #5a6fd8; }
        table { width: 100%; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        th, td { padding: 15px; text-align: left; border-bottom: 1px solid #eee; }
        th { background-color: #f8f9fa; font-weight: bold; }
    </style>
</head>
<body>
    <div class="header">
        <h1>👑 Админ-панель нумерологического бота</h1>
        <p>Последнее обновление: {{ update_time }}</p>
    </div>
    
    <div>
        <a href="/admin" class="btn">📊 Статистика</a>
        <a href="/admin/users" class="btn">👥 Пользователи</a>
    </div>
    
    {% if page == 'stats' %}
    <div class="stats-grid">
        <div class="stat-card">
            <div class="stat-number">{{ stats.total_users }}</div>
            <div class="stat-label">Всего пользователей</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">{{ stats.calculations }}</div>
            <div class="stat-label">Расчетов портретов</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">{{ stats.compatibility_checks }}</div>
            <div class="stat-label">Проверок совместимости</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">{{ stats.forecasts }}</div>
            <div class="stat-label">Прогнозов</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">{{ stats.horoscopes }}</div>
            <div class="stat-label">Гороскопов</div>
        </div>
    </div>
    
    {% elif page == 'users' %}
    <h2>👥 Последние пользователи (всего: {{ total_users }})</h2>
    <table>
        <tr>
            <th>ID</th>
            <th>Имя</th>
            <th>Username</th>
            <th>Дата регистрации</th>
        </tr>
        {% for user in users %}
        <tr>
            <td>{{ user.id }}</td>
            <td>{{ user.first_name }}</td>
            <td>{% if user.username %}@{{ user.username }}{% else %}-{% endif %}</td>
            <td>{{ user.joined }}</td>
        </tr>
        {% endfor %}
    </table>
    {% endif %}
</body>
</html>
"""

@app.route("/")
def home():
    return "🔮 Нумерологический бот работает! /start в Telegram"

@app.route("/ping")
def ping():
    return "pong"

@app.route("/health")
def health():
    return json.dumps({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "users": len(users),
        "bot": BOT_TOKEN is not None
    })

@app.route(ADMIN_PATH)
@app.route(ADMIN_PATH + "/")
def admin():
    """Главная страница админки со статистикой"""
    return render_template_string(
        ADMIN_TEMPLATE,
        page='stats',
        stats=stats,
        update_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

@app.route(ADMIN_PATH + "/users")
def admin_users():
    """Страница со списком пользователей"""
    # Собираем данные пользователей
    users_list = []
    user_items = list(users.items())
    
    for user_id, user_data in user_items[-50:]:
        users_list.append({
            'id': user_id,
            'username': user_data.get('username', ''),
            'first_name': user_data.get('first_name', ''),
            'joined': user_data.get('joined', '')
        })
    
    return render_template_string(
        ADMIN_TEMPLATE,
        page='users',
        users=users_list,
        total_users=len(users),
        update_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    try:
        data = request.get_json()
        if not data:
            return "no data", 400
        
        update = types.Update(**data)
        
        # Запускаем обработку в event loop
        asyncio.run_coroutine_threadsafe(
            dp.feed_update(bot, update),
            loop
        )
        return "ok"
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return "error", 500

# =====================
# ASYNC SETUP
# =====================

async def on_startup():
    """Действия при старте бота"""
    logger.info("Bot starting up...")
    
    # Устанавливаем вебхук
    webhook_info = await bot.get_webhook_info()
    if webhook_info.url != WEBHOOK_URL:
        await bot.set_webhook(WEBHOOK_URL)
        logger.info(f"Webhook set to: {WEBHOOK_URL}")
    
    logger.info("Bot started successfully!")

async def main_async():
    """Основная асинхронная функция"""
    await on_startup()
    
    # Запускаем поллинг (для отладки) или вебхук
    if os.getenv("DEBUG", "false").lower() == "true":
        logger.info("Starting in polling mode (DEBUG)")
        await dp.start_polling(bot)
    else:
        logger.info("Starting in webhook mode")
        # Просто держим event loop живым
        while True:
            await asyncio.sleep(3600)

# =====================
# START
# =====================

def run_bot():
    """Запуск бота"""
    try:
        # Проверка необходимых переменных
        if not BOT_TOKEN:
            logger.error("BOT_TOKEN is not set!")
            return
        
        if not GROQ_API_KEY:
            logger.warning("GROQ_API_KEY is not set! Some features will be limited.")
        
        # Создаем event loop
        asyncio.set_event_loop(loop)
        
        # Запускаем основную асинхронную функцию
        loop.run_until_complete(main_async())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Error in bot: {e}")
    finally:
        loop.close()

def run_flask():
    """Запуск Flask сервера"""
    port = int(os.environ.get("PORT", 10000))
    
    # Используем production WSGI сервер
    from waitress import serve
    logger.info(f"Starting Flask server on port {port}")
    serve(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    logger.info("Starting Numerology Bot...")
    
    # Проверка переменных окружения
    if not BOT_TOKEN:
        logger.error("❌ ERROR: BOT_TOKEN is not set!")
        print("Please set BOT_TOKEN environment variable")
        sys.exit(1)
    
    if not GROQ_API_KEY:
        logger.warning("⚠️ WARNING: GROQ_API_KEY is not set! AI features will not work.")
    
    logger.info(f"✅ BOT_TOKEN: {'Set' if BOT_TOKEN else 'Not set'}")
    logger.info(f"✅ GROQ_API_KEY: {'Set' if GROQ_API_KEY else 'Not set'}")
    logger.info(f"✅ BASE_URL: {BASE_URL}")
    logger.info(f"✅ ADMIN_IDS: {ADMIN_IDS}")
    
    # Создаем файлы если их нет
    if not USERS_FILE.exists():
        save_users({})
    if not STATS_FILE.exists():
        save_stats(load_stats())
    if not PERSONALIZATION_FILE.exists():
        save_personalization(load_personalization())
    
    # Запускаем Flask в отдельном потоке
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    logger.info("✨ Нумерологический бот запущен!")
    logger.info(f"🌐 Веб-сервер: http://0.0.0.0:{os.environ.get('PORT', 10000)}")
    logger.info(f"🌐 Админ-панель: {BASE_URL}{ADMIN_PATH}")
    logger.info(f"👑 Админ ID: {ADMIN_IDS}")
    logger.info("🎯 Уникальные фичи включены")
    
    # Запускаем бота
    try:
        run_bot()
    except Exception as e:
        logger.error(f"Failed to run bot: {e}")
    
    # Держим основной поток живым
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
