# main.pу
import os
import json
import asyncio
import aiohttp
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from collections import defaultdict
import random
import time
from functools import wraps
from contextlib import asynccontextmanager
import contextlib

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from aiogram import Bot, Dispatcher, Router, types
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Update
)

# =====================
# CONFIG & LOGGING
# =====================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
BASE_URL = os.getenv("BASE_URL", "https://your-domain.com")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "260219938").split(",")))
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "your-admin-token")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "your-secret-token")
MODEL_NAME = os.getenv("MODEL_NAME", "llama-3.1-8b-instant")
KEEP_ALIVE_INTERVAL = int(os.getenv("KEEP_ALIVE_INTERVAL", "600"))  # секунд, по умолчанию 10 мин
WEBHOOK_PATH = "/webhook"
ADMIN_PATH = "/admin"
PORT = int(os.getenv("PORT", 8000))
USE_POLLING = os.getenv("USE_POLLING", "false").lower() == "true"

# Rate limiting
limiter = Limiter(key_func=get_remote_address)

# =====================
# PYDANTIC MODELS
# =====================

class UserCreate(BaseModel):
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None

class UserStats(BaseModel):
    user_id: str
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    joined: str
    last_active: str
    total_requests: int = 0

class StatsResponse(BaseModel):
    total_users: int
    active_users: int
    inactive_users: int
    calculations: int
    compatibility_checks: int
    forecasts: int
    horoscopes: int
    daily_stats: Dict[str, int]
    popular_features: Dict[str, int]

class DateModel(BaseModel):
    date_str: str

    @field_validator('date_str')
    def validate_date(cls, v):
        try:
            datetime.strptime(v, "%d.%m.%Y")
            return v
        except ValueError as exc:
            raise ValueError("Invalid date format. Use DD.MM.YYYY") from exc

class DualDateModel(BaseModel):
    date1: str
    date2: str

    @field_validator('date1', 'date2')
    def validate_date(cls, v):
        try:
            datetime.strptime(v, "%d.%m.%Y")
            return v
        except ValueError as exc:
            raise ValueError("Invalid date format. Use DD.MM.YYYY") from exc

# =====================
# STORAGE CLASS
# =====================

class Storage:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.users: Dict[str, Dict] = {}
        self.stats: Dict = {}
        self.personalization: Dict = {}
        self._load_all()
        self._last_save = time.time()

    def _load_all(self):
        self.users = self._load_json("users.json", {})
        self.stats = self._load_json("stats.json", self._default_stats())
        self.personalization = self._load_json(
            "personalization.json",
            {"user_preferences": {}, "user_history": {}},
        )

    def _load_json(self, filename: str, default: Any) -> Any:
        path = Path(filename)
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                logger.error("Corrupted %s, using default", filename)
                return default
        return default

    def _default_stats(self) -> Dict:
        return {
            "total_users": 0,
            "active_users": 0,
            "inactive_users": 0,
            "calculations": 0,
            "compatibility_checks": 0,
            "forecasts": 0,
            "horoscopes": 0,
            "daily_stats": defaultdict(int),
            "popular_features": defaultdict(int),
            "user_registration_dates": {},
            "user_last_activity": {},
        }

    async def save_all(self, force: bool = False):
        current_time = time.time()
        if force or current_time - self._last_save > 60:
            async with self.lock:
                self._save_json("users.json", self.users)
                self._save_json("stats.json", self.stats)
                self._save_json("personalization.json", self.personalization)
            self._last_save = current_time

    def _save_json(self, filename: str, data: Any):
        Path(filename).write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

storage = Storage()

# =====================
# FASTAPI APP WITH LIFESPAN
# =====================

async def keep_alive():
    """Пингуем сами себя, чтобы Render Free не усыплял сервис"""
    if not BASE_URL or BASE_URL == "https://your-domain.com":
        logger.warning("KEEP-ALIVE: BASE_URL не задан, self-ping отключён")
        return
    url = f"{BASE_URL}/ping"
    logger.info("KEEP-ALIVE: запущен, интервал %s сек, url=%s", KEEP_ALIVE_INTERVAL, url)
    while True:
        await asyncio.sleep(KEEP_ALIVE_INTERVAL)
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                async with session.get(url) as resp:
                    logger.debug("KEEP-ALIVE: ping %s → %s", url, resp.status)
        except Exception as e:
            logger.warning("KEEP-ALIVE: ошибка ping: %s", e)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    # Запуск
    logger.info("Starting Astro-Numerology Bot...")

    # Keep-alive для Render Free
    app.state.keep_alive_task = asyncio.create_task(keep_alive())

    # Отложенная установка вебхука / polling (в фоне, чтобы не блокировать открытие порта)
    async def _delayed_setup():
        """Запуск бота после того, как сервер уже слушает порт."""
        await asyncio.sleep(1)  # Даём uvicorn 1 с на bind порта
        if not BOT_TOKEN:
            logger.error("ERROR: BOT_TOKEN is not set!")
            return
        if USE_POLLING:
            try:
                await bot.delete_webhook(drop_pending_updates=True)
                app.state.polling_task = asyncio.create_task(dp.start_polling(bot))
                logger.info("Polling started (USE_POLLING=true).")
            except Exception as e:
                logger.error(f"Ошибка запуска polling: {e}")
        elif BASE_URL:
            webhook_url = f"{BASE_URL}{WEBHOOK_PATH}"
            try:
                wh_kwargs = dict(
                    url=webhook_url,
                    drop_pending_updates=False,
                    max_connections=40,
                )
                if WEBHOOK_SECRET and WEBHOOK_SECRET != "your-secret-token":
                    wh_kwargs["secret_token"] = WEBHOOK_SECRET
                await asyncio.wait_for(bot.set_webhook(**wh_kwargs), timeout=15)
                logger.info(f"Webhook установлен: {webhook_url}")
            except asyncio.TimeoutError:
                logger.error("Таймаут при установке вебхука (15с)")
            except Exception as e:
                logger.error(f"Ошибка установки вебхука: {e}")

    app.state.setup_task = asyncio.create_task(_delayed_setup())

    yield

    # Завершение
    logger.info("Shutting down Astro-Numerology Bot...")
    try:
        for task_name in ("setup_task", "keep_alive_task", "polling_task"):
            task = getattr(app.state, task_name, None)
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        # Удаляем вебхук ТОЛЬКО в режиме polling
        # В webhook-режиме НЕ удаляем, чтобы Telegram продолжал доставлять обновления
        if USE_POLLING:
            await bot.delete_webhook()
        await bot.session.close()
    except Exception as e:
        logger.error(f"Ошибка при завершении: {e}")
    await storage.save_all(force=True)

app = FastAPI(
    title="Astro-Numerology Bot API",
    description="Telegram бот для астро-нумерологии с AI",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

# =====================
# AIOGRAM BOT INIT
# =====================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# =====================
# CONSTANTS
# =====================

GROQ_SYSTEM_PROMPTS = {
    "default": """Ты — профессиональный астро-нумеролог с 20-летним опытом.
Ты сочетаешь астрологию (знаки зодиака, стихии) и нумерологию (числа жизненного пути).
Пиши дружелюбно, уверенно, без мистического фанатизма.
Язык: чистый литературный русский. Не упоминай, что ты ИИ.""",

    "profile": """Ты — эксперт по астрологии и нумерологии, создающий комбинированные портреты личности.
Ты анализируешь знак зодиака (характеристики знака, стихию) и число жизненного пути одновременно,
показывая как они дополняют друг друга и где создают интересные контрасты.
Тон: уверенный, экспертный, без мистики. Язык: русский.""",

    "detailed": """Ты — глубокий эксперт по нумерологии и психологии личности.
Анализируй числа даты рождения, давая глубокие персонализированные инсайты.
Можешь кратко упомянуть знак зодиака как дополнительный контекст.
Будь точным, но вдохновляющим. Язык: русский.""",

    "compatibility": """Ты — специалист по отношениям, совместимости и астро-нумерологии.
Анализируй совместимость пар по двум системам: зодиакальная совместимость (знаки, стихии)
и нумерологическая совместимость (числа жизненного пути).
Будь дипломатичным, подчеркивай сильные стороны пары. Язык: русский.""",

    "horoscope": """Ты — профессиональный астролог с глубоким знанием нумерологии.
Создавай персонализированные гороскопы, основываясь на знаке зодиака и его стихии,
дополняя нумерологическими инсайтами (число жизненного пути).
Тон: уверенный, конкретный, без общих фраз. Язык: русский.""",

    "daily_card": """Ты — персональный астро-нумеролог, создающий карты дня.
Ты формируешь карту дня из трёх компонентов: аффирмация, краткий прогноз, практический совет.
Учитывай знак зодиака и число жизненного пути. Будь конкретным и практичным.
Без эзотерики, без «вселенная/карма/потоки». Язык: русский."""
}

# =====================
# PERSONALIZATION ENGINE
# =====================

class PersonalizationEngine:
    @staticmethod
    async def update_user_profile(user_id: int, action: str, data: dict = None, birth_date: str = None):
        user_id_str = str(user_id)

        if user_id_str not in storage.personalization["user_history"]:
            storage.personalization["user_history"][user_id_str] = {
                "actions": [],
                "preferences": {},
                "last_interaction": datetime.now().isoformat()
            }

        if birth_date:
            storage.personalization["user_history"][user_id_str]["birth_date"] = birth_date

        storage.personalization["user_history"][user_id_str]["actions"].append({
            "action": action,
            "timestamp": datetime.now().isoformat(),
            "data": data
        })

        if len(storage.personalization["user_history"][user_id_str]["actions"]) > 50:
            storage.personalization["user_history"][user_id_str]["actions"] = storage.personalization["user_history"][user_id_str]["actions"][-50:]
        await storage.save_all()

    @staticmethod
    def get_user_birth_date(user_id: int) -> Optional[str]:
        user_id_str = str(user_id)
        return storage.personalization["user_history"].get(user_id_str, {}).get("birth_date")

    @staticmethod
    def get_user_preferences(user_id: int) -> dict:
        user_id_str = str(user_id)
        return storage.personalization["user_history"].get(user_id_str, {}).get("preferences", {})

    @staticmethod
    def personalize_response(user_id: int, base_response: str, feature_type: str) -> str:
        user_history = storage.personalization["user_history"].get(str(user_id), {})
        actions = user_history.get("actions", [])

        if len(actions) < 3:
            return base_response

        recent_actions = [a["action"] for a in actions[-5:]]
        action_counts = {}
        for action in recent_actions:
            action_counts[action] = action_counts.get(action, 0) + 1

        for action, count in action_counts.items():
            if count >= 2:
                if "relationship" in action:
                    base_response = "💖 Замечаю ваш интерес к теме отношений. " + base_response
                elif "career" in action:
                    base_response = "💼 Вижу ваш фокус на карьере. " + base_response

        return base_response

# =====================
# NUMEROLOGY FEATURES
# =====================

class NumerologyFeatures:
    @staticmethod
    def calculate_life_path_number(date_str: str) -> Optional[int]:
        try:
            digits = date_str.replace('.', '')
            total = sum(int(d) for d in digits)

            while total > 9 and total not in [11, 22, 33]:
                total = sum(int(d) for d in str(total))

            return total
        except:
            return None

    @staticmethod
    def generate_daily_affirmation(date_str: str) -> str:
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

# =====================
# ZODIAC SIGNS
# =====================

ZODIAC_SIGNS = [
    ((3, 21), (4, 19), "Овен", "♈", "огонь"),
    ((4, 20), (5, 20), "Телец", "♉", "земля"),
    ((5, 21), (6, 20), "Близнецы", "♊", "воздух"),
    ((6, 21), (7, 22), "Рак", "♋", "вода"),
    ((7, 23), (8, 22), "Лев", "♌", "огонь"),
    ((8, 23), (9, 22), "Дева", "♍", "земля"),
    ((9, 23), (10, 22), "Весы", "♎", "воздух"),
    ((10, 23), (11, 21), "Скорпион", "♏", "вода"),
    ((11, 22), (12, 21), "Стрелец", "♐", "огонь"),
    ((12, 22), (12, 31), "Козерог", "♑", "земля"),
    ((1, 1), (1, 19), "Козерог", "♑", "земля"),
    ((1, 20), (2, 18), "Водолей", "♒", "воздух"),
    ((2, 19), (3, 20), "Рыбы", "♓", "вода"),
]

def get_zodiac_sign(date_str: str) -> Optional[dict]:
    """Определяет знак зодиака по дате рождения DD.MM.YYYY"""
    try:
        day, month, _ = map(int, date_str.split('.'))
        for (m1, d1), (m2, d2), name, emoji, element in ZODIAC_SIGNS:
            if m1 == m2:
                if month == m1 and d1 <= day <= d2:
                    return {"name": name, "emoji": emoji, "element": element}
            elif m1 < m2:
                if (month == m1 and day >= d1) or (month == m2 and day <= d2):
                    return {"name": name, "emoji": emoji, "element": element}
        return None
    except Exception:
        return None

# =====================
# RETRY DECORATOR FOR GROQ
# =====================

def retry(max_retries=3, backoff_factor=1.0):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if retries == max_retries - 1:
                        raise
                    wait = backoff_factor * (2 ** retries)
                    logger.warning("Retry %s/%s after %ss: %s", retries + 1, max_retries, wait, e)
                    await asyncio.sleep(wait)
                    retries += 1
        return wrapper
    return decorator

# =====================
# GROQ API WITH RETRY
# =====================

@retry(max_retries=3, backoff_factor=0.5)
async def _ask_groq_request(prompt: str, system_prompt_key: str = "default") -> str:
    url = "https://api.groq.com/openai/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": GROQ_SYSTEM_PROMPTS.get(system_prompt_key, GROQ_SYSTEM_PROMPTS["default"])},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.6,
        "max_tokens": 1500
    }

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=90)) as session:
        async with session.post(url, headers=headers, json=data) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                logger.error("GROQ API ERROR %s: %s", resp.status, error_text)
                raise ValueError("Groq API error")
            result = await resp.json()
            return result["choices"][0]["message"]["content"].strip()

async def ask_groq(prompt: str, system_prompt_key: str = "default") -> str:
    try:
        return await _ask_groq_request(prompt, system_prompt_key)
    except Exception as e:
        logger.error("GROQ ERROR: %s", e)
        return "🔮 Произошла ошибка при обработке запроса. Попробуйте позже."

async def generate_ai_affirmation(date_str: str, life_number: int, target_date_str: str, period: str = "day") -> str:
    period_names = {
        "day": "день",
        "week": "неделю",
        "month": "месяц"
    }

    period_display = period_names.get(period, "день")
    prompt = f"""
Ты - профессиональный психолог и нумеролог-консультант премиум-уровня.

Создай персональную аффирмацию на {period_display}.

Данные человека:
- Дата рождения: {date_str}
- Число жизненного пути: {life_number}
- Начало периода: {target_date_str}

Требования:

ФОРМАТ:
- 1 предложение (допустимо 2, если необходимо)
- от первого лица ("я")
- не более 20 слов для дня, не более 25 слов для недели/месяца

СТИЛЬ:
- спокойный
- уверенный
- поддерживающий
- без пафоса
- без эзотерических терминов
- без мистики и абстрактной философии

СМЫСЛ:
- отражает сильные стороны числа {life_number}
- практичная формулировка, применимая в реальной жизни
- для недели и месяца - фокус на устойчивости и стратегии, а не на одном дне

ЗАПРЕЩЕНО:
- слова "вселенная", "карма", "энергетические потоки"
- клише из мотивационных цитат
- объяснения или комментарии

Верни ТОЛЬКО текст аффирмации. Без кавычек. Без пояснений.
"""

    try:
        result = await ask_groq(prompt, "default")
        return result.strip()
    except Exception:
        return NumerologyFeatures.generate_daily_affirmation(date_str)

# =====================
# KEYBOARDS
# =====================

def main_menu(user_id: int = None):
    keyboard = [
        [KeyboardButton(text="🔮 Мой профиль")],
        [KeyboardButton(text="♈ Гороскоп"), KeyboardButton(text="🔢 Нумерология")],
        [KeyboardButton(text="💞 Совместимость")],
        [KeyboardButton(text="✨ Карта дня")]
    ]

    if user_id in ADMIN_IDS:
        keyboard.append([KeyboardButton(text="👑 Админ-панель")])

    keyboard.append([KeyboardButton(text="ℹ️ О боте")])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        input_field_placeholder="Выберите действие..."
    )

def admin_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="👥 Пользователи")],
            [KeyboardButton(text="📢 Рассылка")],
            [KeyboardButton(text="🔙 В главное меню")]
        ],
        resize_keyboard=True
    )

def horoscope_type_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🌞 На сегодня", callback_data="horoscope_today"),
                InlineKeyboardButton(text="🌙 На завтра", callback_data="horoscope_tomorrow")
            ],
            [
                InlineKeyboardButton(text="📅 На неделю", callback_data="horoscope_week"),
                InlineKeyboardButton(text="📆 На месяц", callback_data="horoscope_month")
            ]
        ]
    )

# =====================
# UTILITY FUNCTIONS
# =====================

def is_date(text: str) -> bool:
    try:
        DateModel(date_str=text)
        return True
    except:
        return False

def format_user_name(user: types.User) -> str:
    name_parts = []
    if user.first_name:
        name_parts.append(user.first_name)
    if user.last_name:
        name_parts.append(user.last_name)
    return " ".join(name_parts) if name_parts else "Дорогой друг"

def calculate_active_users():
    now = datetime.now()
    active_count = 0
    inactive_count = 0

    for user_id_str, user_data in storage.users.items():
        if "last_active" in user_data:
            try:
                last_active = datetime.strptime(user_data["last_active"], "%Y-%m-%d %H:%M:%S")
                days_inactive = (now - last_active).days

                if days_inactive <= 30:
                    active_count += 1
                else:
                    inactive_count += 1
            except:
                active_count += 1
        else:
            active_count += 1

    return active_count, inactive_count

# =====================
# SAFE REPLY HELPER
# =====================

async def safe_reply(message: Message, text: str, reply_markup=None):
    """Отправка с Markdown, fallback на plain text при ошибке"""
    try:
        await message.answer(text, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception:
        try:
            clean_text = text.replace('*', '').replace('_', '').replace('`', '')
            await message.answer(clean_text, reply_markup=reply_markup)
        except Exception as e:
            logger.error("Failed to send message: %s", e)
            await message.answer(
                "Произошла ошибка при отправке результата. Попробуйте ещё раз.",
                reply_markup=reply_markup
            )

# =====================
# HANDLERS
# =====================

@router.message(CommandStart())
async def start(m: Message):
    user_id = m.from_user.id
    username = m.from_user.username or ""
    first_name = m.from_user.first_name or ""
    last_name = m.from_user.last_name or ""

    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    is_new_user = str(user_id) not in storage.users

    if is_new_user:
        storage.users[str(user_id)] = {
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "joined": now_str,
            "last_active": now_str,
            "total_requests": 0
        }
        storage.stats["total_users"] = len(storage.users)
        storage.stats["daily_stats"]["new_users"] = storage.stats["daily_stats"].get("new_users", 0) + 1
        storage.stats["user_registration_dates"][str(user_id)] = now_str
    else:
        storage.users[str(user_id)]["last_active"] = now_str

    storage.stats["user_last_activity"][str(user_id)] = now_str
    await storage.save_all()

    user_name = format_user_name(m.from_user)

    welcome_messages = [
        f"✨ Приветствую, {user_name}! Я — ваш личный астро-нумеролог.",
        f"🌟 Добро пожаловать, {user_name}! Готовы раскрыть тайны звёзд и чисел?",
        f"🔮 Здравствуйте, {user_name}! Звёзды и числа расскажут многое о вашем пути.",
        f"💫 Рад видеть вас, {user_name}! Давайте исследуем мир астрологии и нумерологии вместе."
    ]

    welcome_text = random.choice(welcome_messages) + "\n\n" + "Выберите, что вас интересует:"

    await m.answer(welcome_text, reply_markup=main_menu(user_id))
    await PersonalizationEngine.update_user_profile(user_id, "start")

@router.message(lambda m: m.text == "🔮 Мой профиль")
async def profile_main(m: Message):
    user_id = m.from_user.id
    await PersonalizationEngine.update_user_profile(user_id, "profile_request")
    await m.answer(
        "🔮 *Мой профиль*\n\n"
        "Введите вашу дату рождения в формате ДД.ММ.ГГГГ\n\n"
        "Например: 15.05.1990\n\n"
        "Я составлю ваш комбинированный портрет:\n"
        "• Знак зодиака и стихия ♈\n"
        "• Число жизненного пути 🔢\n"
        "• Черты личности 🔥\n"
        "• Сильные стороны 💪\n"
        "• Карьера и отношения 💫\n"
        "• Персональные рекомендации 📈",
        parse_mode="Markdown",
        reply_markup=main_menu(user_id)
    )

@router.message(lambda m: m.text == "💞 Совместимость")
async def compatibility_main(m: Message):
    user_id = m.from_user.id
    await PersonalizationEngine.update_user_profile(user_id, "compatibility_request_general")
    await m.answer(
        "💞 *Совместимость*\n\n"
        "Введите две даты рождения через пробел:\n\n"
        "Например: 15.05.1990 22.08.1988\n\n"
        "Я проанализирую совместимость по:\n"
        "• Знакам зодиака и стихиям ♈♌\n"
        "• Числам жизненного пути 🔢\n"
        "• Типам отношений 💑\n"
        "• Сильным сторонам пары 💪\n"
        "• Зонам роста отношений 🔄",
        parse_mode="Markdown",
        reply_markup=main_menu(user_id)
    )

@router.message(lambda m: m.text == "♈ Гороскоп")
async def horoscope_main(m: Message):
    user_id = m.from_user.id
    await PersonalizationEngine.update_user_profile(user_id, "horoscope_request")
    await m.answer(
        "♈ *Гороскоп*\n\n"
        "Выберите период для вашего астро-нумерологического гороскопа:",
        parse_mode="Markdown",
        reply_markup=horoscope_type_menu()
    )

@router.callback_query(lambda c: c.data.startswith("horoscope_"))
async def process_horoscope_type(callback: types.CallbackQuery):
    h_type = callback.data.split("_")[1]

    type_names = {
        "today": "сегодня 🌞",
        "tomorrow": "завтра 🌙",
        "week": "неделю 📅",
        "month": "месяц 📆"
    }

    await callback.message.edit_text(
        f"🌟 *Гороскоп на {type_names[h_type]}*\n\n"
        "Введите вашу дату рождения в формате ДД.ММ.ГГГГ\n\n"
        "Я создам персонализированный гороскоп:\n"
        "• Общий настрой дня 🌈\n"
        "• Сфера удачи 🍀\n"
        "• Совет от чисел 💭\n"
        "• Число дня 🔢",
        parse_mode="Markdown"
    )

    await PersonalizationEngine.update_user_profile(callback.from_user.id, f"horoscope_{h_type}")
    await callback.answer()

@router.message(lambda m: m.text == "🔢 Нумерология")
async def numerology_main(m: Message):
    user_id = m.from_user.id
    await PersonalizationEngine.update_user_profile(user_id, "numerology_request")
    await m.answer(
        "🔢 *Нумерология*\n\n"
        "Введите вашу дату рождения в формате ДД.ММ.ГГГГ\n\n"
        "Например: 15.05.1990\n\n"
        "Я сделаю глубокий нумерологический расклад:\n"
        "• Число жизненного пути 🛤️\n"
        "• Число судьбы 🌟\n"
        "• Число характера 🔥\n"
        "• Сильные стороны 💪\n"
        "• Рекомендации для роста 📈",
        parse_mode="Markdown",
        reply_markup=main_menu(user_id)
    )

@router.message(lambda m: m.text == "✨ Карта дня")
async def daily_card_main(m: Message):
    user_id = m.from_user.id
    stored_date = PersonalizationEngine.get_user_birth_date(user_id)
    if stored_date:
        await daily_card_handler(m, stored_date)
    else:
        await PersonalizationEngine.update_user_profile(user_id, "daily_card_request")
        await m.answer(
            "✨ *Карта дня*\n\n"
            "Введите вашу дату рождения в формате ДД.ММ.ГГГГ\n\n"
            "В следующий раз я запомню вашу дату!",
            parse_mode="Markdown",
            reply_markup=main_menu(user_id)
        )

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
async def admin_stats(m: Message):
    user_id = m.from_user.id

    if user_id not in ADMIN_IDS:
        await m.answer("Доступ запрещен", reply_markup=main_menu(user_id))
        return

    active_users, inactive_users = calculate_active_users()
    storage.stats["active_users"] = active_users
    storage.stats["inactive_users"] = inactive_users
    await storage.save_all()

    total_calculations = (
        storage.stats.get("calculations", 0) +
        storage.stats.get("compatibility_checks", 0) +
        storage.stats.get("forecasts", 0) +
        storage.stats.get("horoscopes", 0)
    )

    total_users = len(storage.users)
    avg_requests = total_calculations / total_users if total_users > 0 else 0

    current_year = datetime.now().year
    users_this_month = 0
    users_this_year = 0

    for reg_date in storage.stats.get("user_registration_dates", {}).values():
        try:
            reg_datetime = datetime.strptime(reg_date, "%Y-%m-%d %H:%M:%S")
            if reg_datetime.year == current_year:
                users_this_year += 1
                if reg_datetime.month == datetime.now().month:
                    users_this_month += 1
        except:
            pass

    stats_text = f"""
📊 *Статистика бота*

👥 *Пользователи:*
• Всего пользователей: {total_users}
• Активных (последние 30 дней): {active_users}
• Неактивных (более 30 дней): {inactive_users}
• Новых в этом году: {users_this_year}
• Новых в этом месяце: {users_this_month}

📈 *Анализов выполнено (всего: {total_calculations}):*
• Профилей и нумерологий: {storage.stats.get("calculations", 0)}
• Проверок совместимости: {storage.stats.get("compatibility_checks", 0)}
• Прогнозов (архив): {storage.stats.get("forecasts", 0)}
• Персональных гороскопов: {storage.stats.get("horoscopes", 0)}

📊 *Средние показатели:*
• Запросов на пользователя: {avg_requests:.1f}

📅 *За сегодня ({datetime.now().strftime("%d.%m.%Y")}):*
• Новых пользователей: {storage.stats.get("daily_stats", {}).get("new_users", 0)}
• Выполнено анализов: {storage.stats.get("daily_stats", {}).get("calculations", 0)}

🎯 *Популярные функции:*
1. {max(storage.stats.get("popular_features", {}), key=storage.stats.get("popular_features", {}).get, default="Нет данных")} ({storage.stats.get("popular_features", {}).get(max(storage.stats.get("popular_features", {}), key=storage.stats.get("popular_features", {}).get, default=""), 0)} раз)
"""

    await m.answer(stats_text, parse_mode="Markdown", reply_markup=admin_menu())

@router.message(lambda m: m.text == "👥 Пользователи")
async def admin_users(m: Message):
    user_id = m.from_user.id

    if user_id not in ADMIN_IDS:
        await m.answer("Доступ запрещен", reply_markup=main_menu(user_id))
        return

    total_users = len(storage.users)
    recent_users = []
    inactive_users_list = []

    now = datetime.now()

    for uid, user_data in list(storage.users.items())[-10:]:
        username = user_data.get("username", "без username")
        first_name = user_data.get("first_name", "")
        last_name = user_data.get("last_name", "")
        name = f"{first_name} {last_name}".strip() or f"Пользователь {uid[-4:]}"
        joined = user_data.get("joined", "неизвестно")
        last_active = user_data.get("last_active", "никогда")

        try:
            if last_active != "никогда":
                last_active_dt = datetime.strptime(last_active, "%Y-%m-%d %H:%M:%S")
                days_inactive = (now - last_active_dt).days
                status = "🟢" if days_inactive <= 7 else "🟡" if days_inactive <= 30 else "🔴"
            else:
                status = "⚪"
        except:
            status = "⚪"

        user_info = f"{status} {name} (@{username})"
        user_info += f"\n   📅 Регистрация: {joined}"
        user_info += f"\n   ⏱️ Последняя активность: {last_active}"

        try:
            if last_active != "никогда":
                last_active_dt = datetime.strptime(last_active, "%Y-%m-%d %H:%M:%S")
                days_inactive = (now - last_active_dt).days
                if days_inactive > 30:
                    inactive_users_list.append(f"{name} - неактивен {days_inactive} дней")
        except:
            pass

        recent_users.append(user_info)

    users_text = f"""
👥 *Информация о пользователях*

📊 Всего пользователей: {total_users}

📈 *Последние 10 пользователей (⚪=нет данных, 🟢=активен, 🟡=давно, 🔴=неактивен):*
{chr(10).join(recent_users) if recent_users else "• Нет данных"}

📉 *Неактивные пользователи (более 30 дней):*
{chr(10).join(inactive_users_list[:5]) if inactive_users_list else "• Нет неактивных пользователей"}

📁 Файл с пользователями: `users.json`
💾 Размер файла: {Path("users.json").stat().st_size if Path("users.json").exists() else 0} байт
"""

    await m.answer(users_text, parse_mode="Markdown", reply_markup=admin_menu())

@router.message(lambda m: m.text == "📢 Рассылка")
async def admin_broadcast(m: Message):
    user_id = m.from_user.id

    if user_id not in ADMIN_IDS:
        await m.answer("Доступ запрещен", reply_markup=main_menu(user_id))
        return

    await m.answer(
        "📢 *Функция рассылки*\n\n"
        "Эта функция находится в разработке.\n\n"
        "Скоро вы сможете отправлять сообщения всем пользователям бота.",
        parse_mode="Markdown",
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
🌟 *Астро-нумерологический бот с AI*

Я — ваш персональный астро-нумеролог, использующий искусственный интеллект для глубокого анализа.

✨ *Что я умею:*
• Создавать комбинированный профиль (астрология + нумерология)
• Составлять глубокий нумерологический портрет
• Генерировать персональные гороскопы по знаку зодиака
• Анализировать совместимость по знакам и числам
• Создавать карту дня с аффирмацией и прогнозом

🔮 *Мой подход:*
Я сочетаю астрологию (знаки зодиака, стихии) и нумерологию (числа жизненного пути) с современными психологическими знаниями. Все анализы уникальны и создаются специально для вас.

📊 *Статистика:*
• Пользователей: {storage.stats["total_users"]}
• Анализов выполнено: {storage.stats.get("calculations", 0) + storage.stats.get("compatibility_checks", 0) + storage.stats.get("horoscopes", 0)}

💡 *Совет:* Регулярно обращайтесь за анализом — звёзды и числа могут раскрывать новые грани вашего пути!

🌐 *Веб-админка:* {BASE_URL}{ADMIN_PATH}
"""

    await m.answer(about_text, parse_mode="Markdown", reply_markup=main_menu(user_id))

# =====================
# MAIN ANALYZERS
# =====================

@router.message(lambda m: is_date(m.text))
async def date_analysis_handler(m: Message):
    user_id = m.from_user.id
    date_str = m.text
    user_history = storage.personalization["user_history"].get(str(user_id), {"actions": []})
    if not user_history["actions"]:
        await process_profile(m, date_str)
        return
    last_action = user_history["actions"][-1]["action"]
    if "horoscope" in last_action:
        await horoscope_handler(m, date_str, last_action)
    elif last_action == "numerology_request":
        await process_numerology(m, date_str)
    elif last_action == "daily_card_request":
        await daily_card_handler(m, date_str)
    elif last_action in ("profile_request", "portrait_request"):
        await process_profile(m, date_str)
    elif "forecast" in last_action:
        await horoscope_handler(m, date_str, last_action)
    else:
        await process_profile(m, date_str)

async def process_profile(m: Message, date_str: str):
    user_id = m.from_user.id

    life_number = NumerologyFeatures.calculate_life_path_number(date_str)
    zodiac = get_zodiac_sign(date_str)
    zodiac_name = zodiac["name"] if zodiac else "не определён"
    zodiac_emoji = zodiac["emoji"] if zodiac else "🔮"
    zodiac_element = zodiac["element"] if zodiac else "не определена"

    await m.answer("🔮 Составляю ваш профиль...")

    storage.stats["calculations"] = storage.stats.get("calculations", 0) + 1
    storage.stats["popular_features"]["profile"] = storage.stats["popular_features"].get("profile", 0) + 1
    storage.stats["daily_stats"]["calculations"] = storage.stats["daily_stats"].get("calculations", 0) + 1

    user_id_str = str(user_id)
    if user_id_str in storage.users:
        storage.users[user_id_str]["last_active"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        storage.users[user_id_str]["total_requests"] = storage.users[user_id_str].get("total_requests", 0) + 1
        await storage.save_all()

    storage.stats["user_last_activity"][user_id_str] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await storage.save_all()

    prompt = f"""
Ты — профессиональный астро-нумеролог и психолог-консультант премиум-уровня.

Создай комбинированный портрет личности для человека, родившегося {date_str}.
Знак зодиака: {zodiac_name} (стихия: {zodiac_element}).
Число жизненного пути: {life_number if life_number else "не определено"}.

ТРЕБОВАНИЯ К СТИЛЮ:
- чистый литературный русский
- спокойный, уверенный, экспертный тон
- без мистического пафоса
- без шаблонных фраз
- обращение к человеку на «вы»
- НЕ писать от первого лица
- писать как личный консультант

СТРУКТУРА (строго соблюдать):

1. ЗНАК ЗОДИАКА + ЧИСЛО ПУТИ: ОБЗОР
Как знак {zodiac_name} (стихия {zodiac_element}) и число {life_number} сочетаются, дополняют или контрастируют друг с другом.

2. ЧЕРТЫ ЛИЧНОСТИ (АСТРО + НУМЕРО)
Опишите характер через призму обеих систем: что даёт знак зодиака, что — число пути.

3. СИЛЬНЫЕ СТОРОНЫ
3–4 качества, объединяющие астрологические и нумерологические характеристики.

4. ЗОНЫ РОСТА
Не более 3 пунктов. Честно, но поддерживающе.

5. КАРЬЕРА И РЕАЛИЗАЦИЯ
В каких ролях и форматах человек раскрывается лучше всего с учётом знака и числа.

6. ОТНОШЕНИЯ
Как знак зодиака и число пути влияют на стиль в близких отношениях.

7. ИТОГОВЫЙ ВЕКТОР
Одно ёмкое резюме личности.

ОБЪЁМ: 300–360 слов.

ЗАПРЕЩЕНО:
- писать «я»
- клише
- общие формулировки
- философские рассуждения
"""

    analysis = await ask_groq(prompt, "profile")
    personalized_analysis = PersonalizationEngine.personalize_response(user_id, analysis, "profile")

    final_response = f"""
🔮 *Ваш профиль* 🔮

{personalized_analysis}

*{zodiac_emoji} {zodiac_name} | Число пути: {life_number}*
📅 *Дата анализа:* {datetime.now().strftime("%d.%m.%Y")}
"""

    await safe_reply(m, final_response, reply_markup=main_menu(user_id))
    await PersonalizationEngine.update_user_profile(user_id, "profile_analysis", {"date": date_str}, birth_date=date_str)

async def process_numerology(m: Message, date_str: str):
    user_id = m.from_user.id

    life_number = NumerologyFeatures.calculate_life_path_number(date_str)
    zodiac = get_zodiac_sign(date_str)
    zodiac_name = zodiac["name"] if zodiac else "не определён"
    zodiac_emoji = zodiac["emoji"] if zodiac else "🔮"
    zodiac_element = zodiac["element"] if zodiac else "не определена"

    await m.answer("🔢 Анализирую ваш нумерологический портрет...")

    storage.stats["calculations"] = storage.stats.get("calculations", 0) + 1
    storage.stats["popular_features"]["numerology"] = storage.stats["popular_features"].get("numerology", 0) + 1
    storage.stats["daily_stats"]["calculations"] = storage.stats["daily_stats"].get("calculations", 0) + 1

    user_id_str = str(user_id)
    if user_id_str in storage.users:
        storage.users[user_id_str]["last_active"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        storage.users[user_id_str]["total_requests"] = storage.users[user_id_str].get("total_requests", 0) + 1
        await storage.save_all()

    storage.stats["user_last_activity"][user_id_str] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await storage.save_all()

    prompt = f"""
Ты — профессиональный нумеролог и психолог-консультант премиум-уровня.

Создай глубокий персональный нумерологический портрет для человека,
родившегося {date_str}.
Число жизненного пути: {life_number if life_number else "не определено"}.
Знак зодиака: {zodiac_name} ({zodiac_element}). Кратко упомяни, как знак дополняет число жизненного пути.

ТРЕБОВАНИЯ К СТИЛЮ:
- чистый литературный русский
- спокойный, уверенный, экспертный тон
- без мистического пафоса
- без шаблонных фраз
- обращение к человеку на «вы»
- НЕ писать от первого лица
- писать как личный консультант

СТРУКТУРА (строго соблюдать):

1. КЛЮЧЕВОЕ ЧИСЛО И СМЫСЛ ЖИЗНЕННОГО ПУТИ
Кратко и точно: как это число проявляется в характере и жизненных задачах.

2. ОСНОВНЫЕ ЧЕРТЫ ЛИЧНОСТИ
Опишите сильные и сложные стороны характера, включая внутренние противоречия.

3. СИЛЬНЫЕ СТОРОНЫ
3–4 качества, которые дают человеку устойчивость и надёжность в жизни.

4. ЗОНЫ РОСТА
Не более 3 пунктов. Честно, но поддерживающе.

5. РЕАЛИЗАЦИЯ И КАРЬЕРА
В каких ролях и форматах человек раскрывается лучше всего.

6. ОТНОШЕНИЯ И ЛИЧНАЯ ЖИЗНЬ
Как человек проявляется в близких отношениях и что для него важно.

7. ИТОГОВЫЙ ВЕКТОР
Одно ёмкое резюме личности.

ОБЪЁМ: 300–360 слов.

ЗАПРЕЩЕНО:
- писать «я»
- клише
- общие формулировки
- философские рассуждения
"""

    analysis = await ask_groq(prompt, "detailed")
    personalized_analysis = PersonalizationEngine.personalize_response(user_id, analysis, "numerology")

    final_response = f"""
🔢 *Ваш нумерологический портрет* 🔢

{personalized_analysis}

*{zodiac_emoji} {zodiac_name} | Число пути: {life_number}*
📅 *Дата анализа:* {datetime.now().strftime("%d.%m.%Y")}
"""

    await safe_reply(m, final_response, reply_markup=main_menu(user_id))
    await PersonalizationEngine.update_user_profile(user_id, "numerology_analysis", {"date": date_str}, birth_date=date_str)

@router.message(lambda m: m.text and len(m.text.split()) == 2 and all("." in part for part in m.text.split()))
async def compatibility_analysis_handler(m: Message):
    user_id = m.from_user.id
    date1, date2 = m.text.split()

    try:
        DualDateModel(date1=date1, date2=date2)
    except Exception:
        await m.answer("Пожалуйста, введите даты в правильном формате: ДД.ММ.ГГГГ ДД.ММ.ГГГГ")
        return

    await m.answer("💞 Анализирую совместимость...")

    storage.stats["compatibility_checks"] = storage.stats.get("compatibility_checks", 0) + 1
    await storage.save_all()

    life1 = NumerologyFeatures.calculate_life_path_number(date1)
    life2 = NumerologyFeatures.calculate_life_path_number(date2)
    zodiac1 = get_zodiac_sign(date1)
    zodiac2 = get_zodiac_sign(date2)
    z1_name = zodiac1["name"] if zodiac1 else "не определён"
    z1_emoji = zodiac1["emoji"] if zodiac1 else "🔮"
    z1_element = zodiac1["element"] if zodiac1 else "не определена"
    z2_name = zodiac2["name"] if zodiac2 else "не определён"
    z2_emoji = zodiac2["emoji"] if zodiac2 else "🔮"
    z2_element = zodiac2["element"] if zodiac2 else "не определена"

    prompt = f"""
Ты — профессиональный консультант по отношениям, астрологии и нумерологии премиум-уровня.

Создай персональный анализ совместимости двух людей по датам рождения:
1) {date1} — {z1_name} (стихия: {z1_element}), число пути: {life1}
2) {date2} — {z2_name} (стихия: {z2_element}), число пути: {life2}

Требования к стилю:
- чистый литературный русский
- без англицизмов и транслитерации
- тон спокойный, экспертный, уважительный
- без мистического пафоса
- без общих фраз
- обращение в третьем лице («пара», «партнёры»)

СТРУКТУРА (строго соблюдать):

1. ЗОДИАКАЛЬНАЯ СОВМЕСТИМОСТЬ
Анализ пары {z1_name}–{z2_name}: как взаимодействуют их стихии ({z1_element} и {z2_element}), что даёт это сочетание знаков.

2. НУМЕРОЛОГИЧЕСКАЯ СОВМЕСТИМОСТЬ
Как сочетаются числа жизненного пути {life1} и {life2}, что это означает для отношений.

3. ОБЩАЯ ОЦЕНКА СОВМЕСТИМОСТИ
Укажи процент совместимости и кратко объясни, за счёт каких факторов он сформирован.

4. СИЛЬНЫЕ СТОРОНЫ СОЮЗА
3–4 конкретных пункта с пояснениями.

5. ВОЗМОЖНЫЕ СЛОЖНОСТИ И РИСКИ
Не более 3 пунктов. Без обвинений, только зоны роста.

6. РЕКОМЕНДАЦИИ ДЛЯ ГАРМОНИЧНОГО РАЗВИТИЯ
Практичные советы, применимые в реальной жизни.

ОБЪЁМ: 270–300 слов.

ЗАПРЕЩЕНО:
- клише
- повторы
- философские рассуждения
- слова «карма», «вселенная», «потоки»
"""

    analysis = await ask_groq(prompt, "compatibility")
    personalized_analysis = PersonalizationEngine.personalize_response(user_id, analysis, "compatibility")

    final_response = f"""
💞 *Анализ совместимости* 💞

*{z1_emoji} {z1_name} (путь {life1}) + {z2_emoji} {z2_name} (путь {life2})*

{personalized_analysis}

*{z1_emoji} {z1_name} | Число пути: {life1}*
*{z2_emoji} {z2_name} | Число пути: {life2}*
"""
    await safe_reply(m, final_response, reply_markup=main_menu(user_id))
    await PersonalizationEngine.update_user_profile(user_id, "compatibility_analysis", {"dates": [date1, date2]})

async def horoscope_handler(m: Message, date_str: str, last_action: str):
    user_id = m.from_user.id

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
        year = today.year
        month = today.month
        target_date_start = datetime(year, month, 1)
        if month == 12:
            target_date_end = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            target_date_end = datetime(year, month + 1, 1) - timedelta(days=1)
        date_description = f"с {target_date_start.strftime('%d.%m.%Y')} по {target_date_end.strftime('%d.%m.%Y')} (на месяц)"
    else:
        target_date = today
        date_description = f"{today.strftime('%d.%m.%Y')} (сегодня)"

    await m.answer(f"♈ Создаю гороскоп на {period_display}...")

    storage.stats["horoscopes"] = storage.stats.get("horoscopes", 0) + 1
    await storage.save_all()

    life_number = NumerologyFeatures.calculate_life_path_number(date_str)
    zodiac = get_zodiac_sign(date_str)
    zodiac_name = zodiac["name"] if zodiac else "не определён"
    zodiac_emoji = zodiac["emoji"] if zodiac else "🔮"
    zodiac_element = zodiac["element"] if zodiac else "не определена"
    period_header = f"{period_display.capitalize()} ({date_description})"

    if h_type in ["today", "tomorrow"]:
        prompt = f"""
Ты — профессиональный астро-нумеролог-консультант премиум-уровня.

Создай персональный гороскоп на {period_header} для человека, родившегося {date_str}.
Знак зодиака: {zodiac_name} (стихия: {zodiac_element}).
Число жизненного пути: {life_number if life_number else 'не определено'}.

Основывай гороскоп на астрологии (характеристики знака, энергия стихии) и дополняй нумерологическими инсайтами (число жизненного пути).

Требования к стилю:
- чистый литературный русский
- тон спокойный, уверенный, как у личного консультанта
- без эзотерического пафоса
- без общих фраз
- без повторов
- обращение на «вы»
- не упоминай расчёты и формулы

Формат ответа — используй ТОЛЬКО эмодзи-разделители (БЕЗ текстовых заголовков, БЕЗ слов «вступление», «энергия дня» и т.п.):

🌅 — 1–2 предложения: дата, знак, число пути, общий настрой.

🔥 — один абзац: эмоциональный фон, уровень концентрации, внутренний ритм дня.

💼 Работа и финансы — конкретные тенденции и что лучше делать.
💬 Отношения и общение — стиль взаимодействия, возможные реакции людей.
🧘 Внутреннее состояние — энергия, усталость, мотивация.

⚡ — один абзац: реальные риски и вызовы дня.

💡 — одна практическая рекомендация.

🎯 — число удачи дня + как его использовать.

✨ — итог одним предложением.

Объём: 150–200 слов.

ЗАПРЕЩЕНО:
- писать текстовые заголовки разделов (типа «Краткое вступление», «Энергия дня», «Ключевые сферы»)
- английские слова и транслитерация
- абстрактная философия

Говори только про этот конкретный день.
"""
    elif h_type == "week":
        prompt = f"""
Ты — профессиональный астро-нумеролог-консультант премиум-уровня.

Создай персональный гороскоп на неделю ({date_description}) для человека, родившегося {date_str}.
Знак зодиака: {zodiac_name} (стихия: {zodiac_element}).
Число жизненного пути: {life_number if life_number else 'не определено'}.

Основывай гороскоп на астрологии (тенденции знака, энергия стихии) и дополняй нумерологическими инсайтами.

Стиль:
- деловой, спокойный, психологически точный
- без мистики
- без воды
- обращение на «вы»

Формат ответа — используй ТОЛЬКО эмодзи-разделители (БЕЗ текстовых заголовков):

🌟 — общий вектор недели для {zodiac_name} с числом пути {life_number}. 2–3 предложения.

📅 {target_date_start.strftime('%d.%m')}–{(target_date_start + timedelta(days=3)).strftime('%d.%m')} — тенденции первой половины: где действовать, где быть осторожнее.

📅 {(target_date_start + timedelta(days=4)).strftime('%d.%m')}–{target_date_end.strftime('%d.%m')} — тенденции второй половины: возможности и риски.

📌 — 2–3 ключевые даты недели с пояснением.

💡 — практическая стратегия на неделю.

🎯 — число недели и как оно влияет на вас.

Объём: 250–300 слов.

ЗАПРЕЩЕНО:
- текстовые заголовки разделов (типа «Общая тема недели», «Первая половина»)
- общие фразы и размытые формулировки
- повторять одно и то же разными словами
"""
    elif h_type == "month":
        prompt = f"""
Ты — профессиональный астро-нумеролог-консультант премиум-уровня.

Создай персональный гороскоп на месяц ({date_description}) для человека, родившегося {date_str}.
Знак зодиака: {zodiac_name} (стихия: {zodiac_element}).
Число жизненного пути: {life_number if life_number else 'не определено'}.

Основывай гороскоп на астрологии (характеристики знака, стихия) и дополняй нумерологическими инсайтами.

Стиль:
- экспертный, спокойный, практичный
- без мистики
- обращение на «вы»

Формат ответа — используй ТОЛЬКО эмодзи-разделители (БЕЗ текстовых заголовков):

🌟 — главный вектор месяца для {zodiac_name} с числом пути {life_number}. 2–3 предложения.

📅 1–10 — задачи первой декады, благоприятные действия, ограничения.

📅 11–20 — задачи второй декады, возможности, на что обратить внимание.

📅 21–конец месяца — задачи третьей декады, чего избегать, к чему стремиться.

📌 — 3–4 ключевые даты месяца с пояснением.

💡 — стратегическая рекомендация на месяц.

🎯 — число месяца и как его использовать в работе, отношениях, решениях.

Объём: 300–350 слов.

ЗАПРЕЩЕНО:
- текстовые заголовки разделов (типа «Общая тема месяца», «Первая декада»)
- эзотерические клише: «вселенная», «потоки», «карма»
- философские рассуждения
"""

    horoscope = await ask_groq(prompt, "horoscope")

    final_response = f"""
♈ *Ваш персональный гороскоп* ♈
*{zodiac_emoji} {zodiac_name} | Число пути: {life_number}*
*На {period_header}*

{horoscope}

📅 *Дата создания гороскопа:* {today.strftime("%d.%m.%Y %H:%M")}
"""

    await safe_reply(m, final_response, reply_markup=main_menu(user_id))
    await PersonalizationEngine.update_user_profile(user_id, f"horoscope_generated_{h_type}", {"date": date_str, "period": h_type}, birth_date=date_str)

async def daily_card_handler(m: Message, date_str: str):
    user_id = m.from_user.id
    life_number = NumerologyFeatures.calculate_life_path_number(date_str)
    zodiac = get_zodiac_sign(date_str)
    zodiac_name = zodiac["name"] if zodiac else "не определён"
    zodiac_emoji = zodiac["emoji"] if zodiac else "🔮"
    zodiac_element = zodiac["element"] if zodiac else "не определена"
    today = datetime.now().strftime("%d.%m.%Y")

    await m.answer("✨ Создаю вашу карту дня...")

    prompt = f"""
Создай персональную карту дня для человека.

Данные:
- Дата рождения: {date_str}
- Знак зодиака: {zodiac_name} (стихия: {zodiac_element})
- Число жизненного пути: {life_number}
- Дата: {today}

Ответ должен содержать РОВНО три блока:

1. АФФИРМАЦИЯ
Одно предложение от первого лица ("я"), не более 20 слов.
Должна отражать сильные стороны знака зодиака и числа пути.

2. ПРОГНОЗ ДНЯ
3-4 предложения. Конкретный прогноз на сегодня: что ожидать, на что обратить внимание.
Учитывай характеристики знака зодиака и энергию числа пути.

3. СОВЕТ ДНЯ
Одна конкретная практическая рекомендация на сегодня.

ЗАПРЕЩЕНО: «вселенная», «карма», «потоки энергии», общие мотивационные фразы, клише.
"""

    response = await ask_groq(prompt, "daily_card")

    final_text = f"""
✨ *Ваша карта дня* ✨
*{zodiac_emoji} {zodiac_name} | Число пути: {life_number}*

{response}

📅 *{today}*
"""
    await safe_reply(m, final_text, reply_markup=main_menu(user_id))
    await PersonalizationEngine.update_user_profile(user_id, "daily_card_generated", {"date": date_str}, birth_date=date_str)

# =====================
# FASTAPI ROUTES
# =====================

def verify_admin(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Проверка администратора"""
    if credentials.credentials != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True

@app.post(WEBHOOK_PATH)
async def telegram_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    """Эндпоинт для получения обновлений от Telegram"""
    logger.info(">>> WEBHOOK HIT from %s", request.client.host if request.client else "unknown")

    # Проверка secret_token для безопасности
    if WEBHOOK_SECRET and WEBHOOK_SECRET != "your-secret-token":
        secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if secret != WEBHOOK_SECRET:
            logger.warning("Webhook secret mismatch!")
            raise HTTPException(status_code=403, detail="Forbidden")

    update_data = await request.json()
    logger.info(">>> WEBHOOK update_id=%s", update_data.get("update_id", "?"))
    background_tasks.add_task(process_telegram_update, update_data)

    return {"status": "ok"}

async def process_telegram_update(update_data: dict):
    """Обработка обновления Telegram"""
    try:
        update = Update(**update_data)
        await dp.feed_update(bot, update)
    except Exception as e:
        logger.error(f"Error processing update: {e}")

@app.api_route("/", methods=["GET", "HEAD"])
async def home():
    return {"status": "running", "service": "Numerology Bot API"}

@app.api_route("/ping", methods=["GET", "HEAD"])
async def ping():
    return {"status": "pong", "timestamp": datetime.now().isoformat()}

@app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "users": len(storage.users),
        "bot": await bot.get_me() if BOT_TOKEN else "not_configured"
    }

@app.get("/debug/webhook")
async def debug_webhook():
    """Диагностика: проверить статус вебхука в Telegram"""
    try:
        info = await bot.get_webhook_info()
        return {
            "url": info.url,
            "has_custom_certificate": info.has_custom_certificate,
            "pending_update_count": info.pending_update_count,
            "last_error_date": str(info.last_error_date) if info.last_error_date else None,
            "last_error_message": info.last_error_message,
            "max_connections": info.max_connections,
            "allowed_updates": info.allowed_updates,
        }
    except Exception as e:
        return {"error": str(e)}

@app.get(ADMIN_PATH, response_class=HTMLResponse)
@limiter.limit("10/minute")
async def admin_panel(request: Request, _: bool = Depends(verify_admin)):
    """Веб-админка"""
    active_users, inactive_users = calculate_active_users()
    total_analyses = (
        storage.stats.get("calculations", 0) +
        storage.stats.get("compatibility_checks", 0) +
        storage.stats.get("forecasts", 0) +
        storage.stats.get("horoscopes", 0)
    )

    return f"""
    <html>
    <head>
        <title>Админ-панель астро-нумеробота (FastAPI)</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
            .container {{ max-width: 1200px; margin: 0 auto; }}
            .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; }}
            .stats {{ background: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            h1 {{ margin: 0; }}
            h2 {{ color: #333; border-bottom: 2px solid #667eea; padding-bottom: 10px; }}
            .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }}
            .card {{ background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            .btn {{ display: inline-block; padding: 10px 20px; background: #4CAF50; color: white; text-decoration: none; border-radius: 5px; margin: 5px; transition: background 0.3s; }}
            .btn:hover {{ background: #45a049; }}
            .api-btn {{ background: #667eea; }}
            .api-btn:hover {{ background: #5a67d8; }}
            .file-link {{ color: #667eea; text-decoration: none; }}
            .file-link:hover {{ text-decoration: underline; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🤖 Админ-панель астро-нумеробота (FastAPI)</h1>
                <p>Версия 2.0 | {datetime.now().strftime("%d.%m.%Y %H:%M")}</p>
            </div>

            <div class="stats">
                <h2>📊 Основная статистика:</h2>
                <div class="grid">
                    <div class="card">
                        <h3>👥 Пользователи</h3>
                        <p><strong>Всего:</strong> {storage.stats.get('total_users', 0)}</p>
                        <p><strong>Активных:</strong> {active_users}</p>
                        <p><strong>Неактивных:</strong> {inactive_users}</p>
                    </div>
                    <div class="card">
                        <h3>📈 Анализы</h3>
                        <p><strong>Всего анализов:</strong> {total_analyses}</p>
                        <p><strong>Портретов:</strong> {storage.stats.get('calculations', 0)}</p>
                        <p><strong>Совместимостей:</strong> {storage.stats.get('compatibility_checks', 0)}</p>
                        <p><strong>Прогнозов:</strong> {storage.stats.get('forecasts', 0)}</p>
                        <p><strong>Гороскопов:</strong> {storage.stats.get('horoscopes', 0)}</p>
                    </div>
                    <div class="card">
                        <h3>📅 Сегодня</h3>
                        <p><strong>Новых пользователей:</strong> {storage.stats.get('daily_stats', {}).get('new_users', 0)}</p>
                        <p><strong>Анализов вполнено:</strong> {storage.stats.get('daily_stats', {}).get('calculations', 0)}</p>
                        <p><strong>Дата:</strong> {datetime.now().strftime("%d.%m.%Y")}</p>
                    </div>
                </div>
            </div>

            <div class="stats">
                <h2>🔧 Действия:</h2>
                <a href="/" class="btn">🏠 Главная</a>
                <a href="/ping" class="btn">🔄 Ping</a>
                <a href="/health" class="btn">❤️ Health Check</a>
                <a href="/api/stats" class="btn api-btn">📈 API Статистика</a>
                <a href="/admin/full_report" class="btn api-btn">📋 Полный отчет</a>
                <a href="/api/docs" class="btn api-btn" target="_blank">📚 API Документация</a>
            </div>

            <div class="stats">
                <h2>📁 Файлы данных:</h2>
                <p><a href="/api/admin/users" class="file-link" target="_blank">users.json</a> ({len(storage.users)} пользователей)</p>
                <p><a href="/api/admin/stats" class="file-link" target="_blank">stats.json</a></p>
                <p><a href="/api/admin/personalization" class="file-link" target="_blank">personalization.json</a></p>
            </div>

            <div class="stats">
                <h2>🔗 Ссылки:</h2>
                <p><strong>Webhook URL:</strong> {BASE_URL}{WEBHOOK_PATH}</p>
                <p><strong>Админ ID:</strong> {ADMIN_IDS[0] if ADMIN_IDS else 'Не задан'}</p>
            </div>
        </div>
    </body>
    </html>
    """

@app.get("/admin/full_report")
@limiter.limit("10/minute")
async def admin_full_report(request: Request, _: bool = Depends(verify_admin)):
    """Полный отчет по пользователям"""
    report = []
    now = datetime.now()

    report.append("📊 ПОЛНЫЙ ОТЧЕТ ПО ПОЛЬЗОВАТЕЛЯМ")
    report.append(f"Дата генерации: {now.strftime('%d.%m.%Y %H:%M:%S')}")
    report.append(f"Всего пользователей: {len(storage.users)}")
    report.append("=" * 50)

    active_count = 0
    inactive_count = 0

    for uid, user_data in sorted(storage.users.items(), key=lambda x: x[1].get("joined", "")):
        username = user_data.get("username", "без username")
        first_name = user_data.get("first_name", "")
        last_name = user_data.get("last_name", "")
        name = f"{first_name} {last_name}".strip() or f"User{uid[-6:]}"
        joined = user_data.get("joined", "неизвестно")
        last_active = user_data.get("last_active", "никогда")
        total_requests = user_data.get("total_requests", 0)

        status = "НЕТ ДАННЫХ"
        try:
            if last_active != "никогда":
                last_active_dt = datetime.strptime(last_active, "%Y-%m-%d %H:%M:%S")
                days_inactive = (now - last_active_dt).days
                if days_inactive <= 7:
                    status = "АКТИВЕН"
                    active_count += 1
                elif days_inactive <= 30:
                    status = "ДАВНО"
                    active_count += 1
                else:
                    status = f"НЕАКТИВЕН ({days_inactive} дней)"
                    inactive_count += 1
            else:
                status = "НЕТ АКТИВНОСТИ"
        except:
            status = "ОШИБКА ДАННЫХ"

        user_line = f"👤 ID: {uid} | {name} | @{username}"
        user_line += f"\n   📅 Регистрация: {joined}"
        user_line += f"\n   ⏱️ Последняя активность: {last_active}"
        user_line += f"\n   📊 Запросов: {total_requests} | Статус: {status}"
        user_line += f"\n   {'─'*40}"

        report.append(user_line)

    report.append("=" * 50)
    report.append(f"ИТОГО: Активных: {active_count} | Неактивных: {inactive_count}")

    return HTMLResponse(content="<pre>" + "\n".join(report) + "</pre>")

# =====================
# API ENDPOINTS
# =====================

@app.get("/api/stats")
@limiter.limit("30/minute")
async def get_stats_api(request: Request):
    """API для получения статистики"""
    active_users, inactive_users = calculate_active_users()
    storage.stats["active_users"] = active_users
    storage.stats["inactive_users"] = inactive_users
    await storage.save_all()

    return storage.stats

@app.get("/api/admin/users")
@limiter.limit("10/minute")
async def get_users_api(request: Request, _: bool = Depends(verify_admin)):
    """API для получения пользователей"""
    return storage.users

@app.get("/api/admin/stats")
@limiter.limit("10/minute")
async def get_stats_raw_api(request: Request, _: bool = Depends(verify_admin)):
    """API для получения сырой статистики"""
    return storage.stats

@app.get("/api/admin/personalization")
@limiter.limit("10/minute")
async def get_personalization_api(request: Request, _: bool = Depends(verify_admin)):
    """API для получения данных персонализации"""
    return storage.personalization

# =====================
# MAIN ENTRY POINT
# =====================

if __name__ == "__main__":
    import uvicorn

    if not BOT_TOKEN:
        logger.error("ERROR: BOT_TOKEN is not set!")
        exit(1)
    if not GROQ_API_KEY:
        logger.error("ERROR: GROQ_API_KEY is not set!")
        exit(1)
    if not BASE_URL:
        logger.warning("WARNING: BASE_URL is not set! Webhook may not work properly.")

    logger.info("✨ Астро-нумерологический бот запущен!")
    logger.info(f"🌐 API Documentation: {BASE_URL}/api/docs")
    logger.info(f"🔧 Admin panel: {BASE_URL}{ADMIN_PATH}")
    logger.info(f"👑 Admin ID: {ADMIN_IDS[0] if ADMIN_IDS else 'Не задан'}")
    logger.info(f"🚀 Server running on port: {PORT}")
    logger.info("="*50)
    logger.info("🎯 Уникальные фичи включены:")
    logger.info("• Комбинированный профиль (астрология + нумерология)")
    logger.info("• Глубокий нумерологический портрет с AI")
    logger.info("• Персональные гороскопы по знаку зодиака")
    logger.info("• Совместимость по знакам и числам")
    logger.info("• Карта дня с аффирмацией")
    logger.info("• Система персонализации")
    logger.info("="*50)

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
        reload=False,
    )
