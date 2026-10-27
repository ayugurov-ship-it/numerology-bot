import unittest

from agents.forecast_qa import ensure_period_number_heading, validate_forecast


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
        text = (
            "🌟 Прогноз на месяц.\\n"
            "🎯 Число месяца 3 - что это вообще такое число месяца 3\\n"
            "✨ Итог: завершите важное дело."
        )
        normalized = ensure_period_number_heading(text, "число месяца", 3)
        self.assertNotIn("что это вообще такое", normalized)
        self.assertIn("Это общий символический ориентир календарного месяца", normalized)
        result = validate_forecast(normalized, self.plan, "month")
        self.assertTrue(result["pass"], result["issues"])


if __name__ == "__main__":
    unittest.main()
