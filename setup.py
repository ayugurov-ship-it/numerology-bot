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
            '        "include_reasoning": False\n'
        )
        if needle not in source:
            raise RuntimeError("Groq request block not found")
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
    print("Groq patch applied: max_completion_tokens=4096, reasoning_effort=low")


def patch_natal_place_message():
    source = MAIN.read_text(encoding="utf-8")

    old = '''        f"🧭 Координаты: {geo['latitude']:.4f}, {geo['longitude']:.4f}\\n\\n"
        ("После оплаты будут рассчитаны планеты, аспекты и персональная расшифровка. "
'''

    new = '''        f"🧭 Координаты: {geo['latitude']:.4f}, {geo['longitude']:.4f}\\n\\n" +
        ("После оплаты будут рассчитаны планеты, аспекты и персональная расшифровка. "
'''

    if old not in source:
        raise RuntimeError("Natal place confirmation block not found")

    source = source.replace(old, new, 1)
    MAIN.write_text(source, encoding="utf-8")
    py_compile.compile(str(MAIN), doraise=True)
    print("Natal place confirmation patch applied")


if __name__ == "__main__":
    calendar_patch()
    patch_groq()
    patch_natal_place_message()
