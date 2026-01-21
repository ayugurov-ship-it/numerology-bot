import os
import json
import asyncio
import aiohttp
import logging
import random
from datetime import datetime, timedelta
from pathlib import Path
from threading import Thread
from typing import Optional, Dict, Any

try:
    import requests
    from flask import Flask, request
    from aiogram import Bot, Dispatcher, Router, types, F
    from aiogram.filters import CommandStart, Command
    from aiogram.client.default import DefaultBotProperties
    from aiogram.types import (
        ReplyKeyboardMarkup,
        KeyboardButton,
        Message,
        InlineKeyboardMarkup,
        InlineKeyboardButton,
        ReplyKeyboardRemove
    )
    from aiogram.utils.keyboard import InlineKeyboardBuilder
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
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
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

# Системные промпты (улучшенные)
SYSTEM_PROMPTS = {
    "portrait": """Ты — профессиональный нумеролог с 20-летним опытом. Создай подробный нумерологический портрет.

Включи следующие разделы в красивой форме с эмодзи:

🌟 **Основные числа:**
- Число жизненного пути (расскажи о его значении)
- Число судьбы
- Число души
- Число личности

✨ **Характеристики личности:**
- Ключевые черты характера
- Таланты и способности  
- Сильные стороны
- Слабые стороны и зоны роста

💼 **Профессиональная сфера:**
- Подходящие профессии
- Карьерные рекомендации
- Деловые качества

❤️ **Личная жизнь:**
- Совместимость с другими числами
- Рекомендации по отношениям
- Семейная жизнь

🌱 **Советы для развития:**
- Как раскрыть потенциал
- Что важно развивать
- Чего следует избегать

💫 **Особые рекомендации:**
- Аффирмации для ежедневного использования
- Камни-талисманы
- Благоприятные цвета
- Счастливые числа

Формат: живой, вдохновляющий, практичный. Не упоминай, что ты ИИ. Добавь немного магии и загадочности.""",
    
    "compatibility": """Ты — эксперт по нумерологической совместимости. Проанализируй пару людей.

Включи:

💞 **Общая оценка совместимости:** (0-100%)
✨ **Энергетическая гармония:** Как энергии чисел взаимодействуют
🤝 **Сильные стороны пары:** Что объединяет и усиливает
⚡️ **Вызовы и сложности:** Где могут возникнуть трудности
💡 **Рекомендации для гармонии:** Практические советы
🌟 **Совместные возможности:** В каких сферах лучше всего проявить себя
💖 **Перспективы отношений:** Краткосрочные и долгосрочные прогнозы

Будь дипломатичным, конструктивным и поддерживающим.""",
    
    "forecast": """Ты — аналитик по нумерологическим циклам. Создай прогноз на период.

📅 **Общая энергетика периода:** Основные вибрации
🎯 **Благоприятные возможности:** Что стоит предпринять
⚠️ **Возможные вызовы:** На что обратить внимание
💡 **Рекомендации для успеха:** Практические шаги
🌟 **Фокусные области:** На чем сосредоточиться
✨ **Личный рост:** Как использовать период для развития
🔮 **Предостережения:** Чего лучше избегать

Будь конкретным, практичным и мотивирующим. Укажи конкретные даты или временные рамки.""",
    
    "horoscope": """Ты — нумеролог-астролог. Создай вдохновляющий гороскоп.

🌅 **Общая атмосфера периода:** Основной настрой
🍀 **Сфера удачи:** Где ждет успех
💡 **Совет от чисел:** Мудрость цифр
🚀 **Что следует делать:** Конкретные действия
⛔️ **Чего лучше избегать:** Предостережения
🌟 **Творческие возможности:** Идеи для реализации
❤️ **Личные отношения:** Советы для сердца
💼 **Карьера и финансы:** Деловые рекомендации
🌿 **Здоровье и энергия:** Советы по самочувствию

Будь креативным, мотивирующим и поэтичным. Добавь элемент магии и тайны."""
}

# =====================
# ХРАНИЛИЩЕ ДАННЫХ (УЛУЧШЕННОЕ)
# =====================

USERS_FILE = Path("users.json")
STATS_FILE = Path("stats.json")
USER_DATES_FILE = Path("user_dates.json")

def load_data(filename: Path, default=None):
    if filename.exists():
        try:
            return json.loads(filename.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Ошибка загрузки {filename}: {e}")
            return default if default is not None else {}
    return default if default is not None else {}

def save_data(filename: Path, data):
    try:
        filename.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.error(f"Ошибка сохранения {filename}: {e}")

# Загружаем данные
users = load_data(USERS_FILE, {})
stats = load_data(STATS_FILE, {
    "total_users": 0,
    "calculations": 0,
    "compatibility_checks": 0,
    "forecasts": 0,
    "horoscopes": 0,
    "daily_stats": {}
})
user_dates = load_data(USER_DATES_FILE, {})

# =====================
# НУМЕРОЛОГИЧЕСКИЙ КАЛЬКУЛЯТОР (УЛУЧШЕННЫЙ)
# =====================

class NumerologyCalculator:
    """Расширенный нумерологический калькулятор"""
    
    @staticmethod
    def calculate_life_path(date_str: str) -> int:
        """Число жизненного пути"""
        try:
            digits = date_str.replace('.', '')
            total = sum(int(d) for d in digits)
            
            while total > 9 and total not in [11, 22, 33]:
                total = sum(int(d) for d in str(total))
            
            return total
        except:
            return None
    
    @staticmethod
    def calculate_destiny_number(date_str: str) -> int:
        """Число судьбы (сумма всех цифр полной даты)"""
        try:
            digits = date_str.replace('.', '')
            total = sum(int(d) for d in digits)
            
            while total > 9:
                total = sum(int(d) for d in str(total))
            
            return total
        except:
            return None
    
    @staticmethod
    def calculate_soul_number(date_str: str) -> int:
        """Число души (сумма гласных в имени - здесь используем дату)"""
        try:
            day = int(date_str.split('.')[0])
            while day > 9:
                day = sum(int(d) for d in str(day))
            return day
        except:
            return None
    
    @staticmethod
    def calculate_personality_number(date_str: str) -> int:
        """Число личности (сумма согласных - здесь используем месяц)"""
        try:
            month = int(date_str.split('.')[1])
            while month > 9:
                month = sum(int(d) for d in str(month))
            return month
        except:
            return None
    
    @staticmethod
    def get_number_meaning(number: int) -> Dict[str, Any]:
        """Расширенные значения чисел"""
        meanings = {
            1: {
                "title": "Лидер",
                "traits": ["Самостоятельность", "Инициативность", "Смелость", "Новаторство"],
                "professions": ["Предприниматель", "Руководитель", "Изобретатель"],
                "compatibility": [3, 5, 9],
                "colors": ["Красный", "Оранжевый"],
                "stones": ["Рубин", "Гранат"],
                "advice": "Уверенно идите к цели, не бойтесь быть первым"
            },
            2: {
                "title": "Дипломат",
                "traits": ["Чувствительность", "Тактичность", "Гармония", "Кооперация"],
                "professions": ["Психолог", "Дипломат", "Художник"],
                "compatibility": [4, 6, 8],
                "colors": ["Белый", "Серебряный"],
                "stones": ["Жемчуг", "Лунный камень"],
                "advice": "Развивайте интуицию и доверяйте партнерским отношениям"
            },
            3: {
                "title": "Творец",
                "traits": ["Креативность", "Оптимизм", "Общительность", "Энтузиазм"],
                "professions": ["Артист", "Писатель", "Преподаватель"],
                "compatibility": [1, 5, 7],
                "colors": ["Желтый", "Бирюзовый"],
                "stones": ["Топаз", "Янтарь"],
                "advice": "Выражайте себя через творчество и радуйтесь жизни"
            },
            4: {
                "title": "Строитель",
                "traits": ["Стабильность", "Практичность", "Надежность", "Трудолюбие"],
                "professions": ["Архитектор", "Инженер", "Бухгалтер"],
                "compatibility": [2, 6, 8],
                "colors": ["Зеленый", "Коричневый"],
                "stones": ["Изумруд", "Нефрит"],
                "advice": "Создавайте прочный фундамент для будущих достижений"
            },
            5: {
                "title": "Искатель",
                "traits": ["Свобода", "Любознательность", "Адаптивность", "Авантюризм"],
                "professions": ["Путешественник", "Журналист", "Маркетолог"],
                "compatibility": [1, 3, 7],
                "colors": ["Синий", "Серый"],
                "stones": ["Бирюза", "Сапфир"],
                "advice": "Исследуйте мир и оставайтесь открытыми переменам"
            },
            6: {
                "title": "Хранитель",
                "traits": ["Ответственность", "Забота", "Гармония", "Преданность"],
                "professions": ["Врач", "Учитель", "Социальный работник"],
                "compatibility": [2, 4, 9],
                "colors": ["Розовый", "Бирюзовый"],
                "stones": ["Розовый кварц", "Аметист"],
                "advice": "Заботьтесь о близких и создавайте уют вокруг себя"
            },
            7: {
                "title": "Мудрец",
                "traits": ["Аналитичность", "Интуиция", "Созерцательность", "Мудрость"],
                "professions": ["Ученый", "Философ", "Исследователь"],
                "compatibility": [3, 5, 9],
                "colors": ["Фиолетовый", "Индиго"],
                "stones": ["Аметист", "Лазурит"],
                "advice": "Развивайте внутреннюю мудрость и доверяйте интуиции"
            },
            8: {
                "title": "Достигатель",
                "traits": ["Амбициозность", "Организованность", "Успех", "Изобилие"],
                "professions": ["Бизнесмен", "Банкир", "Руководитель"],
                "compatibility": [2, 4, 6],
                "colors": ["Золотой", "Черный"],
                "stones": ["Бриллиант", "Обсидиан"],
                "advice": "Ставьте амбициозные цели и привлекайте изобилие"
            },
            9: {
                "title": "Гуманист",
                "traits": ["Мудрость", "Сострадание", "Терпимость", "Завершение"],
                "professions": ["Благотворитель", "Врач", "Артист"],
                "compatibility": [1, 6, 7],
                "colors": ["Бордовый", "Пурпурный"],
                "stones": ["Рубин", "Кошачий глаз"],
                "advice": "Помогайте другим и завершайте циклы с благодарностью"
            },
            11: {
                "title": "Просветленный",
                "traits": ["Интуиция", "Вдохновение", "Озарение", "Духовность"],
                "professions": ["Мистик", "Художник", "Духовный учитель"],
                "compatibility": [2, 4, 22],
                "colors": ["Серебряный", "Жемчужный"],
                "stones": ["Селенит", "Лабрадорит"],
                "advice": "Слушайте высшее руководство и вдохновляйте других"
            },
            22: {
                "title": "Мастер-строитель",
                "traits": ["Практичность", "Масштабность", "Реализация", "Сила"],
                "professions": ["Архитектор", "Политик", "Изобретатель"],
                "compatibility": [4, 8, 11],
                "colors": ["Платиновый", "Белый"],
                "stones": ["Алмаз", "Горный хрусталь"],
                "advice": "Воплощайте великие идеи в реальность с мудростью"
            },
            33: {
                "title": "Мастер-учитель",
                "traits": ["Служение", "Исцеление", "Любовь", "Просветление"],
                "professions": ["Учитель", "Целитель", "Гуру"],
                "compatibility": [6, 9, 11],
                "colors": ["Радужный", "Золотой"],
                "stones": ["Опал", "Авантюрин"],
                "advice": "Несите свет и исцеление через служение человечеству"
            }
        }
        return meanings.get(number, {
            "title": "Особое число",
            "traits": ["Уникальность", "Индивидуальность"],
            "professions": ["Разные направления"],
            "compatibility": [1, 2, 3],
            "colors": ["Разные цвета"],
            "stones": ["Кварц", "Агат"],
            "advice": "Исследуйте свою уникальную энергию"
        })
    
    @staticmethod
    def generate_affirmation(date_str: str) -> str:
        """Генерация персонализированной аффирмации"""
        life_number = NumerologyCalculator.calculate_life_path(date_str)
        
        affirmations = {
            1: "Я уверенно веду свою жизнь к великим целям и победам",
            2: "Я привлекаю гармоничные отношения и прекрасное сотрудничество",
            3: "Я творчески выражаю себя и наполняю мир радостью и красотой",
            4: "Я строю прочный фундамент успеха и стабильности в своей жизни",
            5: "Я свободен в выборе и открыт удивительным приключениям жизни",
            6: "Я создаю любящую гармонию в отношениях и забочусь о близких",
            7: "Я доверяю своей мудрой интуиции и нахожу глубинные ответы",
            8: "Я привлекаю изобилие, успех и процветание во все сферы жизни",
            9: "Я завершаю циклы с благодарностью и открываюсь новым началам",
            11: "Я вдохновляю окружающих своим светом и духовным видением",
            22: "Я воплощаю великие идеи в реальность с мастерством и силой",
            33: "Я несу исцеление и любовь через служение и духовное руководство"
        }
        
        return affirmations.get(life_number, "Я принимаю этот день с благодарностью и открытым сердцем")
    
    @staticmethod
    def get_daily_number() -> int:
        """Число дня (на основе текущей даты)"""
        today = datetime.now()
        day_num = today.day + today.month + today.year
        while day_num > 9:
            day_num = sum(int(d) for d in str(day_num))
        return day_num

# =====================
# GROQ API (УЛУЧШЕННЫЙ)
# =====================

async def ask_groq(prompt: str, prompt_type: str = "portrait") -> str:
    """Улучшенный запрос к Groq API с кэшированием"""
    if not GROQ_API_KEY:
        return "🌟 Сервис временно недоступен. Пожалуйста, попробуйте позже или воспользуйтесь базовым анализом."
    
    cache_file = Path(f"cache_{hash(prompt) % 1000}.json")
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            if datetime.now().timestamp() - cached["timestamp"] < 3600:  # 1 час кэш
                return cached["response"]
        except:
            pass
    
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Динамические токены в зависимости от типа
    max_tokens = {
        "portrait": 1500,
        "compatibility": 1200,
        "forecast": 1000,
        "horoscope": 1200
    }.get(prompt_type, 1000)
    
    data = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPTS.get(prompt_type, SYSTEM_PROMPTS["portrait"])},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": max_tokens,
        "top_p": 0.9
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data, timeout=45) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"Groq API error {resp.status}: {error_text}")
                    return await generate_fallback_response(prompt, prompt_type)
                
                result = await resp.json()
                response = result["choices"][0]["message"]["content"]
                
                # Сохраняем в кэш
                cache_data = {
                    "timestamp": datetime.now().timestamp(),
                    "response": response
                }
                save_data(cache_file, cache_data)
                
                return response
                
    except asyncio.TimeoutError:
        logger.error("Groq API timeout")
        return await generate_fallback_response(prompt, prompt_type)
    except Exception as e:
        logger.error(f"Groq API exception: {e}")
        return await generate_fallback_response(prompt, prompt_type)

async def generate_fallback_response(prompt: str, prompt_type: str) -> str:
    """Генерация резервного ответа если API не работает"""
    if "дата" in prompt.lower():
        date_match = None
        for part in prompt.split():
            if '.' in part and len(part) == 10:
                date_match = part
                break
        
        if date_match:
            life_number = NumerologyCalculator.calculate_life_path(date_match)
            meaning = NumerologyCalculator.get_number_meaning(life_number)
            
            if prompt_type == "portrait":
                return f"""🌟 **Нумерологический портрет для {date_match}**

🔢 **Основные числа:**
• Число жизненного пути: {life_number} - {meaning['title']}
• Число судьбы: {NumerologyCalculator.calculate_destiny_number(date_match)}
• Число души: {NumerologyCalculator.calculate_soul_number(date_match)}
• Число личности: {NumerologyCalculator.calculate_personality_number(date_match)}

✨ **Ключевые черты:**
{', '.join(meaning['traits'][:4])}

💼 **Подходящие профессии:**
{', '.join(meaning['professions'][:3])}

❤️ **Совместимость:** с числами {', '.join(map(str, meaning['compatibility']))}

💎 **Талисманы:** {', '.join(meaning['stones'])}
🎨 **Цвета:** {', '.join(meaning['colors'])}

💫 **Аффирмация дня:**
{NumerologyCalculator.generate_affirmation(date_match)}

🌟 **Совет:** {meaning['advice']}"""
    
    return "✨ На основе анализа чисел вижу благоприятные энергии! Рекомендую доверять интуиции и сохранять позитивный настрой."

# =====================
# ИНИЦИАЛИЗАЦИЯ БОТА - ИСПРАВЛЕННАЯ
# =====================

try:
    # ИСПРАВЛЕНО: используем DefaultBotProperties для aiogram 3.7.0+
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML")
    )
    dp = Dispatcher()
    router = Router()
    dp.include_router(router)
    logger.info("✅ Бот инициализирован")
except Exception as e:
    logger.error(f"❌ Ошибка инициализации бота: {e}")
    exit(1)

# =====================
# КЛАВИАТУРЫ (УЛУЧШЕННЫЕ)
# =====================

def main_menu(user_id: int = None, has_date: bool = False):
    """Главное меню с учетом сохраненной даты"""
    keyboard = [
        [KeyboardButton(text="✨ Нумеропортрет")],
        [KeyboardButton(text="💞 Совместимость")],
        [KeyboardButton(text="🌟 Гороскоп")],
        [KeyboardButton(text="📅 Прогноз")],
        [KeyboardButton(text="🔄 Аффирмация")]
    ]
    
    if has_date:
        keyboard.insert(0, [KeyboardButton(text="📊 Моя нумерология")])
    
    if user_id in ADMIN_IDS:
        keyboard.append([KeyboardButton(text="👑 Админ")])
    
    keyboard.append([KeyboardButton(text="ℹ️ Помощь")])
    
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        input_field_placeholder="Выберите действие..."
    )

def horoscope_menu():
    """Меню для гороскопа"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🌞 Сегодня", callback_data="horoscope_today")
    builder.button(text="🌙 Завтра", callback_data="horoscope_tomorrow")
    builder.button(text="📅 На неделю", callback_data="horoscope_week")
    builder.button(text="📆 На месяц", callback_data="horoscope_month")
    builder.button(text="✨ На год", callback_data="horoscope_year")
    builder.button(text="🔄 Общий гороскоп", callback_data="horoscope_general")
    builder.adjust(2, 2, 2)
    return builder.as_markup()

def period_menu():
    """Меню для прогноза"""
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 На месяц", callback_data="period_month")
    builder.button(text="📆 На 3 месяца", callback_data="period_quarter")
    builder.button(text="🎯 На год", callback_data="period_year")
    builder.button(text="✨ На неделю", callback_data="period_week")
    builder.button(text="🌟 На полгода", callback_data="period_halfyear")
    builder.adjust(2, 2, 1)
    return builder.as_markup()

def compatibility_menu():
    """Меню для совместимости"""
    builder = InlineKeyboardBuilder()
    builder.button(text="💑 Романтика", callback_data="comp_love")
    builder.button(text="💼 Бизнес", callback_data="comp_business")
    builder.button(text="👥 Дружба", callback_data="comp_friends")
    builder.button(text="👨‍👩‍👧‍👦 Семья", callback_data="comp_family")
    builder.button(text="💝 Духовная", callback_data="comp_spiritual")
    builder.adjust(2, 2, 1)
    return builder.as_markup()

# =====================
# ОБРАБОТЧИКИ СООБЩЕНИЙ
# =====================

@router.message(CommandStart())
async def start_command(message: Message):
    """Обработка команды /start"""
    user_id = message.from_user.id
    user_key = str(user_id)
    
    # Сохраняем пользователя
    if user_key not in users:
        users[user_key] = {
            "username": message.from_user.username or "",
            "first_name": message.from_user.first_name or "",
            "last_name": message.from_user.last_name or "",
            "joined": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_active": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        save_data(USERS_FILE, users)
        stats["total_users"] = len(users)
        save_data(STATS_FILE, stats)
    
    # Проверяем есть ли сохраненная дата
    has_date = user_key in user_dates
    
    # Персонализированное приветствие
    greetings = [
        f"✨ Приветствую, {message.from_user.first_name or 'друг'}! Готовы раскрыть тайны чисел?",
        f"🌟 Добро пожаловать, {message.from_user.first_name or 'путешественник'}! Числа ждут анализа.",
        f"🔮 Здравствуйте, {message.from_user.first_name or 'искатель'}! Давайте исследуем вашу нумерологию."
    ]
    
    welcome_text = random.choice(greetings)
    
    if has_date:
        saved_date = user_dates[user_key]
        life_number = NumerologyCalculator.calculate_life_path(saved_date)
        welcome_text += f"\n\n📅 Я помню вашу дату рождения: {saved_date}"
        welcome_text += f"\n🔢 Ваше число жизненного пути: {life_number}"
    
    welcome_text += "\n\nВыберите действие:"
    
    await message.answer(
        welcome_text,
        reply_markup=main_menu(user_id, has_date)
    )
    logger.info(f"Пользователь {user_id} запустил бота")

@router.message(F.text == "📊 Моя нумерология")
async def my_numerology_handler(message: Message):
    """Показывает сохраненную нумерологию пользователя"""
    user_id = str(message.from_user.id)
    
    if user_id not in user_dates:
        await message.answer(
            "📝 У вас нет сохраненной даты рождения.\n\n"
            "Введите вашу дату рождения в формате ДД.ММ.ГГГГ,\n"
            "чтобы я мог сохранить ее для быстрого доступа.",
            reply_markup=main_menu(message.from_user.id, False)
        )
        return
    
    date_str = user_dates[user_id]
    await process_saved_date(message, date_str)

async def process_saved_date(message: Message, date_str: str):
    """Обработка сохраненной даты"""
    user_id = message.from_user.id
    
    # Базовый расчет
    life_number = NumerologyCalculator.calculate_life_path(date_str)
    destiny_number = NumerologyCalculator.calculate_destiny_number(date_str)
    soul_number = NumerologyCalculator.calculate_soul_number(date_str)
    personality_number = NumerologyCalculator.calculate_personality_number(date_str)
    meaning = NumerologyCalculator.get_number_meaning(life_number)
    
    # Формируем базовый ответ
    response = f"""
📊 <b>Ваша персональная нумерология</b>

📅 <b>Дата рождения:</b> {date_str}

🔢 <b>Ключевые числа:</b>
• 🛤️ <b>Число жизненного пути {life_number}:</b> {meaning['title']}
• ⭐ <b>Число судьбы {destiny_number}:</b> Ваше предназначение
• 💖 <b>Число души {soul_number}:</b> Ваши внутренние желания
• 🎭 <b>Число личности {personality_number}:</b> Как вас видят другие

✨ <b>Основные черты:</b>
{chr(10).join(f'• {trait}' for trait in meaning['traits'][:4])}

💼 <b>Профессии:</b> {', '.join(meaning['professions'][:3])}

💞 <b>Совместимость:</b> с числами {', '.join(map(str, meaning['compatibility']))}

💎 <b>Талисманы:</b> {', '.join(meaning['stones'])}
🎨 <b>Цвета:</b> {', '.join(meaning['colors'])}

🌟 <b>Число дня:</b> {NumerologyCalculator.get_daily_number()} (энергия сегодня)
"""
    
    await message.answer(response, reply_markup=main_menu(user_id, True))
    
    # Отправляем аффирмацию отдельным сообщением
    affirmation = NumerologyCalculator.generate_affirmation(date_str)
    await message.answer(
        f"🔄 <b>Ваша аффирмация:</b>\n\n{affirmation}",
        reply_markup=main_menu(user_id, True)
    )

@router.message(F.text == "✨ Нумеропортрет")
async def portrait_handler(message: Message):
    """Обработка нумеропортрета"""
    user_id = str(message.from_user.id)
    
    if user_id in user_dates:
        # Предлагаем использовать сохраненную дату
        builder = InlineKeyboardBuilder()
        builder.button(text="📅 Использовать сохраненную", callback_data=f"use_saved_{user_dates[user_id]}")
        builder.button(text="✏️ Ввести новую дату", callback_data="enter_new_date")
        builder.adjust(1)
        
        await message.answer(
            f"📅 У вас сохранена дата рождения: {user_dates[user_id]}\n\n"
            "Хотите использовать ее для анализа?",
            reply_markup=builder.as_markup()
        )
    else:
        await message.answer(
            "✨ <b>Нумерологический портрет</b>\n\n"
            "Введите вашу дату рождения в формате <b>ДД.ММ.ГГГГ</b>\n\n"
            "<i>Пример:</i> 15.05.1990\n\n"
            "Я создам подробный анализ вашей личности на основе чисел,\n"
            "включая характер, таланты, совместимость и рекомендации.",
            reply_markup=ReplyKeyboardRemove()
        )

@router.message(F.text == "🌟 Гороскоп")
async def horoscope_handler(message: Message):
    """Обработка гороскопа"""
    user_id = str(message.from_user.id)
    
    if user_id in user_dates:
        builder = InlineKeyboardBuilder()
        builder.button(text="📅 Использовать сохраненную", callback_data=f"horoscope_saved_{user_dates[user_id]}")
        builder.button(text="✏️ Ввести новую дату", callback_data="horoscope_new")
        builder.adjust(1)
        
        await message.answer(
            f"📅 У вас сохранена дата рождения: {user_dates[user_id]}\n\n"
            "Хотите использовать ее для гороскопа?",
            reply_markup=builder.as_markup()
        )
    else:
        await message.answer(
            "🌟 <b>Персональный гороскоп</b>\n\n"
            "Выберите период для гороскопа:",
            reply_markup=horoscope_menu()
        )

@router.message(F.text == "📅 Прогноз")
async def forecast_handler(message: Message):
    """Обработка прогноза"""
    await message.answer(
        "📅 <b>Нумерологический прогноз</b>\n\n"
        "Выберите период для прогноза:",
        reply_markup=period_menu()
    )

@router.message(F.text == "💞 Совместимость")
async def compatibility_handler(message: Message):
    """Обработка совместимости"""
    await message.answer(
        "💞 <b>Нумерологическая совместимость</b>\n\n"
        "Выберите тип отношений для анализа:",
        reply_markup=compatibility_menu()
    )

@router.message(F.text == "🔄 Аффирмация")
async def affirmation_handler(message: Message):
    """Обработка аффирмации"""
    user_id = str(message.from_user.id)
    
    if user_id in user_dates:
        affirmation = NumerologyCalculator.generate_affirmation(user_dates[user_id])
        await message.answer(
            f"🔄 <b>Ваша персональная аффирмация</b>\n\n"
            f"{affirmation}\n\n"
            f"<i>Основано на вашей дате рождения: {user_dates[user_id]}</i>",
            reply_markup=main_menu(message.from_user.id, True)
        )
    else:
        await message.answer(
            "🔄 <b>Персональная аффирмация</b>\n\n"
            "Введите вашу дату рождения:\n\n"
            "<b>Формат:</b> ДД.ММ.ГГГГ\n"
            "<i>Пример:</i> 15.05.1990\n\n"
            "Я создам для вас аффирмацию — утверждение, которое\n"
            "поможет настроиться на удачный день.",
            reply_markup=ReplyKeyboardRemove()
        )

@router.message(F.text == "ℹ️ Помощь")
async def help_handler(message: Message):
    """Обработка помощи"""
    help_text = f"""
🌟 <b>Нумерологический бот с AI</b>

Я — ваш персональный нумеролог, использующий искусственный интеллект для глубокого анализа.

✨ <b>Доступные функции:</b>

1. <b>✨ Нумеропортрет</b> — глубокий анализ личности по дате рождения
2. <b>💞 Совместимость</b> — анализ отношений для разных сфер жизни
3. <b>🌟 Гороскоп</b> — нумерологический гороскоп на разные периоды
4. <b>📅 Прогноз</b> — прогноз на неделю/месяц/год
5. <b>🔄 Аффирмация</b> — персональное утверждение на день
6. <b>📊 Моя нумерология</b> — быстрый доступ к сохраненным данным

📋 <b>Как пользоваться:</b>
1. Выберите функцию в меню
2. Следуйте инструкциям бота
3. Получите персонализированный анализ

🔮 <b>Формат даты:</b> ДД.ММ.ГГГГ (например, 15.05.1990)
💡 <b>Бот запоминает</b> вашу дату рождения для быстрого доступа!

📊 <b>Статистика:</b> {stats['total_users']} пользователей уже доверили мне свои числа!
"""
    
    await message.answer(help_text, reply_markup=main_menu(message.from_user.id, str(message.from_user.id) in user_dates))

@router.message(F.text == "👑 Админ")
async def admin_handler(message: Message):
    """Админ панель"""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("Эта функция доступна только администраторам")
        return
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    admin_text = f"""
👑 <b>Панель администратора</b>

📊 <b>Статистика:</b>
• 👥 Пользователей: {stats['total_users']}
• 📈 Анализов портретов: {stats.get('calculations', 0)}
• 💞 Проверок совместимости: {stats.get('compatibility_checks', 0)}
• 📅 Прогнозов: {stats.get('forecasts', 0)}
• 🌟 Гороскопов: {stats.get('horoscopes', 0)}
• 📨 Запросов сегодня: {stats['daily_stats'].get(today, 0)}

🌐 <b>Веб-админка:</b> {BASE_URL}/admin
🆔 <b>Ваш ID:</b> {message.from_user.id}
🔗 <b>Webhook:</b> {WEBHOOK_URL}

<b>💾 Сохраненных дат:</b> {len(user_dates)}
"""
    
    await message.answer(admin_text, reply_markup=main_menu(message.from_user.id, str(message.from_user.id) in user_dates))

# =====================
# ОБРАБОТЧИКИ CALLBACK
# =====================

@router.callback_query(F.data.startswith("use_saved_"))
async def use_saved_date_callback(callback: types.CallbackQuery):
    """Использование сохраненной даты для портрета"""
    date_str = callback.data.replace("use_saved_", "")
    user_id = str(callback.from_user.id)
    
    await callback.message.edit_text("✨ Создаю нумерологический портрет...")
    
    # Обновляем статистику
    stats["calculations"] = stats.get("calculations", 0) + 1
    today = datetime.now().strftime("%Y-%m-%d")
    stats["daily_stats"][today] = stats["daily_stats"].get(today, 0) + 1
    save_data(STATS_FILE, stats)
    
    # Создаем промпт для AI
    prompt = f"""
Создай подробный нумерологический портрет для человека, родившегося {date_str}.

Числа:
- Жизненный путь: {NumerologyCalculator.calculate_life_path(date_str)}
- Судьба: {NumerologyCalculator.calculate_destiny_number(date_str)}
- Души: {NumerologyCalculator.calculate_soul_number(date_str)}
- Личности: {NumerologyCalculator.calculate_personality_number(date_str)}

Сделай анализ глубоким, вдохновляющим и практичным.
"""
    
    # Получаем ответ от AI
    analysis = await ask_groq(prompt, "portrait")
    
    # Формируем финальный ответ
    life_number = NumerologyCalculator.calculate_life_path(date_str)
    meaning = NumerologyCalculator.get_number_meaning(life_number)
    
    response = f"""
✨ <b>Ваш нумерологический портрет</b> ✨

📅 <b>Дата рождения:</b> {date_str}
🔢 <b>Число жизненного пути:</b> {life_number} ({meaning['title']})

{analysis}

💫 <b>Базовые рекомендации:</b>
• {meaning['advice']}
• Совместимость с числами: {', '.join(map(str, meaning['compatibility']))}
• Талисманы: {', '.join(meaning['stones'])}
• Цвета: {', '.join(meaning['colors'])}

🔄 <b>Аффирмация:</b>
{NumerologyCalculator.generate_affirmation(date_str)}
"""
    
    await callback.message.answer(response, reply_markup=main_menu(callback.from_user.id, True))
    await callback.answer()

@router.callback_query(F.data == "enter_new_date")
async def enter_new_date_callback(callback: types.CallbackQuery):
    """Запрос новой даты"""
    await callback.message.edit_text(
        "📝 Введите вашу дату рождения в формате <b>ДД.ММ.ГГГГ</b>\n\n"
        "<i>Пример:</i> 15.05.1990"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("horoscope_"))
async def horoscope_callback(callback: types.CallbackQuery):
    """Обработка выбора периода для гороскопа"""
    if callback.data.startswith("horoscope_saved_"):
        # Использование сохраненной даты
        date_str = callback.data.replace("horoscope_saved_", "")
        await process_horoscope_with_date(callback, date_str)
        return
    
    if callback.data == "horoscope_new":
        # Ввод новой даты
        await callback.message.edit_text(
            "📝 Введите дату рождения для гороскопа:\n\n"
            "<b>Формат:</b> ДД.ММ.ГГГГ\n"
            "<i>Пример:</i> 15.05.1990"
        )
        await callback.answer()
        return
    
    # Обработка периода
    period = callback.data.replace("horoscope_", "")
    
    period_names = {
        "today": "сегодня 🌞",
        "tomorrow": "завтра 🌙", 
        "week": "неделю 📅",
        "month": "месяц 📆",
        "year": "год 🎯",
        "general": "общий гороскоп ✨"
    }
    
    await callback.message.edit_text(
        f"🌟 <b>Гороскоп на {period_names.get(period, 'период')}</b>\n\n"
        "Введите вашу дату рождения:\n\n"
        "<b>Формат:</b> ДД.ММ.ГГГГ\n"
        "<i>Пример:</i> 15.05.1990\n\n"
        "Я создам персонализированный нумерологический гороскоп."
    )
    await callback.answer()

async def process_horoscope_with_date(callback: types.CallbackQuery, date_str: str):
    """Обработка гороскопа с датой"""
    await callback.message.edit_text("🌟 Создаю нумерологический гороскоп...")
    
    # Обновляем статистику
    stats["horoscopes"] = stats.get("horoscopes", 0) + 1
    today = datetime.now().strftime("%Y-%m-%d")
    stats["daily_stats"][today] = stats["daily_stats"].get(today, 0) + 1
    save_data(STATS_FILE, stats)
    
    # Определяем период (из callback.data)
    period = "today"  # по умолчанию
    
    # Создаем промпт
    prompt = f"""
Создай подробный нумерологический гороскоп на сегодня для человека, родившегося {date_str}.

Основные числа:
- Число жизненного пути: {NumerologyCalculator.calculate_life_path(date_str)}
- Число дня: {NumerologyCalculator.get_daily_number()}

Сделай гороскоп вдохновляющим, практичным и детализированным.
"""
    
    # Получаем ответ от AI
    horoscope = await ask_groq(prompt, "horoscope")
    
    # Формируем ответ
    life_number = NumerologyCalculator.calculate_life_path(date_str)
    daily_number = NumerologyCalculator.get_daily_number()
    
    response = f"""
🌟 <b>Ваш нумерологический гороскоп</b> 🌟

📅 <b>Дата рождения:</b> {date_str}
📆 <b>Период:</b> сегодня
🔢 <b>Число жизненного пути:</b> {life_number}
✨ <b>Число дня:</b> {daily_number}

{horoscope}

🔄 <b>Аффирмация дня:</b>
{NumerologyCalculator.generate_affirmation(date_str)}

💫 <b>Совет от чисел:</b>
Сегодня благоприятный день для новых начинаний и творчества!
"""
    
    # Сохраняем дату если еще не сохранена
    user_id = str(callback.from_user.id)
    if user_id not in user_dates:
        user_dates[user_id] = date_str
        save_data(USER_DATES_FILE, user_dates)
    
    await callback.message.answer(response, reply_markup=main_menu(callback.from_user.id, True))
    await callback.answer()

# =====================
# ОБРАБОТЧИКИ ДАТ
# =====================

def is_valid_date(text: str) -> bool:
    """Проверка валидности даты"""
    try:
        datetime.strptime(text, "%d.%m.%Y")
        # Проверка что дата не в будущем
        date_obj = datetime.strptime(text, "%d.%m.%Y")
        if date_obj > datetime.now():
            return False
        return True
    except:
        return False

@router.message(F.text & F.text.regexp(r'\d{2}\.\d{2}\.\d{4}'))
async def process_date_input(message: Message):
    """Обработка введенной даты"""
    date_str = message.text.strip()
    
    if not is_valid_date(date_str):
        await message.answer(
            "❌ <b>Неверный формат даты</b>\n\n"
            "Пожалуйста, введите дату в формате <b>ДД.ММ.ГГГГ</b>\n"
            "<i>Пример:</i> 15.05.1990\n\n"
            "Дата должна быть реальной и не в будущем."
        )
        return
    
    user_id = str(message.from_user.id)
    
    # Сохраняем дату
    user_dates[user_id] = date_str
    save_data(USER_DATES_FILE, user_dates)
    
    await message.answer("✨ Анализирую данные...")
    
    # Обновляем статистику
    stats["calculations"] = stats.get("calculations", 0) + 1
    today = datetime.now().strftime("%Y-%m-%d")
    stats["daily_stats"][today] = stats["daily_stats"].get(today, 0) + 1
    save_data(STATS_FILE, stats)
    
    # Создаем промпт для AI
    prompt = f"""
Создай подробный нумерологический портрет для человека, родившегося {date_str}.

Числа:
- Жизненный путь: {NumerologyCalculator.calculate_life_path(date_str)}
- Судьба: {NumerologyCalculator.calculate_destiny_number(date_str)}
- Души: {NumerologyCalculator.calculate_soul_number(date_str)}
- Личности: {NumerologyCalculator.calculate_personality_number(date_str)}

Сделай анализ глубоким, вдохновляющим и практичным.
"""
    
    # Получаем ответ от AI
    analysis = await ask_groq(prompt, "portrait")
    
    # Формируем финальный ответ
    life_number = NumerologyCalculator.calculate_life_path(date_str)
    meaning = NumerologyCalculator.get_number_meaning(life_number)
    
    response = f"""
✨ <b>Ваш нумерологический портрет</b> ✨

📅 <b>Дата рождения:</b> {date_str}
✅ <b>Дата сохранена</b> для быстрого доступа!

🔢 <b>Ключевые числа:</b>
• 🛤️ <b>Жизненный путь {life_number}:</b> {meaning['title']}
• ⭐ <b>Судьба {NumerologyCalculator.calculate_destiny_number(date_str)}:</b> Ваше предназначение
• 💖 <b>Души {NumerologyCalculator.calculate_soul_number(date_str)}:</b> Внутренние желания
• 🎭 <b>Личности {NumerologyCalculator.calculate_personality_number(date_str)}:</b> Как вас видят

{analysis}

💫 <b>Базовые характеристики:</b>
• <b>Черты:</b> {', '.join(meaning['traits'][:3])}
• <b>Профессии:</b> {', '.join(meaning['professions'][:2])}
• <b>Совместимость:</b> с числами {', '.join(map(str, meaning['compatibility'][:2]))}
• <b>Талисманы:</b> {meaning['stones'][0]}
• <b>Цвета:</b> {meaning['colors'][0]}

🔄 <b>Ваша аффирмация:</b>
{NumerologyCalculator.generate_affirmation(date_str)}

🌟 <b>Совет:</b> {meaning['advice']}
"""
    
    await message.answer(response, reply_markup=main_menu(message.from_user.id, True))

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
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    min-height: 100vh;
                }
                .container {
                    background: rgba(255, 255, 255, 0.1);
                    backdrop-filter: blur(10px);
                    border-radius: 20px;
                    padding: 40px;
                    margin-top: 50px;
                    box-shadow: 0 20px 40px rgba(0,0,0,0.2);
                }
                h1 {
                    font-size: 3.5em;
                    margin-bottom: 20px;
                    text-align: center;
                    text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
                }
                .status {
                    background: rgba(255,255,255,0.15);
                    padding: 25px;
                    border-radius: 15px;
                    margin: 30px 0;
                    border: 1px solid rgba(255,255,255,0.2);
                }
                .stats {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                    gap: 15px;
                    margin: 25px 0;
                }
                .stat-box {
                    background: rgba(255,255,255,0.1);
                    padding: 15px;
                    border-radius: 10px;
                    text-align: center;
                    transition: transform 0.3s;
                }
                .stat-box:hover {
                    transform: translateY(-5px);
                    background: rgba(255,255,255,0.2);
                }
                .stat-number {
                    font-size: 2em;
                    font-weight: bold;
                    margin-bottom: 5px;
                }
                .stat-label {
                    font-size: 0.9em;
                    opacity: 0.9;
                }
                .buttons {
                    display: flex;
                    flex-wrap: wrap;
                    gap: 15px;
                    justify-content: center;
                    margin-top: 30px;
                }
                .btn {
                    color: white;
                    background: rgba(255,255,255,0.2);
                    padding: 15px 30px;
                    border-radius: 50px;
                    text-decoration: none;
                    transition: all 0.3s;
                    border: 1px solid rgba(255,255,255,0.3);
                    font-weight: 500;
                    display: inline-flex;
                    align-items: center;
                    gap: 10px;
                }
                .btn:hover {
                    background: rgba(255,255,255,0.3);
                    transform: translateY(-2px);
                    box-shadow: 0 10px 20px rgba(0,0,0,0.2);
                    text-decoration: none;
                    color: white;
                }
                .emoji {
                    font-size: 1.2em;
                }
                .features {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                    gap: 20px;
                    margin: 30px 0;
                }
                .feature {
                    background: rgba(255,255,255,0.1);
                    padding: 20px;
                    border-radius: 15px;
                    text-align: center;
                }
                .feature-icon {
                    font-size: 2.5em;
                    margin-bottom: 15px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🔮 Нумерологический Бот</h1>
                
                <div class="status">
                    <p style="text-align: center; font-size: 1.2em; margin-bottom: 20px;">
                        ✅ Бот работает и готов к запросам!
                    </p>
                    
                    <div class="stats">
                        <div class="stat-box">
                            <div class="stat-number">{}</div>
                            <div class="stat-label">👥 Пользователей</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-number">{}</div>
                            <div class="stat-label">✨ Анализов</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-number">{}</div>
                            <div class="stat-label">💞 Совместимостей</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-number">{}</div>
                            <div class="stat-label">🌟 Гороскопов</div>
                        </div>
                    </div>
                    
                    <p style="text-align: center; opacity: 0.9; margin-top: 20px;">
                        🕐 Запущен: {} | 💾 Сохраненных дат: {}
                    </p>
                </div>
                
                <div class="features">
                    <div class="feature">
                        <div class="feature-icon">✨</div>
                        <h3>Нумеропортрет</h3>
                        <p>Глубокий анализ личности по дате рождения</p>
                    </div>
                    <div class="feature">
                        <div class="feature-icon">🌟</div>
                        <h3>Гороскоп</h3>
                        <p>Персональный нумерологический гороскоп</p>
                    </div>
                    <div class="feature">
                        <div class="feature-icon">💞</div>
                        <h3>Совместимость</h3>
                        <p>Анализ отношений по нумерологии</p>
                    </div>
                </div>
                
                <div class="buttons">
                    <a href="/admin" class="btn"><span class="emoji">👑</span> Админ-панель</a>
                    <a href="/ping" class="btn"><span class="emoji">📡</span> Ping</a>
                    <a href="/health" class="btn"><span class="emoji">❤️</span> Health Check</a>
                    <a href="/stats" class="btn"><span class="emoji">📊</span> Статистика</a>
                </div>
                
                <p style="text-align: center; margin-top: 40px; opacity: 0.8; font-size: 0.9em;">
                    Откройте Telegram и найдите бота для использования
                </p>
            </div>
        </body>
    </html>
    """.format(
        stats['total_users'],
        stats.get('calculations', 0),
        stats.get('compatibility_checks', 0),
        stats.get('horoscopes', 0),
        datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        len(user_dates)
    )

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
        "saved_dates": len(user_dates),
        "requests_today": stats['daily_stats'].get(datetime.now().strftime("%Y-%m-%d"), 0),
        "memory_usage": "OK"
    }

@app.route("/stats")
def stats_page():
    today = datetime.now().strftime("%Y-%m-%d")
    
    html = f"""
    <html>
        <head>
            <title>📊 Статистика бота</title>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; max-width: 1000px; margin: 0 auto; padding: 20px; background: #f5f5f5; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 15px; margin-bottom: 30px; text-align: center; }}
                .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }}
                .stat-card {{ background: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); text-align: center; }}
                .stat-number {{ font-size: 36px; font-weight: bold; color: #667eea; margin: 10px 0; }}
                .stat-label {{ color: #666; font-size: 14px; text-transform: uppercase; }}
                .recent-users {{ background: white; padding: 20px; border-radius: 10px; margin-top: 20px; }}
                .user-item {{ padding: 10px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>📊 Статистика нумерологического бота</h1>
                <p>Обновлено: {datetime.now().strftime("%d.%m.%Y %H:%M")}</p>
            </div>
            
            <div class="stats-grid">
                <div class="stat-card"><div class="stat-number">{stats.get('total_users', 0)}</div><div class="stat-label">👥 Пользователей</div></div>
                <div class="stat-card"><div class="stat-number">{stats.get('calculations', 0)}</div><div class="stat-label">✨ Анализов</div></div>
                <div class="stat-card"><div class="stat-number">{stats.get('compatibility_checks', 0)}</div><div class="stat-label">💞 Совместимостей</div></div>
                <div class="stat-card"><div class="stat-number">{stats.get('horoscopes', 0)}</div><div class="stat-label">🌟 Гороскопов</div></div>
                <div class="stat-card"><div class="stat-number">{stats.get('forecasts', 0)}</div><div class="stat-label">📅 Прогнозов</div></div>
                <div class="stat-card"><div class="stat-number">{stats['daily_stats'].get(today, 0)}</div><div class="stat-label">📨 Запросов сегодня</div></div>
            </div>
            
            <div class="recent-users">
                <h3>💾 Сохраненные даты рождения: {len(user_dates)}</h3>
                <p>Бот запоминает даты для быстрого доступа</p>
            </div>
            
            <div style="margin-top: 30px; text-align: center;">
                <a href="/admin" style="background: #667eea; color: white; padding: 10px 20px; border-radius: 5px; text-decoration: none; margin-right: 10px;">👑 Админка</a>
                <a href="/" style="background: #764ba2; color: white; padding: 10px 20px; border-radius: 5px; text-decoration: none;">🏠 На главную</a>
            </div>
        </body>
    </html>
    """
    return html

@app.route("/admin")
def admin():
    """Админ панель"""
    today = datetime.now().strftime("%Y-%m-%d")
    week_stats = {}
    
    # Статистика за неделю
    for i in range(6, -1, -1):
        date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        week_stats[date] = stats['daily_stats'].get(date, 0)
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>👑 Админ-панель</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ 
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                color: #333;
            }}
            .admin-container {{
                background: rgba(255, 255, 255, 0.95);
                border-radius: 20px;
                padding: 40px;
                margin-top: 20px;
                box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            }}
            .header {{
                text-align: center;
                margin-bottom: 40px;
                padding-bottom: 20px;
                border-bottom: 2px solid #eee;
            }}
            .header h1 {{
                color: #667eea;
                margin-bottom: 10px;
            }}
            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                gap: 25px;
                margin-bottom: 40px;
            }}
            .stat-card {{
                background: white;
                padding: 25px;
                border-radius: 15px;
                box-shadow: 0 5px 15px rgba(0,0,0,0.08);
                text-align: center;
                transition: transform 0.3s, box-shadow 0.3s;
                border: 1px solid #f0f0f0;
            }}
            .stat-card:hover {{
                transform: translateY(-5px);
                box-shadow: 0 15px 30px rgba(0,0,0,0.1);
            }}
            .stat-icon {{
                font-size: 2.5em;
                margin-bottom: 15px;
            }}
            .stat-number {{
                font-size: 42px;
                font-weight: bold;
                color: #667eea;
                margin: 10px 0;
            }}
            .stat-label {{
                color: #666;
                font-size: 14px;
                text-transform: uppercase;
                letter-spacing: 1px;
            }}
            .info-box {{
                background: #f8f9fa;
                padding: 25px;
                border-radius: 15px;
                margin: 30px 0;
                border-left: 5px solid #667eea;
            }}
            .week-stats {{
                background: white;
                padding: 25px;
                border-radius: 15px;
                margin-top: 30px;
            }}
            .stat-row {{
                display: flex;
                justify-content: space-between;
                padding: 10px 0;
                border-bottom: 1px solid #eee;
            }}
            .controls {{
                display: flex;
                gap: 15px;
                margin-top: 30px;
                flex-wrap: wrap;
            }}
            .btn {{
                background: #667eea;
                color: white;
                padding: 12px 25px;
                border-radius: 10px;
                text-decoration: none;
                transition: background 0.3s;
                border: none;
                cursor: pointer;
                font-size: 16px;
                display: inline-flex;
                align-items: center;
                gap: 8px;
            }}
            .btn:hover {{
                background: #5a6fd8;
                text-decoration: none;
                color: white;
            }}
            .btn-secondary {{
                background: #764ba2;
            }}
            .btn-secondary:hover {{
                background: #6a4190;
            }}
        </style>
    </head>
    <body>
        <div class="admin-container">
            <div class="header">
                <h1>👑 Админ-панель нумерологического бота</h1>
                <p style="color: #666;">Статус: <span style="color: #4CAF50; font-weight: bold;">● Активен</span> | {datetime.now().strftime("%d.%m.%Y %H:%M")}</p>
            </div>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-icon">👥</div>
                    <div class="stat-number">{stats.get('total_users', 0)}</div>
                    <div class="stat-label">Пользователей</div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon">✨</div>
                    <div class="stat-number">{stats.get('calculations', 0)}</div>
                    <div class="stat-label">Анализов портретов</div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon">💞</div>
                    <div class="stat-number">{stats.get('compatibility_checks', 0)}</div>
                    <div class="stat-label">Совместимостей</div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon">🌟</div>
                    <div class="stat-number">{stats.get('horoscopes', 0)}</div>
                    <div class="stat-label">Гороскопов</div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon">📅</div>
                    <div class="stat-number">{stats.get('forecasts', 0)}</div>
                    <div class="stat-label">Прогнозов</div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon">📨</div>
                    <div class="stat-number">{stats['daily_stats'].get(today, 0)}</div>
                    <div class="stat-label">Запросов сегодня</div>
                </div>
            </div>
            
            <div class="info-box">
                <h3>📊 Информация о системе</h3>
                <p><strong>🌐 Webhook URL:</strong> {WEBHOOK_URL}</p>
                <p><strong>👑 Админ ID:</strong> {ADMIN_IDS[0]}</p>
                <p><strong>🔗 База URL:</strong> {BASE_URL}</p>
                <p><strong>💾 Сохраненных дат:</strong> {len(user_dates)}</p>
                <p><strong>📁 Пользователей с датами:</strong> {len([uid for uid in user_dates if uid in users])}</p>
            </div>
            
            <div class="week-stats">
                <h3>📈 Активность за последние 7 дней</h3>
                {"".join([f'<div class="stat-row"><span>{date}</span><span>{count} запросов</span></div>' for date, count in week_stats.items()])}
            </div>
            
            <div class="controls">
                <a href="/" class="btn">🏠 На главную</a>
                <a href="/stats" class="btn">📊 Статистика</a>
                <a href="/health" class="btn">❤️ Health Check</a>
                <a href="/ping" class="btn">📡 Ping</a>
                <button onclick="location.reload()" class="btn btn-secondary">🔄 Обновить</button>
            </div>
        </div>
        
        <script>
            // Автообновление каждые 30 секунд
            setTimeout(() => location.reload(), 30000);
        </script>
    </body>
    </html>
    """
    return html

@app.route(WEBHOOK_PATH, methods=["POST", "GET"])
def webhook():
    if request.method == "GET":
        return "✅ Webhook готов к работе! Бот активен.", 200
    
    try:
        data = request.get_json()
        
        # Логируем входящие запросы
        if 'message' in data and 'text' in data['message']:
            user_id = data['message']['from'].get('id')
            text = data['message']['text']
            logger.info(f"📨 Сообщение от {user_id}: {text}")
        elif 'callback_query' in data:
            user_id = data['callback_query']['from']['id']
            callback_data = data['callback_query']['data']
            logger.info(f"🔘 Callback от {user_id}: {callback_data}")
        
        update = types.Update(**data)
        
        # Запускаем обработку в event loop
        asyncio.run_coroutine_threadsafe(
            dp.feed_update(bot, update),
            loop
        )
        return "ok"
    except Exception as e:
        logger.error(f"❌ Ошибка webhook: {e}", exc_info=True)
        return "error", 500

# =====================
# WEBHOOK SETUP
# =====================

def setup_webhook():
    """Настройка webhook"""
    try:
        logger.info("🔄 Настройка webhook...")
        
        # Удаляем старый webhook
        delete_url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook"
        response = requests.post(delete_url, json={"drop_pending_updates": True})
        if response.status_code == 200:
            logger.info("✅ Старый webhook удален")
        else:
            logger.warning(f"⚠️ Не удалось удалить webhook: {response.text}")
        
        # Ждем немного
        import time
        time.sleep(1)
        
        # Устанавливаем новый webhook
        set_url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
        data = {
            "url": WEBHOOK_URL,
            "drop_pending_updates": True,
            "allowed_updates": ["message", "callback_query", "chat_member"],
            "max_connections": 40
        }
        response = requests.post(set_url, json=data)
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"✅ Webhook установлен: {WEBHOOK_URL}")
            logger.info(f"✅ Ответ Telegram: {result}")
        else:
            logger.error(f"❌ Ошибка установки webhook: {response.text}")
            
    except Exception as e:
        logger.error(f"❌ Ошибка настройки webhook: {e}")

# =====================
# ЗАПУСК
# =====================

def run_flask():
    """Запуск Flask сервера"""
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"🚀 Запуск Flask на порту {port}")
    
    # Для production лучше использовать waitress или gunicorn
    try:
        app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
    except Exception as e:
        logger.error(f"❌ Ошибка запуска Flask: {e}")

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("🚀 ЗАПУСК НУМЕРОЛОГИЧЕСКОГО БОТА")
    logger.info("=" * 60)
    
    # Проверка обязательных переменных
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN не установлен!")
        exit(1)
    
    logger.info(f"✅ BOT_TOKEN: {'Установлен' if BOT_TOKEN else 'Нет'}")
    logger.info(f"✅ GROQ_API_KEY: {'Установлен' if GROQ_API_KEY else 'Нет (будут fallback ответы)'}")
    logger.info(f"✅ BASE_URL: {BASE_URL}")
    logger.info(f"✅ ADMIN_IDS: {ADMIN_IDS}")
    logger.info(f"✅ Пользователей в базе: {len(users)}")
    logger.info(f"✅ Сохраненных дат: {len(user_dates)}")
    
    # Создаем файлы если их нет
    if not USERS_FILE.exists():
        save_data(USERS_FILE, {})
        logger.info("✅ Файл users.json создан")
    
    if not STATS_FILE.exists():
        save_data(STATS_FILE, stats)
        logger.info("✅ Файл stats.json создан")
    
    if not USER_DATES_FILE.exists():
        save_data(USER_DATES_FILE, {})
        logger.info("✅ Файл user_dates.json создан")
    
    # Настраиваем event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Настраиваем webhook
    setup_webhook()
    
    # Запускаем Flask в отдельном потоке
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    logger.info("✨ Нумерологический бот успешно запущен!")
    logger.info(f"🌐 Админ-панель: {BASE_URL}/admin")
    logger.info(f"📊 Статистика: {BASE_URL}/stats")
    logger.info(f"👑 Админ ID: {ADMIN_IDS[0]}")
    logger.info("📱 Откройте Telegram и найдите вашего бота")
    logger.info("=" * 60)
    
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        logger.info("⏹️ Остановка бота...")
    finally:
        loop.close()
        logger.info("✅ Бот остановлен")
