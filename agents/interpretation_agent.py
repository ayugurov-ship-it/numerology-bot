"""Interpretation Agent + Report QA: генерация, проверка и контролируемая правка."""
from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable

from agents.report_qa import validate_report_text

logger = logging.getLogger(__name__)


def _evidence_snapshot(chart: dict[str, Any]) -> str:
    """Compact source-of-truth used by Judge/Repair to reduce token pressure."""
    lines = ["ПЛАНЕТЫ:"]
    for name, value in chart.get("planets", {}).items():
        if isinstance(value, dict):
            parts = [str(value.get("formatted", ""))]
            if value.get("house") is not None:
                parts.append(f"дом={value['house']}")
            if value.get("retrograde"):
                parts.append("ретроградное")
            if value.get("time_uncertainty"):
                parts.append(f"неопределённость={','.join(value.get('possible_signs', []))}")
            lines.append(f"- {name}: " + "; ".join(p for p in parts if p))
    lines.append("АСПЕКТЫ:")
    for a in chart.get("aspects", []):
        lines.append(f"- {a['first']} — {a['aspect']} — {a['second']} (орб {a.get('orb', '')}°)")
    if chart.get("angles"):
        lines.append("УГЛЫ:")
        for key in ("ascendant", "mc"):
            if chart["angles"].get(key):
                lines.append(f"- {key}: {chart['angles'][key].get('formatted', '')}")
    houses = chart.get("houses") or []
    lines.append("ДОМА: " + ("; ".join(h.get("formatted", "") for h in houses) if houses else "не рассчитаны"))
    return "\n".join(lines)



async def generate_verified_report(
    *,
    prompt: str,
    chart: dict[str, Any],
    birth_time_known: bool,
    ask_groq: Callable[[str, str], Awaitable[str]],
    max_repairs: int = 2,
) -> str:
    """Генерирует отчёт и не пропускает его без QA.

    Сначала идут детерминированные проверки. Затем независимая по роли
    проверка смысла через отдельный judge-вызов. При ошибке модель получает
    только конкретные замечания и компактный источник истины, после чего переписывает отчёт.
    """
    report = await ask_groq(prompt, "natal")

    for attempt in range(1, max_repairs + 2):
        hard_errors = validate_report_text(report, chart, birth_time_known)
        if hard_errors:
            logger.warning("[NATAL_REPORT] DETERMINISTIC QA FAILED attempt=%d: %s",
                           attempt, " | ".join(hard_errors))
        else:
            judge_prompt = f"""
Ты — независимый контролёр качества натального отчёта.
Твоя задача НЕ переписывать текст, а найти фактические и логические нарушения.

ИСТОЧНИК ИСТИНЫ — только JSON рассчитанной карты ниже.
Нельзя считать правдой то, чего нет в JSON.

КАРТА:
{_evidence_snapshot(chart)}

ОТЧЁТ:
{report}

Проверь:
1. Не придуманы ли аспекты, положения планет, градусы, дома или ASC/MC.
2. Если время неизвестно, не трактуется ли Луна как абсолютно точная, если есть time_uncertainty.
3. Не выдаются ли профессии/события как предопределённые картой.
4. Нет ли противоречий между разделами.
5. Нет ли повторов, пустых общих фраз и советов, не связанных с картой.
6. Не утверждается ли будущее как неизбежное.

Ответь строго двумя блоками:
VERDICT: PASS или FAIL
ISSUES: список конкретных проблем; если проблем нет — NONE.
"""
            judge = await ask_groq(judge_prompt, "natal_qa")
            if "VERDICT: PASS" in judge.upper() and "VERDICT: FAIL" not in judge.upper():
                logger.info("[NATAL_REPORT] QA PASS attempt=%d", attempt)
                return report
            hard_errors = ["Независимый контролёр нашёл проблемы: " + judge[:2500]]
            logger.warning("[NATAL_REPORT] SEMANTIC QA FAILED attempt=%d", attempt)

        if attempt > max_repairs:
            raise RuntimeError(
                "Натальный отчёт не прошёл контроль качества после повторных исправлений: "
                + " | ".join(hard_errors)
            )

        repair_prompt = f"""
ПЕРЕПИШИ ВЕСЬ НАТАЛЬНЫЙ ОТЧЁТ, НЕ ДОБАВЛЯЯ НИКАКИХ НОВЫХ ФАКТОВ.

Исходный отчёт:
{report}

Ошибки контроля качества:
{chr(10).join('- ' + e for e in hard_errors)}

ИСТОЧНИК ИСТИНЫ — ТОЛЬКО РАССЧИТАННАЯ КАРТА:
{_evidence_snapshot(chart)}

Критические правила:
- Аспекты можно утверждать ТОЛЬКО если exact pair + aspect есть в карте.
- Нельзя создавать аспект по смыслу или «логике» знаков.
- При неизвестном времени нельзя использовать ASC, MC, дома и планеты по домам.
- При неопределённости Луны сохраняй неопределённость.
- Не назначай профессии по карте и не предсказывай неизбежные события.
- Не добавляй новые факты, которых нет в карте.
- Сохрани структуру и персональность, но убери ошибки.
"""
        report = await ask_groq(repair_prompt, "natal")

    raise RuntimeError("Report QA завершился без проверенного результата.")
