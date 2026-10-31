"""Проверки длины, алфавита, обязательных групп и ошибок настроек."""

from dataclasses import replace
import itertools
import string
import unittest
from unittest.mock import patch

from password_generator.generator import GenerationOptions, generate_password


class GeneratorTests(unittest.TestCase):
    """Проверить контракт генератора на обычных и граничных значениях."""

    def test_all_group_combinations_and_boundary_lengths(self) -> None:
        """Проверить 15 сочетаний на длинах 4, 16, 128 по восемь раз.

        Проверяем свойства результата, без недостоверного требования
        уникальности и без попытки доказать случайность статистикой.
        """
        alphabets = (string.ascii_lowercase, string.ascii_uppercase,
                     string.digits, string.punctuation)
        for flags in itertools.product((False, True), repeat=4):
            if not any(flags):
                continue
            selected = [group for enabled, group in zip(flags, alphabets) if enabled]
            allowed = set("".join(selected))
            for length in (4, 16, 128):
                with self.subTest(flags=flags, length=length):
                    for _ in range(8):
                        password = generate_password(GenerationOptions(length, *flags))
                        self.assertEqual(len(password), length)
                        self.assertTrue(set(password) <= allowed)
                        for group in selected:
                            self.assertTrue(any(symbol in group for symbol in password))

    def test_invalid_lengths(self) -> None:
        """Отклонить выход за границы, неправильный тип и bool вместо длины."""
        for length in (-1, 0, 3, 129, 10**20, 16.0, "16", True, None):
            with self.subTest(length=length), self.assertRaises(ValueError):
                generate_password(GenerationOptions(length=length))

    def test_no_selected_groups(self) -> None:
        """Пустой набор групп должен давать понятную ошибку."""
        with self.assertRaisesRegex(ValueError, "хотя бы одну"):
            generate_password(GenerationOptions(16, False, False, False, False))

    def test_group_flags_require_booleans(self) -> None:
        """Числа и строки не подменяют логические переключатели."""
        for field in ("lowercase", "uppercase", "digits", "special"):
            for value in (1, 0, "True", None):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    generate_password(replace(GenerationOptions(), **{field: value}))

    def test_invalid_options_object(self) -> None:
        """Вместо настроек нельзя передать произвольный объект."""
        with self.assertRaises(ValueError):
            generate_password(None)

    def test_candidate_missing_groups_is_retried(self) -> None:
        """Контролируемый источник даёт сначала плохой, затем допустимый кандидат.

        Так обязательность групп проверяется независимо от удачи при генерации.
        """
        with patch("password_generator.generator.secrets.choice",
                   side_effect=list("aaaaaA1!")):
            self.assertEqual(generate_password(GenerationOptions(length=4)), "aA1!")


if __name__ == "__main__":
    unittest.main()
