import unittest

from agents.forecast_qa import (
    ensure_period_number_heading,
    validate_forecast,
    remove_unverified_position_sentences,
    remove_unverified_lunar_position_sentences,
)


class ForecastNumberHeadingTests(unittest.TestCase):
    def setUp(self):
        self.plan = {
            "period": "month",
            "date": "01.11.2026 – 30.11.2026",
            "life_number": 11,
            "period_number": 3,
            "period_number_label": "число месяца",
            "events": [],
            "moon_positions": {},
        }

    def test_valid_month_number_passes(self):
        text = "🎯 Число месяца 3\nТри символизирует творчество.\n\n✨ Итог: готовьтесь к новому."
        normalized = ensure_period_number_heading(text, "число месяца", 3)
        result = validate_forecast(normalized, self.plan, "month")
        self.assertTrue(result["pass"], result["issues"])
        self.assertIn("Число месяца 3", normalized)

    def test_missing_month_number_heading_is_added(self):
        text = "🎯 Тройка символизирует творчество.\n\n✨ Итог: готовьтесь к новому."
        normalized = ensure_period_number_heading(text, "число месяца", 3)
        self.assertIn("Число месяца 3", normalized)
        result = validate_forecast(normalized, self.plan, "month")
        self.assertTrue(result["pass"], result["issues"])

    def test_explicit_wrong_number_is_not_silently_rewritten(self):
        text = "🎯 Число месяца 4\nЧетвёрка символизирует структуру.\n\n✨ Итог."
        normalized = ensure_period_number_heading(text, "число месяца", 3)
        self.assertIn("Число месяца 4", normalized)
        result = validate_forecast(normalized, self.plan, "month")
        self.assertFalse(result["pass"])
        self.assertTrue(any("Неверное число месяца" in issue for issue in result["issues"]))

    def test_error_response_is_not_decorated_with_number_heading(self):
        text = "🔮 Произошла ошибка при обработке запроса. Попробуйте позже."
        normalized = ensure_period_number_heading(text, "число месяца", 3)
        self.assertEqual(normalized, text)

    def test_weird_model_explanation_is_replaced_with_clear_definition(self):
        text = """🌟 Прогноз на месяц.
🎯 Число месяца 3 - что это вообще такое число месяца 3
✨ Итог: завершите важное дело."""
        normalized = ensure_period_number_heading(text, "число месяца", 3)
        self.assertNotIn("что это вообще такое", normalized)
        self.assertIn("Это общий символический ориентир календарного месяца", normalized)
        result = validate_forecast(normalized, self.plan, "month")
        self.assertTrue(result["pass"], result["issues"])



    def test_month_moon_sequence_checks_transitions_after_start_date(self):
        plan = {
            "period": "month",
            "date": "01.11.2026 – 30.11.2026",
            "events": [
                {"date": "10.11.2026", "type": "переход", "text": "Луна: Стрелец → Козерог в 13:00"},
                {"date": "11.11.2026", "type": "переход", "text": "Луна: Козерог → Водолей в 14:00"},
            ],
            "moon_positions": {"10.11.2026": "Стрелец", "11.11.2026": "Козерог"},
        }
        text = "🌙 С 10 ноября Луна перемещается из Стрельца в Козерога, затем в Водолея."
        result = validate_forecast(text, plan, "month")
        transition_issues = [issue for issue in result["issues"] if "Переход Луны" in issue or "Неподтверждённый переход Луны" in issue]
        self.assertEqual(transition_issues, [])

    def test_wrong_moon_sequence_still_fails(self):
        plan = {
            "period": "month",
            "date": "01.11.2026 – 30.11.2026",
            "events": [
                {"date": "10.11.2026", "type": "переход", "text": "Луна: Стрелец → Козерог в 13:00"},
            ],
            "moon_positions": {"10.11.2026": "Стрелец"},
        }
        text = "🌙 С 10 ноября Луна перемещается из Стрельца в Водолея."
        result = validate_forecast(text, plan, "month")
        self.assertFalse(result["pass"])
        self.assertTrue(any("Неподтверждённый переход Луны" in issue for issue in result["issues"]))



    def test_false_planet_position_sentence_is_removed_and_revalidated(self):
        plan = {
            "period": "today",
            "date": "28.10.2026",
            "positions": {"Солнце": {"sign": "Скорпион"}},
            "events": [],
            "moon_positions": {},
        }
        text = (
            "🌅 Главная тема дня — действовать последовательно. "
            "Солнце находится в Льве и усиливает желание спорить. "
            "Полезно сначала проверить факты, а затем принимать решение."
        )
        cleaned, removed = remove_unverified_position_sentences(text, plan)
        self.assertEqual(len(removed), 1)
        self.assertNotIn("Солнце находится в Льве", cleaned)
        self.assertIn("Полезно сначала проверить факты", cleaned)
        result = validate_forecast(cleaned, plan, "today")
        self.assertTrue(result["pass"], result["issues"])

    def test_late_moon_sign_sentence_is_removed_but_other_text_is_preserved(self):
        plan = {
            "period": "month",
            "date": "01.11.2026 – 30.11.2026",
            "events": [
                {"date": "05.11.2026", "type": "переход", "text": "Луна: Дева → Весы в 17:38"},
            ],
            "moon_positions": {"05.11.2026": "Дева"},
        }
        text = (
            "🌟 В начале месяца важно расставить приоритеты. "
            "05 ноября Луна находится в Весах, поэтому день располагает к переговорам. "
            "В работе полезно заранее согласовать сроки."
        )
        cleaned, removed = remove_unverified_lunar_position_sentences(text, plan, "month")
        self.assertEqual(len(removed), 1)
        self.assertNotIn("Луна находится в Весах", cleaned)
        self.assertIn("В работе полезно заранее согласовать сроки", cleaned)
        result = validate_forecast(cleaned, plan, "month")
        self.assertTrue(result["pass"], result["issues"])

    def test_explicit_lunar_transition_with_time_is_not_removed(self):
        plan = {
            "period": "month",
            "date": "01.11.2026 – 30.11.2026",
            "events": [
                {"date": "05.11.2026", "type": "переход", "text": "Луна: Дева → Весы в 17:38"},
            ],
            "moon_positions": {"05.11.2026": "Дева"},
        }
        text = "05 ноября в 17:38 Луна переходит из Девы в Весы."
        cleaned, removed = remove_unverified_lunar_position_sentences(text, plan, "month")
        self.assertEqual(removed, [])
        self.assertEqual(cleaned, text)

    def test_correct_planet_position_is_preserved(self):
        plan = {
            "period": "today",
            "date": "28.10.2026",
            "positions": {"Солнце": {"sign": "Скорпион"}},
            "events": [],
            "moon_positions": {},
        }
        text = "Солнце находится в Скорпионе. Сосредоточьтесь на главном."
        cleaned, removed = remove_unverified_position_sentences(text, plan)
        self.assertEqual(removed, [])
        self.assertEqual(cleaned, text)


if __name__ == "__main__":
    unittest.main()
