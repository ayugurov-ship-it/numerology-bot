import os
import logging
import asyncio
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
from flask import Flask, request, jsonify
import json
from dateutil.relativedelta import relativedelta

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Flask приложение для вебхука
app = Flask(__name__)

# Токен бота (замените на ваш)
BOT_TOKEN = os.getenv('BOT_TOKEN', 'ВАШ_ТОКЕН_ЗДЕСЬ')
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Состояния FSM
class NumerologyForm(StatesGroup):
    waiting_for_birthdate = State()
    waiting_for_relationship_type = State()
    waiting_for_partner_birthdate = State()
    waiting_for_forecast_period = State()

# Хранение данных пользователей (временное, для примера)
user_data = {}

# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ НУМЕРОЛОГИИ =====

def calculate_life_path_number(birthdate_str):
    """Вычисляет число жизненного пути"""
    try:
        day, month, year = map(int, birthdate_str.split('.'))
        total = sum(map(int, str(day))) + sum(map(int, str(month))) + sum(map(int, str(year)))
        while total > 9 and total not in [11, 22, 33]:
            total = sum(map(int, str(total)))
        return total
    except:
        return 0

def get_life_path_info(number):
    """Информация о числе жизненного пути"""
    info = {
        1: {"name": "Лидер", "traits": ["Амбициозность", "Решительность", "Независимость"], "professions": ["Руководитель", "Предприниматель"], "colors": ["Красный", "Оранжевый"]},
        2: {"name": "Дипломат", "traits": ["Чувствительность", "Гармония", "Сотрудничество"], "professions": ["Дипломат", "Психолог"], "colors": ["Серебряный", "Белый"]},
        3: {"name": "Творец", "traits": ["Креативность", "Оптимизм", "Общительность"], "professions": ["Артист", "Писатель"], "colors": ["Желтый", "Бирюзовый"]},
        4: {"name": "Строитель", "traits": ["Практичность", "Стабильность", "Трудолюбие"], "professions": ["Инженер", "Архитектор"], "colors": ["Зеленый", "Синий"]},
        5: {"name": "Свободный дух", "traits": ["Адаптивность", "Любознательность", "Авантюризм"], "professions": ["Путешественник", "Журналист"], "colors": ["Серебряный", "Серый"]},
        6: {"name": "Заботливый", "traits": ["Ответственность", "Забота", "Гармония"], "professions": ["Врач", "Учитель"], "colors": ["Розовый", "Голубой"]},
        7: {"name": "Философ", "traits": ["Аналитичность", "Интуиция", "Мудрость"], "professions": ["Ученый", "Философ"], "colors": ["Фиолетовый", "Белый"]},
        8: {"name": "Реализатор", "traits": ["Энергичность", "Организованность", "Успешность"], "professions": ["Бизнесмен", "Банкир"], "colors": ["Черный", "Золотой"]},
        9: {"name": "Гуманист", "traits": ["Сострадание", "Идеализм", "Терпимость"], "professions": ["Благотворитель", "Волонтер"], "colors": ["Красный", "Золотой"]},
        11: {"name": "Просветленный", "traits": ["Интуиция", "Вдохновение", "Озарение", "Духовность"], "professions": ["Мистик", "Художник", "Духовный учитель"], "colors": ["Серебряный", "Жемчужный"]},
        22: {"name": "Мастер-строитель", "traits": ["Видение", "Практичность", "Лидерство"], "professions": ["Архитектор", "Изобретатель"], "colors": ["Белый", "Золотой"]},
        33: {"name": "Мастер-учитель", "traits": ["Сострадание", "Вдохновение", "Мудрость"], "professions": ["Учитель", "Целитель"], "colors": ["Розовый", "Кристальный"]}
    }
    return info.get(number, {"name": "Неизвестно", "traits": [], "professions": [], "colors": []})

def calculate_destiny_number(name):
    """Вычисляет число судьбы (упрощенно)"""
    if not name:
        return 2  # Значение по умолчанию
    numerology_map = {
        'а': 1, 'б': 2, 'в': 3, 'г': 4, 'д': 5, 'е': 6, 'ё': 7, 'ж': 8, 'з': 9,
        'и': 1, 'й': 2, 'к': 3, 'л': 4, 'м': 5, 'н': 6, 'о': 7, 'п': 8, 'р': 9,
        'с': 1, 'т': 2, 'у': 3, 'ф': 4, 'х': 5, 'ц': 6, 'ч': 7, 'ш': 8, 'щ': 9,
        'ъ': 1, 'ы': 2, 'ь': 3, 'э': 4, 'ю': 5, 'я': 6
    }
    total = 0
    for char in name.lower():
        if char in numerology_map:
            total += numerology_map[char]
    while total > 9 and total not in [11, 22, 33]:
        total = sum(map(int, str(total)))
    return total

def calculate_compatibility(num1, num2, relationship_type):
    """Вычисляет совместимость"""
    compatibility_matrix = {
        'romance': {
            1: [1, 3, 5],
            2: [2, 4, 6, 8],
            3: [1, 3, 5, 9],
            4: [2, 4, 8],
            5: [1, 3, 5, 7],
            6: [2, 6, 9],
            7: [5, 7],
            8: [2, 4, 8],
            9: [3, 6, 9],
            11: [2, 4, 22],
            22: [4, 22, 11],
            33: [6, 9, 33]
        },
        'business': {
            1: [1, 8],
            2: [2, 4, 6],
            3: [3, 5],
            4: [2, 4, 8],
            5: [3, 5],
            6: [2, 6],
            7: [7],
            8: [1, 4, 8],
            9: [9],
            11: [11, 22],
            22: [4, 22],
            33: [33]
        },
        'friendship': {
            1: [1, 3, 5],
            2: [2, 4, 6],
            3: [1, 3, 5, 9],
            4: [2, 4, 8],
            5: [1, 3, 5, 7],
            6: [2, 6, 9],
            7: [5, 7],
            8: [2, 4, 8],
            9: [3, 6, 9],
            11: [2, 11, 33],
            22: [4, 8, 22],
            33: [6, 9, 11, 33]
        }
    }
    
    matrix = compatibility_matrix.get(relationship_type, compatibility_matrix['friendship'])
    compatible_numbers = matrix.get(num1, [])
    
    if num2 in compatible_numbers:
        return "✅ Высокая совместимость"
    elif abs(num1 - num2) <= 2:
        return "⚠️ Средняя совместимость"
    else:
        return "❌ Низкая совместимость"

def generate_forecast(birth_number, period):
    """Генерирует прогноз на период"""
    forecasts = {
        'week': {
            1: "Отличная неделя для новых начинаний и лидерства.",
            2: "Неделя гармонии и сотрудничества.",
            11: "Время духовного роста и интуитивных озарений."
        },
        'month': {
            1: "Месяц активных действий и достижений.",
            2: "Месяц дипломатии и построения отношений.",
            11: "Месяц духовного просветления и творчества."
        },
        '3months': {
            1: "Квартал решительных действий и карьерного роста.",
            2: "Квартал партнерства и совместных проектов.",
            11: "Квартал глубоких духовных открытий."
        },
        '6months': {
            1: "Полгода смелых решений и новых направлений.",
            2: "Полгода укрепления связей и гармонии.",
            11: "Полгода трансформации и духовного развития."
        },
        'year': {
            1: "Год больших перемен и личных достижений.",
            2: "Год сотрудничества и взаимопонимания.",
            11: "Год духовного пробуждения и миссии."
        }
    }
    
    return forecasts.get(period, {}).get(birth_number, "Прогноз в процессе разработки.")

# ===== ОСНОВНЫЕ ОБРАБОТЧИКИ =====

@dp.message_handler(commands=['start', 'help'])
async def send_welcome(message: types.Message):
    """Обработчик команды /start"""
    logger.info(f"👤 Пользователь {message.from_user.id} запустил бота")
    
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = [
        KeyboardButton("Моя нумерология"),
        KeyboardButton("Нумеропортрет"),
        KeyboardButton("Совместимость"),
        KeyboardButton("Прогноз"),
        KeyboardButton("Гороскоп")
    ]
    keyboard.add(*buttons)
    
    welcome_text = """✨ Добро пожаловать в SoulCode Numerology Bot! ✨

Я помогу вам:
• Узнать свою нумерологию
• Получить подробный нумеропортрет
• Проверить совместимость с партнером
• Получить прогноз на период

Выберите действие:"""
    
    await message.answer(welcome_text, reply_markup=keyboard)

@dp.message_handler(lambda message: message.text == "Моя нумерология")
async def my_numerology(message: types.Message):
    """Обработчик для Моя нумерология"""
    logger.info(f"📊 Пользователь {message.from_user.id} запросил нумерологию")
    
    # Запрашиваем дату рождения
    await message.answer("Введите вашу дату рождения в формате ДД.ММ.ГГГГ:")
    await NumerologyForm.waiting_for_birthdate.set()

@dp.message_handler(state=NumerologyForm.waiting_for_birthdate)
async def process_birthdate(message: types.Message, state: FSMContext):
    """Обработка даты рождения"""
    try:
        # Проверяем формат даты
        datetime.strptime(message.text, '%d.%m.%Y')
        birthdate = message.text
        
        # Сохраняем данные пользователя
        user_id = message.from_user.id
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id]['birthdate'] = birthdate
        
        # Вычисляем числа
        life_path = calculate_life_path_number(birthdate)
        destiny = calculate_destiny_number(message.from_user.first_name or "")
        
        # Получаем информацию о числе жизненного пути
        life_info = get_life_path_info(life_path)
        
        # Формируем ответ
        response = f"""🔮 Ваша персональная нумерология

Дата рождения: {birthdate}

Ключевые числа:
• Число жизненного пути {life_path}: {life_info['name']}
• Число судьбы {destiny}: Ваше предназначение
• Число души 1: Ваши внутренние желания
• Число личности 5: Как вас видят другие

Основные черты:
{chr(10).join(['• ' + trait for trait in life_info['traits']])}

Профессии: {', '.join(life_info['professions'][:3])}

Совместимость: с числами 2, 4, 22

Талисманы: Селенит, Лабрадорит
Цвета: {', '.join(life_info['colors'])}

Число дня: 5 (энергия сегодня)

Ваша аффирмация:
Я вдохновляю окружающих своим светом и духовным видением"""
        
        await message.answer(response)
        await state.finish()
        
    except ValueError:
        await message.answer("❌ Неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ:")
        return

@dp.message_handler(lambda message: message.text == "Нумеропортрет")
async def numeroportrait(message: types.Message):
    """Обработчик для Нумеропортрет"""
    logger.info(f"🎨 Пользователь {message.from_user.id} запросил нумеропортрет")
    
    # Проверяем, есть ли сохраненная дата рождения
    user_id = message.from_user.id
    saved_birthdate = user_data.get(user_id, {}).get('birthdate')
    
    keyboard = InlineKeyboardMarkup()
    
    if saved_birthdate:
        keyboard.add(
            InlineKeyboardButton(
                f"Использовать мою дату ({saved_birthdate})", 
                callback_data=f"use_saved_{saved_birthdate}"
            )
        )
    
    keyboard.add(
        InlineKeyboardButton("Ввести новую дату", callback_data="enter_new_date")
    )
    
    await message.answer("Создаю нумерологический портрет...\n\nВыберите действие:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("use_saved_"))
async def process_use_saved(callback_query: types.CallbackQuery):
    """Обработчик для использования сохраненной даты рождения"""
    logger.info(f"📩 Получен callback: {callback_query.data}")
    
    try:
        # Извлекаем дату из callback_data
        birthdate = callback_query.data.replace("use_saved_", "")
        
        # Вычисляем числа для портрета
        life_path = calculate_life_path_number(birthdate)
        life_info = get_life_path_info(life_path)
        
        # Формируем подробный портрет
        portrait = f"""🎭 Ваш нумерологический портрет

📅 Дата рождения: {birthdate}

🎯 Число жизненного пути {life_path} - {life_info['name']}
Путь: {life_info['name']} стремится к {life_info['traits'][0].lower()} и {life_info['traits'][1].lower()}

🌟 Сильные стороны:
• {life_info['traits'][0]}
• {life_info['traits'][1] if len(life_info['traits']) > 1 else 'Мудрость'}
• {life_info['traits'][2] if len(life_info['traits']) > 2 else 'Гармония'}

💼 Рекомендуемые сферы деятельности:
{chr(10).join(['• ' + prof for prof in life_info['professions']])}

🎨 Творческий потенциал: Высокий
💖 Эмоциональная сфера: Сбалансированная
🧠 Интеллектуальные способности: Развитые

🌈 Рекомендации:
1. Используйте цвета: {', '.join(life_info['colors'])}
2. Развивайте {life_info['traits'][0].lower()}
3. Избегайте конфликтов в числах 3 и 7

✨ Ваш девиз: "Я принимаю свою уникальность и следую своему пути" """
        
        await bot.send_message(callback_query.from_user.id, portrait)
        await callback_query.answer("Портрет создан!")
        
    except Exception as e:
        logger.error(f"❌ Ошибка в обработчике use_saved: {e}")
        await bot.send_message(callback_query.from_user.id, "❌ Произошла ошибка при создании портрета")
        await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data == "enter_new_date")
async def process_enter_new_date(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработчик для ввода новой даты"""
    await bot.send_message(callback_query.from_user.id, "Введите дату рождения в формате ДД.ММ.ГГГГ:")
    await NumerologyForm.waiting_for_birthdate.set()
    await callback_query.answer()

@dp.message_handler(lambda message: message.text == "Совместимость")
async def compatibility_start(message: types.Message):
    """Начало проверки совместимости"""
    logger.info(f"💑 Пользователь {message.from_user.id} запросил совместимость")
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = [
        InlineKeyboardButton("🇺🇸 Романтика", callback_data="compat_romance"),
        InlineKeyboardButton("🇬🇧 Бизнес", callback_data="compat_business"),
        InlineKeyboardButton("🇩🇪 Дружба", callback_data="compat_friendship"),
        InlineKeyboardButton("🇫🇷 Семья", callback_data="compat_family"),
        InlineKeyboardButton("🇦🇹 Духовная", callback_data="compat_spiritual")
    ]
    keyboard.add(*buttons)
    
    await message.answer("Нумерологическая совместимость\nВыберите тип отношений для анализа:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("compat_"))
async def process_compatibility_type(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработка выбора типа отношений"""
    relationship_type = callback_query.data.replace("compat_", "")
    
    # Сохраняем тип отношений в состоянии
    await state.update_data(relationship_type=relationship_type)
    
    # Проверяем, есть ли у пользователя сохраненная дата рождения
    user_id = callback_query.from_user.id
    saved_birthdate = user_data.get(user_id, {}).get('birthdate')
    
    keyboard = InlineKeyboardMarkup()
    
    if saved_birthdate:
        keyboard.add(
            InlineKeyboardButton(
                f"Использовать мою дату ({saved_birthdate})", 
                callback_data=f"compat_use_my_{saved_birthdate}"
            )
        )
    
    keyboard.add(
        InlineKeyboardButton("Ввести свою дату", callback_data="compat_enter_my")
    )
    
    await bot.send_message(
        callback_query.from_user.id,
        f"Вы выбрали: {relationship_type.capitalize()}\n\nТеперь введите дату рождения партнера в формате ДД.ММ.ГГГГ:",
        reply_markup=keyboard
    )
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("compat_use_my_"))
async def process_compat_use_my(callback_query: types.CallbackQuery, state: FSMContext):
    """Использовать свою дату для совместимости"""
    birthdate = callback_query.data.replace("compat_use_my_", "")
    user_id = callback_query.from_user.id
    
    # Сохраняем свою дату в состоянии
    await state.update_data(my_birthdate=birthdate)
    
    await bot.send_message(
        callback_query.from_user.id,
        f"✅ Используем вашу дату рождения: {birthdate}\n\nТеперь введите дату рождения партнера в формате ДД.ММ.ГГГГ:"
    )
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data == "compat_enter_my")
async def process_compat_enter_my(callback_query: types.CallbackQuery):
    """Ввод своей даты для совместимости"""
    await bot.send_message(
        callback_query.from_user.id,
        "Введите свою дату рождения в формате ДД.ММ.ГГГГ:"
    )
    await NumerologyForm.waiting_for_birthdate.set()
    await callback_query.answer()

@dp.message_handler(state=NumerologyForm.waiting_for_birthdate)
async def process_partner_birthdate(message: types.Message, state: FSMContext):
    """Обработка даты рождения партнера для совместимости"""
    try:
        # Проверяем формат даты
        datetime.strptime(message.text, '%d.%m.%Y')
        birthdate = message.text
        
        # Получаем данные из состояния
        data = await state.get_data()
        relationship_type = data.get('relationship_type', 'friendship')
        my_birthdate = data.get('my_birthdate')
        
        if not my_birthdate:
            # Если своей даты еще нет, сохраняем как свою и запрашиваем партнера
            await state.update_data(my_birthdate=birthdate)
            await message.answer("✅ Ваша дата сохранена. Теперь введите дату рождения партнера:")
            return
        
        # Вычисляем числа
        my_number = calculate_life_path_number(my_birthdate)
        partner_number = calculate_life_path_number(birthdate)
        
        # Получаем совместимость
        compatibility = calculate_compatibility(my_number, partner_number, relationship_type)
        
        # Формируем ответ
        response = f"""💞 Нумерологическая совместимость

Тип отношений: {relationship_type.capitalize()}

Ваше число: {my_number} ({get_life_path_info(my_number)['name']})
Число партнера: {partner_number} ({get_life_path_info(partner_number)['name']})

Результат: {compatibility}

Рекомендации:
• Учитывайте особенности друг друга
• Проявляйте терпение
• Используйте сильные стороны обоих чисел"""
        
        await message.answer(response)
        await state.finish()
        
    except ValueError:
        await message.answer("❌ Неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ:")

@dp.message_handler(lambda message: message.text == "Прогноз")
async def forecast_start(message: types.Message):
    """Начало получения прогноза"""
    logger.info(f"🔮 Пользователь {message.from_user.id} запросил прогноз")
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = [
        InlineKeyboardButton("На неделю", callback_data="forecast_week"),
        InlineKeyboardButton("На месяц", callback_data="forecast_month"),
        InlineKeyboardButton("На 3 месяца", callback_data="forecast_3months"),
        InlineKeyboardButton("На полгода", callback_data="forecast_6months"),
        InlineKeyboardButton("На год", callback_data="forecast_year")
    ]
    keyboard.add(*buttons)
    
    await message.answer("Нумерологический прогноз\nВыберите период для прогноза:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("forecast_"))
async def process_forecast_period(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработка выбора периода для прогноза"""
    period = callback_query.data.replace("forecast_", "")
    
    # Сохраняем период в состоянии
    await state.update_data(forecast_period=period)
    
    # Проверяем, есть ли у пользователя сохраненная дата рождения
    user_id = callback_query.from_user.id
    saved_birthdate = user_data.get(user_id, {}).get('birthdate')
    
    keyboard = InlineKeyboardMarkup()
    
    if saved_birthdate:
        keyboard.add(
            InlineKeyboardButton(
                f"Использовать мою дату ({saved_birthdate})", 
                callback_data=f"forecast_use_{saved_birthdate}"
            )
        )
    
    keyboard.add(
        InlineKeyboardButton("Ввести новую дату", callback_data="forecast_enter_new")
    )
    
    period_names = {
        'week': "неделю",
        'month': "месяц",
        '3months': "3 месяца",
        '6months': "полгода",
        'year': "год"
    }
    
    await bot.send_message(
        callback_query.from_user.id,
        f"Вы выбрали прогноз на {period_names.get(period, period)}\n\nВыберите дату рождения:",
        reply_markup=keyboard
    )
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("forecast_use_"))
async def process_forecast_use(callback_query: types.CallbackQuery, state: FSMContext):
    """Использовать сохраненную дату для прогноза"""
    birthdate = callback_query.data.replace("forecast_use_", "")
    
    # Получаем период из состояния
    data = await state.get_data()
    period = data.get('forecast_period', 'month')
    
    # Вычисляем число жизненного пути
    life_path = calculate_life_path_number(birthdate)
    
    # Генерируем прогноз
    forecast = generate_forecast(life_path, period)
    
    # Формируем ответ
    period_names = {
        'week': "неделю",
        'month': "месяц",
        '3months': "3 месяца",
        '6months': "полгода",
        'year': "год"
    }
    
    response = f"""📅 Прогноз на {period_names.get(period, period)}

Дата рождения: {birthdate}
Ваше число: {life_path} ({get_life_path_info(life_path)['name']})

✨ Прогноз:
{forecast}

🔮 Рекомендации:
• Слушайте свою интуицию
• Проявляйте активность в ключевые дни
• Используйте энергию числа {life_path}

💫 Благоприятные дни для начинаний:
- Сегодня и завтра
- Дни с числом {life_path} в дате"""

    await bot.send_message(callback_query.from_user.id, response)
    await state.finish()
    await callback_query.answer("Прогноз готов!")

@dp.callback_query_handler(lambda c: c.data == "forecast_enter_new")
async def process_forecast_enter_new(callback_query: types.CallbackQuery, state: FSMContext):
    """Ввод новой даты для прогноза"""
    await bot.send_message(
        callback_query.from_user.id,
        "Введите дату рождения в формате ДД.ММ.ГГГГ:"
    )
    await NumerologyForm.waiting_for_birthdate.set()
    await callback_query.answer()

@dp.message_handler(lambda message: message.text == "Гороскоп")
async def horoscope(message: types.Message):
    """Обработчик для Гороскоп (заглушка)"""
    await message.answer("✨ Функция гороскопа в разработке. Скоро будет доступна!")

# ===== WEBHOOK ОБРАБОТЧИКИ =====

@app.route('/webhook', methods=['POST'])
async def webhook():
    """Обработчик вебхука от Telegram"""
    update = types.Update(**request.json)
    await dp.process_update(update)
    return jsonify({'status': 'ok'})

@app.route('/ping', methods=['HEAD'])
def ping():
    """Проверка работоспособности"""
    return '', 200

# ===== ЗАПУСК БОТА =====

async def on_startup(dp):
    """Действия при запуске бота"""
    logger.info("🚀 Бот запущен")
    # Установка вебхука (если нужно)
    # await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(dp):
    """Действия при остановке бота"""
    logger.info("🛑 Бот остановлен")
    # Удаление вебхука
    # await bot.delete_webhook()

if __name__ == '__main__':
    # Для запуска через вебхук (например, на Heroku)
    # port = int(os.environ.get('PORT', 5000))
    # app.run(host='0.0.0.0', port=port)
    
    # Для запуска через polling (локально)
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup, on_shutdown=on_shutdown)
