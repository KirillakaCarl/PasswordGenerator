"""Проверки заранее заданных примеров, границ и контракта оценки."""

import unittest

from password_generator.assessment import assess_baseline, assess_password

# Наборы сначала записаны в ASSESSMENT_RULES.md, затем перенесены сюда.
MAIN_CASES = (
    ("password", "Слабый"),
    ("Password123!", "Слабый"),
    ("12345678", "Слабый"),
    ("aaaaaaaaaaaaaaaa", "Слабый"),
    ("Abc123!Abc123!", "Слабый"),
    ("V7!mQ2#zR9@k", "Сильный"),
    ("sova most reka veter", "Сильный"),
)
HOLDOUT_CASES = (
    ("P@ssw0rd2026!", "Слабый"),
    ("Z9$Z9$Z9$Z9$", "Слабый"),
    ("987654321098", "Слабый"),
    ("QwErTy2026!", "Слабый"),
    ("b8!Rz4@L", "Средний"),
    ("N8$wT6&rY2%p", "Сильный"),
)


class AssessmentTests(unittest.TestCase):
    """Оценивать искусственные строки без интерфейса и внешних сервисов."""

    def test_main_cases(self) -> None:
        """Сверить категории с основными примерами спецификации."""
        for password, category in MAIN_CASES:
            with self.subTest(category=category):
                self.assertEqual(assess_password(password).category, category)

    def test_holdout_cases(self) -> None:
        """Проверить отложенные примеры без подгонки порогов."""
        for password, category in HOLDOUT_CASES:
            with self.subTest(category=category):
                self.assertEqual(assess_password(password).category, category)

    def test_improvement_over_baseline(self) -> None:
        """Улучшение должно устранить ложную высокую оценку шаблонов."""
        self.assertEqual(assess_baseline("Password123!").category, "Сильный")
        self.assertEqual(assess_baseline("Abc123!Abc123!").category, "Сильный")
        self.assertEqual(assess_password("Password123!").category, "Слабый")
        self.assertEqual(assess_password("Abc123!Abc123!").category, "Слабый")

    def test_empty_input(self) -> None:
        """Пустой ввод не получает категорию сложности."""
        for assess in (assess_baseline, assess_password):
            result = assess("")
            self.assertEqual((result.score, result.category), (0, "Не задан"))

    def test_invalid_input(self) -> None:
        """Проверить неправильные типы и превышение ограничения длины."""
        for value in (None, 123, b"example", "x" * 1025):
            for assess in (assess_baseline, assess_password):
                with (
                    self.subTest(function=assess.__name__),
                    self.assertRaises(ValueError),
                ):
                    assess(value)

    def test_length_limits(self) -> None:
        """Проверить ограничения на 7/8/11/12 и допустимость 1024 символов."""
        sample = "V7!mQ2#zR9@k"
        for size, maximum in ((7, 39), (8, 74), (11, 74), (12, 100)):
            with self.subTest(size=size):
                result = assess_password(sample[:size])
                self.assertLessEqual(result.score, maximum)
        self.assertEqual(assess_password(sample).category, "Сильный")
        self.assertLessEqual(assess_password("x" * 1024).score, 39)

    def test_spaces_unicode_and_determinism(self) -> None:
        """Проверить пробелы, Unicode и повторяемость результата."""
        for password in (" ", "  ", "Ёж7!Мир9#Ток2", "山川風月", "  example  "):
            result = assess_password(password)
            self.assertEqual(result, assess_password(password))
            self.assertIn(f"Длина: {len(password)}.", result.explanations[0])
            self.assertTrue(0 <= result.score <= 100)

    def test_reasons_do_not_echo_password(self) -> None:
        """Результат содержит пояснения без копии исходного пароля."""
        password = "V7!mQ2#zR9@k"
        self.assertNotIn(password, repr(assess_password(password)))

    def test_triple_and_reverse_sequence(self) -> None:
        """Проверить тройной повтор и обратную последовательность."""
        self.assertLessEqual(assess_password("M8!xxxT4&rY2%p").score, 74)
        result = assess_password("M8!zyxwT4&rY2%p")
        self.assertTrue(any(
            "последовательность" in text for text in result.explanations
        ))

    def test_category_boundaries(self) -> None:
        """Проверить обе стороны порогов 40 и 75 на базовой формуле."""
        cases = (
            ("a" * 7, 31, "Слабый"),
            ("a" * 10, 40, "Средний"),
            ("aA" * 9, 74, "Средний"),
            ("aA1" * 5, 75, "Сильный"),
        )
        for password, score, category in cases:
            result = assess_baseline(password)
            self.assertEqual(
                (result.score, result.category), (score, category)
            )


if __name__ == "__main__":
    unittest.main()
