from pathlib import Path
import py_compile

from calendar_patch import patch as calendar_patch


MAIN = Path("main.py")


def patch_groq():
    source = MAIN.read_text(encoding="utf-8")

    old_budget = '        "max_completion_tokens": 1500,'
    new_budget = '        "max_completion_tokens": 4096,'
    if old_budget in source:
        source = source.replace(old_budget, new_budget, 1)

    reasoning_block = (
        '        "reasoning_effort": "low",\n'
        '        "include_reasoning": False'
    )
    if reasoning_block not in source:
        needle = '        "max_completion_tokens": 4096,\n'
        replacement = (
            '        "max_completion_tokens": 4096,\n'
            '        "reasoning_effort": "low",\n'
            '            "include_reasoning": False\n'
        )
        if needle not in source:
            raise RuntimeError("Groq request block not found")
        # Preserve the established patch exactly; this branch is only reached
        # on an unpatched source.
        replacement = (
            '        "max_completion_tokens": 4096,\n'
            '        "reasoning_effort": "low",\n'
            '        "include_reasoning": False\n'
        )
        source = source.replace(needle, replacement, 1)

    old_response = '''            result = await resp.json()
            return result["choices"][0]["message"]["content"].strip()
'''
    new_response = '''            result = await resp.json()
            choice = (result.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            content = message.get("content") or ""

            if not content.strip():
                logger.error(
                    "GROQ API EMPTY CONTENT: finish_reason=%s usage=%s message_keys=%s",
                    choice.get("finish_reason"),
                    result.get("usage"),
                    list(message.keys()),
                )
                raise RuntimeError(
                    "Groq returned empty content "
                    f"(finish_reason={choice.get('finish_reason')})"
                )

            logger.info(
                "GROQ OK: model=%s finish_reason=%s content_chars=%s",
                result.get("model", MODEL_NAME),
                choice.get("finish_reason"),
                len(content.strip()),
            )
            return content.strip()
'''
    if old_response in source:
        source = source.replace(old_response, new_response, 1)

    MAIN.write_text(source, encoding="utf-8")
    py_compile.compile(str(MAIN), doraise=True)


def patch_natal_place_message():
    source = MAIN.read_text(encoding="utf-8")
    old = '''        f"🧭 Координаты: {geo['latitude']:.4f}, {geo['longitude']:.4f}\\n\\n" +
        ("После оплаты будут рассчитаны планеты, аспекты и персональная расшифровка. "
'''
    # Already fixed: do not alter again.
    if old not in source:
        print("Natal place confirmation already fixed or not found")
        return
    raise RuntimeError("Unexpected unpatched natal place block")


def patch_natal_calculation_diagnostics():
    source = MAIN.read_text(encoding="utf-8")

    old = '''    try:
        if data.get("birth_time"):
            chart = calculate_natal_chart(
                data["date"],
                data["birth_time"],
                float(data["latitude"]),
                float(data["longitude"]),
                data["timezone"],
                data.get("place"),
            )
        else:
            chart = calculate_natal_chart_without_time(
                data["date"],
                float(data["latitude"]),
                float(data["longitude"]),
                data["timezone"],
                data.get("place"),
            )
    except Exception as exc:
        logger.exception("Natal calculation failed: %s", exc)
        await message.answer(
            "Не удалось выполнить астрономический расчёт. Данные сохранены, попробуйте ещё раз позже.",
            reply_markup=main_menu(user_id),
        )
        return
'''
    new = '''    try:
        if data.get("birth_time"):
            logger.info(
                "Natal calculation START: date=%s time=%s lat=%s lon=%s tz=%s",
                data.get("date"), data.get("birth_time"),
                data.get("latitude"), data.get("longitude"), data.get("timezone"),
            )
            chart = calculate_natal_chart(
                data["date"],
                data["birth_time"],
                float(data["latitude"]),
                float(data["longitude"]),
                data["timezone"],
                data.get("place"),
            )
        else:
            logger.info(
                "Natal calculation START (no time): date=%s lat=%s lon=%s tz=%s",
                data.get("date"), data.get("latitude"),
                data.get("longitude"), data.get("timezone"),
            )
            chart = calculate_natal_chart_without_time(
                data["date"],
                float(data["latitude"]),
                float(data["longitude"]),
                data["timezone"],
                data.get("place"),
            )

        logger.info(
            "Natal calculation OK: planets=%s aspects=%s houses=%s",
            len(chart.get("planets", {})),
            len(chart.get("aspects", [])),
            len(chart.get("houses", [])),
        )
    except Exception as exc:
        logger.exception(
            "Natal calculation FAILED: type=%s message=%s data=%r",
            type(exc).__name__, exc, data,
        )
        await message.answer(
            "Не удалось выполнить астрономический расчёт. Данные сохранены, попробуйте ещё раз позже.",
            reply_markup=main_menu(user_id),
        )
        return
'''
    if old not in source:
        raise RuntimeError("Natal calculation block not found")
    source = source.replace(old, new, 1)
    MAIN.write_text(source, encoding="utf-8")
    py_compile.compile(str(MAIN), doraise=True)
    print("Natal calculation diagnostics patched")


if __name__ == "__main__":
    calendar_patch()
    patch_groq()
    patch_natal_place_message()
    patch_natal_calculation_diagnostics()
