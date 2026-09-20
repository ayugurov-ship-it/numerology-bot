"""Recovery Agent: повторяет детерминированные этапы только безопасными способами."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


async def run_with_recovery(
    operation: Callable[[], Awaitable[dict[str, Any]]],
    validator: Callable[[dict[str, Any]], list[str]],
    *,
    stage: str,
    retries: int = 1,
) -> dict[str, Any]:
    """Выполняет расчёт, проверяет его и при сбое повторяет.

    Recovery не исправляет данные сам и ничего не «угадывает»: повторяется
    тот же детерминированный расчёт, после чего QA снова проверяет результат.
    """
    last_errors: list[str] = []
    for attempt in range(1, retries + 2):
        try:
            logger.info("[%s] CALCULATION attempt=%d", stage, attempt)
            result = await operation()
            errors = validator(result)
            if not errors:
                logger.info("[%s] CALCULATION_QA OK attempt=%d", stage, attempt)
                return result
            last_errors = errors
            logger.error("[%s] CALCULATION_QA FAILED attempt=%d: %s",
                         stage, attempt, " | ".join(errors))
        except Exception as exc:
            last_errors = [f"{type(exc).__name__}: {exc}"]
            logger.exception("[%s] CALCULATION FAILED attempt=%d", stage, attempt)
        if attempt <= retries:
            logger.warning("[%s] RECOVERY retry=%d", stage, attempt)
            await asyncio.sleep(0.2)

    raise RuntimeError(
        f"{stage}: расчёт не прошёл проверку после повторной попытки: "
        + " | ".join(last_errors)
    )
