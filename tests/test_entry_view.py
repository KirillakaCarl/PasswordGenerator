"""Проверки поиска и сортировки без запуска окна или изменения файлов."""

from datetime import datetime
import unittest

from password_generator.entry_view import display_created_at, select_entries
from password_generator.storage import VaultEntry


class EntryViewTests(unittest.TestCase):
    """Сравнить представление с ожидаемыми ID искусственных записей."""

    def setUp(self) -> None:
        """Подготовить разные названия, даты и только учебные секреты."""
        self.entries = [
            VaultEntry(
                "a", "Почта", "hidden-only", "2026-01-01T09:00:00+00:00"
            ),
            VaultEntry("b", "банк", "other", "2026-01-03T09:00:00+00:00"),
            VaultEntry(
                "c", "ПОЧТА личная", "another", "2026-01-02T09:00:00+00:00"
            ),
        ]

    def test_partial_case_insensitive_search(self) -> None:
        """Проверить часть названия без регистра и крайних пробелов запроса."""
        result = select_entries(self.entries, "  ПоЧт ", "title_asc")
        self.assertEqual([entry.identifier for entry in result], ["a", "c"])

    def test_empty_query_and_no_matches(self) -> None:
        """Проверить пустой запрос и запрос без совпадений."""
        self.assertEqual(len(select_entries(self.entries, "  ")), 3)
        self.assertEqual(select_entries(self.entries, "unknown"), ())
        self.assertEqual(select_entries([], ""), ())

    def test_passwords_are_not_searchable(self) -> None:
        """Совпадение только в секрете не раскрывает запись в результатах."""
        self.assertEqual(select_entries(self.entries, "hidden-only"), ())

    def test_four_sort_orders(self) -> None:
        """Проверить обе стороны алфавитного и хронологического порядка."""
        cases = {
            "title_asc": ["b", "a", "c"],
            "title_desc": ["c", "a", "b"],
            "date_asc": ["a", "c", "b"],
            "date_desc": ["b", "c", "a"],
        }
        for order, expected in cases.items():
            with self.subTest(order=order):
                result = select_entries(self.entries, sort_order=order)
                self.assertEqual(
                    [entry.identifier for entry in result], expected
                )

    def test_dates_compare_actual_time(self) -> None:
        """Дата 12:00 +0300 старше 10:00 UTC, несмотря на видимые часы."""
        entries = [
            VaultEntry("a", "same", "x", "2026-01-01T12:00:00+03:00"),
            VaultEntry("b", "same", "x", "2026-01-01T10:00:00+00:00"),
        ]
        self.assertEqual(
            [entry.identifier for entry in select_entries(entries)],
            ["b", "a"],
        )

    def test_russian_alphabet_and_stable_duplicates(self) -> None:
        """Буква ё идёт после е, одинаковые названия не путают ID записей."""
        entries = [
            VaultEntry(str(i), title, "x", "2026-01-01T00:00:00+00:00")
            for i, title in enumerate(("Ж", "ё", "е", "Е"))
        ]
        result = select_entries(entries, sort_order="title_asc")
        self.assertEqual(
            [entry.identifier for entry in result], ["2", "3", "1", "0"]
        )

    def test_original_collection_is_unchanged(self) -> None:
        """Поиск и сортировка не меняют исходный список записей."""
        before = self.entries.copy()
        select_entries(self.entries, "банк", "title_desc")
        self.assertEqual(self.entries, before)

    def test_displayed_date_preserves_instant(self) -> None:
        """Представление с часовым поясом сохраняет момент времени."""
        entry = self.entries[0]
        displayed = datetime.strptime(
            display_created_at(entry), "%d.%m.%Y %H:%M:%S %z"
        )
        self.assertEqual(displayed, datetime.fromisoformat(entry.created_at))

    def test_invalid_sort_order(self) -> None:
        """Неизвестный порядок не должен молча менять поведение."""
        with self.assertRaises(ValueError):
            select_entries(self.entries, sort_order="unknown")


if __name__ == "__main__":
    unittest.main()
