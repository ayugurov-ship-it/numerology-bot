"""Оркестратор натальной карты: последовательность агентов и журнал выполнения."""
from __future__ import annotations

import logging
from typing import Any

from agents.natal_qa import validate_natal_chart
from agents.recovery_agent import run_with_recovery

logger = logging.getLogger(__name__)


async def calculate_verified_natal(
    *,
    date_str: str,
    birth_time: str | None,
    latitude: float,
    longitude: float,
    timezone: str,
    place: str,
    calculate_exact,
    calculate_unknown,
) -> dict[str, Any]:
    known_time = bool(birth_time)
    logger.info("[NATAL] START date=%s time_known=%s place=%s",
                date_str, known_time, place)
    logger.info("[NATAL] INPUT OK")

    async def operation():
        if known_time:
            return calculate_exact(
                date_str, birth_time, latitude, longitude, timezone, place
            )
        return calculate_unknown(
            date_str, latitude, longitude, timezone, place
        )

    chart = await run_with_recovery(
        operation,
        lambda result: validate_natal_chart(result, birth_time_known=known_time),
        stage="NATAL",
        retries=1,
    )
    logger.info("[NATAL] FINISHED")
    return chart
