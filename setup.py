from pathlib import Path
import re
import py_compile

ROOT = Path(__file__).resolve().parent
MAIN = ROOT / "main.py"
MARKER = "# === INLINE BIRTH DATE CALENDAR ==="

MONTHS_RU = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
WEEKDAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

CALENDAR_BLOCK = r'''

# === INLINE BIRTH DATE CALENDAR ===
MONTHS_RU = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
WEEKDAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def birth_years_keyboard(start=1920):
    rows = []
    for y in range(start, start + 100, 10):
        rows.append([InlineKeyboardButton(text=f"{y}–{y+9}", callback_data=f"birth_decade:{y}")])
    rows.append([
        InlineKeyboardButton(text="◀️ Старше", callback_data=f"birth_year_page:{start-100}"),
        InlineKeyboardButton(text="Младше ▶️", callback_data=f"birth_year_page:{start+100}")
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def birth_years_keyboard_page(decade):
    rows = []
    for offset in (0, 5):
        rows.append([InlineKeyboardButton(text=str(y), callback_data=f"birth_year:{y}") for y in range(decade + offset, decade + offset + 5)])
    rows.append([InlineKeyboardButton(text="← К десятилетиям", callback_data="birth_year_page:1920")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def birth_month_keyboard(year):
    rows = []
    for start in (1, 4, 7, 10):
        rows.append([InlineKeyboardButton(text=MONTHS_RU[m-1], callback_data=f"birth_month:{year}:{m}") for m in range(start, start + 3)])
    rows.append([InlineKeyboardButton(text="← К годам", callback_data="birth_year_page:1920")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def birth_calendar_keyboard(year, month):
    prev_y, prev_m = (year - 1, 12) if month == 1 else (year, month - 1)
    next_y, next_m = (year + 1, 1) if month == 12 else (year, month + 1)
    rows = [[
        InlineKeyboardButton(text="‹", callback_data=f"birth_cal:{prev_y}:{prev_m}"),
        InlineKeyboardButton(text=f"{MONTHS_RU[month-1]} {year}", callback_data=f"birth_month:{year}:{month}"),
        InlineKeyboardButton(text="›", callback_data=f"birth_cal:{next_y}:{next_m}")
    ], [InlineKeyboardButton(text=d, callback_data="birth_noop") for d in WEEKDAYS_RU]]
    for week in calendar.monthcalendar(year, month):
        rows.append([
            InlineKeyboardButton(text=str(day) if day else "·", callback_data=f"birth_date:{day:02d}.{month:02d}.{year}" if day else "birth_noop")
            for day in week
        ])
    rows.append([
        InlineKeyboardButton(text="← Месяцы", callback_data=f"birth_month:{year}:{month}"),
        InlineKeyboardButton(text="📅 Годы", callback_data="birth_year_page:1920")
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def show_birth_date_picker(message: Message):
    await message.answer(
        "📅 *Выберите дату рождения*\n\n"
        "Сначала выберите год, затем месяц и день.\n"
        "Ничего вводить вручную не нужно.",
        parse_mode="Markdown",
        reply_markup=birth_years_keyboard()
    )


@router.callback_query(lambda c: c.data == "birth_noop")
async def birth_noop(callback: types.CallbackQuery):
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("birth_year_page:"))
async def birth_year_page(callback: types.CallbackQuery):
    start = int(callback.data.split(":")[1])
    start = max(1700, min(2020, start))
    await callback.answer()
    await callback.message.edit_text("📅 *Выберите год рождения*", parse_mode="Markdown", reply_markup=birth_years_keyboard(start))


@router.callback_query(lambda c: c.data and c.data.startswith("birth_decade:"))
async def birth_decade(callback: types.CallbackQuery):
    decade = int(callback.data.split(":")[1])
    await callback.answer()
    await callback.message.edit_text(f"📅 *{decade}–{decade+9}*\n\nВыберите год:", parse_mode="Markdown", reply_markup=birth_years_keyboard_page(decade))


@router.callback_query(lambda c: c.data and c.data.startswith("birth_year:"))
async def birth_year(callback: types.CallbackQuery):
    year = int(callback.data.split(":")[1])
    await callback.answer()
    await callback.message.edit_text(f"📅 *Выберите месяц — {year}*", parse_mode="Markdown", reply_markup=birth_month_keyboard(year))


@router.callback_query(lambda c: c.data and c.data.startswith("birth_month:"))
async def birth_month(callback: types.CallbackQuery):
    _, year, month = callback.data.split(":")
    await callback.answer()
    await callback.message.edit_text("📅 *Выберите день рождения*", parse_mode="Markdown", reply_markup=birth_calendar_keyboard(int(year), int(month)))


@router.callback_query(lambda c: c.data and c.data.startswith("birth_cal:"))
async def birth_cal(callback: types.CallbackQuery):
    _, year, month = callback.data.split(":")
    await callback.answer()
    await callback.message.edit_text("📅 *Выберите день рождения*", parse_mode="Markdown", reply_markup=birth_calendar_keyboard(int(year), int(month)))


@router.callback_query(lambda c: c.data and c.data.startswith("birth_date:"))
async def birth_date(callback: types.CallbackQuery):
    date_str = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    history = storage.personalization["user_history"].get(str(user_id), {})
    actions = history.get("actions", [])
    action = actions[-1]["action"] if actions else "profile_request"
    if action == "calendar_date_selected" and len(actions) > 1:
        action = actions[-2]["action"]
    await PersonalizationEngine.update_user_profile(user_id, "calendar_date_selected", birth_date=date_str)
    await callback.answer(f"Дата: {date_str}")
    if action == "numerology_request":
        await process_numerology(callback.message, date_str)
    elif action == "natal_chart_request":
        await natal_chart_handler(callback.message, date_str, None)
    elif action == "daily_card_request":
        await daily_card_handler(callback.message, date_str)
    elif action.startswith("horoscope_"):
        await horoscope_handler(callback.message, date_str, action)
    else:
        await process_profile(callback.message, date_str)


@router.message(lambda m: m.text == "📅 Изменить дату")
async def change_birth_date(m: Message):
    await PersonalizationEngine.update_user_profile(m.from_user.id, "change_birth_date")
    await show_birth_date_picker(m)
'''

PROFILE = r'''@router.message(lambda m: m.text == "🔮 Мой профиль")
async def profile_main(m: Message):
    user_id = m.from_user.id
    await PersonalizationEngine.update_user_profile(user_id, "profile_request")
    stored_date = PersonalizationEngine.get_user_birth_date(user_id)
    if stored_date:
        await m.answer(
            f"🔮 *{format_user_name(m.from_user)}, ваш профиль*\n\n"
            f"Я помню вашу дату рождения: *{stored_date}*.\n\n"
            "Сразу формирую ваш профиль.",
            parse_mode="Markdown",
            reply_markup=main_menu(user_id)
        )
        await process_profile(m, stored_date)
    else:
        await show_birth_date_picker(m)

@router.message(lambda m: m.text == "💞 Совместимость")'''

NUMEROLOGY = r'''@router.message(lambda m: m.text == "🔢 Нумерология")
async def numerology_main(m: Message):
    user_id = m.from_user.id
    await PersonalizationEngine.update_user_profile(user_id, "numerology_request")
    stored_date = PersonalizationEngine.get_user_birth_date(user_id)
    if stored_date:
        await process_numerology(m, stored_date)
    else:
        await show_birth_date_picker(m)

@router.message(lambda m: m.text == "🌌 Натальная карта")'''

NATAL = r'''@router.message(lambda m: m.text == "🌌 Натальная карта")
async def natal_chart_main(m: Message):
    user_id = m.from_user.id
    await PersonalizationEngine.update_user_profile(user_id, "natal_chart_request")
    stored_date = PersonalizationEngine.get_user_birth_date(user_id)
    if stored_date:
        await natal_chart_handler(m, stored_date, None)
    else:
        await show_birth_date_picker(m)

@router.message(lambda m: m.text == "✨ Карта дня")'''

DAILY = r'''@router.message(lambda m: m.text == "✨ Карта дня")
async def daily_card_main(m: Message):
    user_id = m.from_user.id
    stored_date = PersonalizationEngine.get_user_birth_date(user_id)
    if stored_date:
        await daily_card_handler(m, stored_date)
    else:
        await PersonalizationEngine.update_user_profile(user_id, "daily_card_request")
        await show_birth_date_picker(m)

@router.message(lambda m: m.text == "👑 Админ-панель")'''

HOROSCOPE = r'''@router.callback_query(lambda c: c.data.startswith("horoscope_"))
async def process_horoscope_type(callback: types.CallbackQuery):
    h_type = callback.data.split("_")[1]
    action = f"horoscope_{h_type}"
    await PersonalizationEngine.update_user_profile(callback.from_user.id, action)
    stored_date = PersonalizationEngine.get_user_birth_date(callback.from_user.id)
    await callback.answer()
    if stored_date:
        await horoscope_handler(callback.message, stored_date, action)
    else:
        await callback.message.edit_text(
            "📅 *Выберите дату рождения*\n\nВручную ничего вводить не нужно.",
            parse_mode="Markdown",
            reply_markup=birth_years_keyboard()
        )

@router.message(lambda m: m.text == "🔢 Нумерология")'''


def replace_once(source, pattern, replacement, label):
    result, count = re.subn(pattern, lambda _m: replacement, source, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"{label} not found")
    return result


def patch_main():
    source = MAIN.read_text(encoding="utf-8")
    if MARKER in source:
        py_compile.compile(str(MAIN), doraise=True)
        return

    if "import calendar\n" not in source:
        source = source.replace("import json\n", "import json\nimport calendar\n", 1)

    if "def horoscope_type_menu():" not in source:
        raise RuntimeError("horoscope_type_menu marker not found")
    source = source.replace("def horoscope_type_menu():", CALENDAR_BLOCK + "\ndef horoscope_type_menu():", 1)

    source = replace_once(
        source,
        r'@router\.message\(lambda m: m\.text == "🔮 Мой профиль"\).*?@router\.message\(lambda m: m\.text == "💞 Совместимость"\)',
        PROFILE,
        "profile handler"
    )
    source = replace_once(
        source,
        r'@router\.callback_query\(lambda c: c\.data\.startswith\("horoscope_"\)\).*?@router\.message\(lambda m: m\.text == "🔢 Нумерология"\)',
        HOROSCOPE,
        "horoscope handler"
    )
    source = replace_once(
        source,
        r'@router\.message\(lambda m: m\.text == "🔢 Нумерология"\).*?@router\.message\(lambda m: m\.text == "🌌 Натальная карта"\)',
        NUMEROLOGY,
        "numerology handler"
    )
    source = replace_once(
        source,
        r'@router\.message\(lambda m: m\.text == "🌌 Натальная карта"\).*?@router\.message\(lambda m: m\.text == "✨ Карта дня"\)',
        NATAL,
        "natal handler"
    )
    source = replace_once(
        source,
        r'@router\.message\(lambda m: m\.text == "✨ Карта дня"\).*?@router\.message\(lambda m: m\.text == "👑 Админ-панель"\)',
        DAILY,
        "daily card handler"
    )

    if '[KeyboardButton(text="📅 Изменить дату")]' not in source:
        source = source.replace(
            '[KeyboardButton(text="💞 Совместимость")],',
            '[KeyboardButton(text="💞 Совместимость")],\n        [KeyboardButton(text="📅 Изменить дату")],',
            1
        )

    returning = r'''    stored_birth_date = PersonalizationEngine.get_user_birth_date(user_id)
    if not is_new_user and stored_birth_date:
        await m.answer(
            f"✨ С возвращением, {user_name}!\n\nЯ помню вашу дату рождения — *{stored_birth_date}*.\n\nВыберите, что вас интересует:",
            parse_mode="Markdown",
            reply_markup=main_menu(user_id)
        )
        await PersonalizationEngine.update_user_profile(user_id, "start")
        return

'''
    if "stored_birth_date = PersonalizationEngine.get_user_birth_date(user_id)" not in source:
        source = source.replace("    welcome_messages = [", returning + "    welcome_messages = [", 1)

    MAIN.write_text(source, encoding="utf-8")
    py_compile.compile(str(MAIN), doraise=True)


try:
    patch_main()
except Exception as exc:
    raise RuntimeError(f"Calendar UX patch failed: {exc}") from exc

from setuptools import setup
setup(name="numerology-bot-build-hook", version="0.0.1")
