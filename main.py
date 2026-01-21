import os
import json
import asyncio
import requests
import aiohttp
import logging
logging.basicConfig(level=logging.INFO)
from pathlib import Path
from datetime import datetime
from flask import Flask, request, render_template_string
from threading import Thread
from collections import defaultdict

from aiogram import Bot, Dispatcher, Router, types
from aiogram.filters import CommandStart, Command
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
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "260219938").split(","))) if os.getenv("ADMIN_IDS") else []

MODEL_NAME = "llama-3.1-8b-instant"
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = BASE_URL + WEBHOOK_PATH
ADMIN_PATH = "/admin"

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
STATS_FILE = Path("stats.json")

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
        "daily_stats": defaultdict(int),
        "user_activity": {}
    }

def save_stats(data):
    STATS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

users = load_users()
stats = load_stats()

# =====================
# STATS TRACKING
# =====================

def update_stats(user_id: int, action: str):
    """Обновление статистики"""
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Общая статистика
    stats["total_users"] = len(users)
    stats["active_users"] = len([u for u in users.values() if u.get("last_active", "") == today])
    
    if action == "calculation":
        stats["calculations"] += 1
    elif action == "compatibility":
        stats["compatibility_checks"] += 1
    elif action == "forecast":
        stats["forecasts"] += 1
    
    # Дневная статистика
    stats["daily_stats"][today] = stats["daily_stats"].get(today, 0) + 1
    
    # Активность пользователя
    user_stats = stats["user_activity"].get(str(user_id), {
        "calculations": 0,
        "compatibility": 0,
        "forecasts": 0,
        "last_active": today
    })
    
    if action in user_stats:
        user_stats[action] += 1
    user_stats["last_active"] = today
    stats["user_activity"][str(user_id)] = user_stats
    
    save_stats(stats)

def update_user_info(user_id: int, username: str, first_name: str, last_name: str = ""):
    """Обновление информации о пользователе"""
    if str(user_id) not in users:
        users[str(user_id)] = {
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "joined": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_active": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "calculations": 0,
            "compatibility": 0,
            "forecasts": 0
        }
    else:
        users[str(user_id)]["last_active"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    save_users(users)

# =====================
# GROK API
# =====================

async def ask_groq(prompt: str, name: str) -> str:
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

def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🧮 Расчет по дате")],
            [KeyboardButton(text="📊 Совместимость")],
            [KeyboardButton(text="🔮 Прогноз на год")],
            [KeyboardButton(text="ℹ️ Помощь")]
        ],
        resize_keyboard=True
    )

def admin_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="👥 Пользователи")],
            [KeyboardButton(text="🔙 Главное меню")]
        ],
        resize_keyboard=True
    )

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
    username = m.from_user.username or ""
    first_name = m.from_user.first_name or ""
    last_name = m.from_user.last_name or ""
    
    update_user_info(user_id, username, first_name, last_name)
    
    if user_id in ADMIN_IDS:
        await m.answer(
            "👑 Привет, администратор!\nВыберите действие:",
            reply_markup=admin_menu()
        )
    else:
        await m.answer(
            "Привет! Я нумерологический бот 🔢\nВыбери действие:",
            reply_markup=main_menu()
        )

@router.message(Command("admin"))
async def admin_command(m: Message):
    if m.from_user.id in ADMIN_IDS:
        await m.answer(
            "👑 Панель администратора",
            reply_markup=admin_menu()
        )
    else:
        await m.answer("У вас нет прав администратора")

@router.message(lambda m: m.text == "🔙 Главное меню")
async def back_to_main(m: Message):
    await m.answer(
        "Главное меню:",
        reply_markup=main_menu()
    )

@router.message(lambda m: m.text == "📊 Статистика")
async def show_stats(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        await m.answer("У вас нет прав для просмотра статистики")
        return
    
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    stats_text = f"""
📊 *Статистика бота*

👥 Пользователи:
• Всего: {stats['total_users']}
• Активных сегодня: {stats['active_users']}

📈 Активность:
• Расчетов: {stats['calculations']}
• Совместимостей: {stats['compatibility_checks']}
• Прогнозов: {stats['forecasts']}

📅 За сегодня ({today}):
• Запросов: {stats['daily_stats'].get(today, 0)}
• Вчера ({yesterday}): {stats['daily_stats'].get(yesterday, 0)}
"""
    
    await m.answer(stats_text, parse_mode="Markdown", reply_markup=admin_menu())

@router.message(lambda m: m.text == "👥 Пользователи")
async def show_users(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        await m.answer("У вас нет прав для просмотра пользователей")
        return
    
    if not users:
        await m.answer("Нет данных о пользователях")
        return
    
    # Показываем последних 10 пользователей
    user_list = list(users.items())[-10:]
    users_text = "👥 *Последние 10 пользователей:*\n\n"
    
    for user_id, user_data in user_list:
        users_text += f"• {user_data.get('first_name', 'Неизвестно')}"
        if user_data.get('username'):
            users_text += f" (@{user_data['username']})"
        users_text += f"\n   ID: {user_id}\n   Зарегистрирован: {user_data.get('joined', 'N/A')}\n\n"
    
    await m.answer(users_text, parse_mode="Markdown", reply_markup=admin_menu())

@router.message(lambda m: m.text in ["🧮 Расчет по дате", "📊 Совместимость", "🔮 Прогноз на год", "ℹ️ Помощь"])
async def menu_handler(m: Message):
    user_id = m.from_user.id
    update_user_info(user_id, m.from_user.username or "", m.from_user.first_name or "")
    
    if m.text == "🧮 Расчет по дате":
        await m.answer("Введите дату рождения в формате ДД.ММ.ГГГГ")

    elif m.text == "📊 Совместимость":
        await m.answer("Введите две даты через пробел\nПример: 12.03.1995 10.05.1993")

    elif m.text == "🔮 Прогноз на год":
        await m.answer("Введите дату рождения для прогноза на год")

    elif m.text == "ℹ️ Помощь":
        await m.answer("Я рассчитываю нумерологию, совместимость и прогнозы 🔮")

@router.message(lambda m: is_date(m.text))
async def date_handler(m: Message):
    await m.answer("🔮 Анализирую дату...")
    
    user_id = m.from_user.id
    update_stats(user_id, "calculation")

    prompt = f"Сделай нумерологический анализ даты рождения {m.text}"
    result = await ask_groq(prompt, m.from_user.first_name)

    await m.answer(result, reply_markup=main_menu())

@router.message(lambda m: len(m.text.split()) == 2 and "." in m.text)
async def compatibility_handler(m: Message):
    d1, d2 = m.text.split()
    await m.answer("💞 Анализирую совместимость...")
    
    user_id = m.from_user.id
    update_stats(user_id, "compatibility")

    prompt = f"Совместимость дат: {d1} и {d2}"
    result = await ask_groq(prompt, m.from_user.first_name)

    await m.answer(result, reply_markup=main_menu())

# =====================
# FLASK WEBHOOK SERVER WITH ADMIN
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
        body {
            font-family: Arial, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .stat-number {
            font-size: 36px;
            font-weight: bold;
            color: #667eea;
        }
        .stat-label {
            color: #666;
            margin-top: 5px;
        }
        table {
            width: 100%;
            background: white;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        th, td {
            padding: 15px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }
        th {
            background-color: #f8f9fa;
            font-weight: bold;
        }
        .btn {
            display: inline-block;
            padding: 10px 20px;
            background: #667eea;
            color: white;
            text-decoration: none;
            border-radius: 5px;
            margin: 10px 5px;
        }
        .btn:hover {
            background: #5a6fd8;
        }
        .nav {
            margin-bottom: 20px;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🔢 Админ-панель нумерологического бота</h1>
        <p>Последнее обновление: {{ update_time }}</p>
    </div>
    
    <div class="nav">
        <a href="/admin" class="btn">📊 Статистика</a>
        <a href="/admin/users" class="btn">👥 Пользователи</a>
        <a href="/admin/broadcast" class="btn">📢 Рассылка</a>
    </div>
    
    {% if page == 'stats' %}
    <div class="stats-grid">
        <div class="stat-card">
            <div class="stat-number">{{ stats.total_users }}</div>
            <div class="stat-label">Всего пользователей</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">{{ stats.active_users }}</div>
            <div class="stat-label">Активных сегодня</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">{{ stats.calculations }}</div>
            <div class="stat-label">Расчетов</div>
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
            <div class="stat-number">{{ stats.daily_stats[today] }}</div>
            <div class="stat-label">Запросов сегодня</div>
        </div>
    </div>
    
    <h2>📅 Статистика по дням (последние 7 дней)</h2>
    <table>
        <tr>
            <th>Дата</th>
            <th>Запросов</th>
        </tr>
        {% for date, count in daily_stats %}
        <tr>
            <td>{{ date }}</td>
            <td>{{ count }}</td>
        </tr>
        {% endfor %}
    </table>
    
    {% elif page == 'users' %}
    <h2>👥 Последние пользователи</h2>
    <table>
        <tr>
            <th>ID</th>
            <th>Имя</th>
            <th>Username</th>
            <th>Дата регистрации</th>
            <th>Последняя активность</th>
        </tr>
        {% for user in users %}
        <tr>
            <td>{{ user.id }}</td>
            <td>{{ user.first_name }}</td>
            <td>{{ user.username }}</td>
            <td>{{ user.joined }}</td>
            <td>{{ user.last_active }}</td>
        </tr>
        {% endfor %}
    </table>
    
    {% elif page == 'broadcast' %}
    <h2>📢 Рассылка сообщений</h2>
    <form method="POST" action="/admin/broadcast">
        <textarea name="message" placeholder="Введите сообщение для рассылки..." rows="6" style="width:100%; padding:10px; margin-bottom:10px;"></textarea>
        <br>
        <button type="submit" class="btn">Отправить всем пользователям</button>
    </form>
    {% endif %}
</body>
</html>
"""

@app.route("/")
def home():
    return "Bot is running"

@app.route("/ping")
def ping():
    return "pong"

@app.route(ADMIN_PATH)
@app.route(ADMIN_PATH + "/")
def admin():
    """Главная страница админки со статистикой"""
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Получаем последние 7 дней статистики
    daily_stats_items = sorted(stats["daily_stats"].items(), reverse=True)[:7]
    
    return render_template_string(
        ADMIN_TEMPLATE,
        page='stats',
        stats=stats,
        today=today,
        daily_stats=daily_stats_items,
        update_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

@app.route(ADMIN_PATH + "/users")
def admin_users():
    """Страница со списком пользователей"""
    # Собираем данные пользователей
    users_list = []
    for user_id, user_data in list(users.items())[-50:]:  # Последние 50 пользователей
        users_list.append({
            'id': user_id,
            'username': user_data.get('username', ''),
            'first_name': user_data.get('first_name', ''),
            'joined': user_data.get('joined', ''),
            'last_active': user_data.get('last_active', '')
        })
    
    return render_template_string(
        ADMIN_TEMPLATE,
        page='users',
        users=users_list,
        update_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

@app.route(ADMIN_PATH + "/broadcast", methods=['GET', 'POST'])
def admin_broadcast():
    """Страница рассылки сообщений"""
    if request.method == 'POST':
        message = request.form.get('message', '')
        if message:
            # Здесь можно добавить логику рассылки
            # Например, асинхронную отправку сообщений всем пользователям
            return "Сообщение отправлено в очередь рассылки"
    
    return render_template_string(
        ADMIN_TEMPLATE,
        page='broadcast',
        update_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

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
    
    # Создаем необходимые файлы, если их нет
    if not USERS_FILE.exists():
        save_users({})
    if not STATS_FILE.exists():
        save_stats(load_stats())
    
    set_webhook()

    Thread(target=run_flask, daemon=True).start()

    print("Bot started")
    print(f"Admin panel available at: {BASE_URL}{ADMIN_PATH}")
    loop.run_forever()
