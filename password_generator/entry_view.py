"""Поиск и порядок отображения записей без изменения хранилища и паролей."""

from collections.abc import Iterable
from datetime import datetime

from password_generator.storage import VaultEntry

SORT_ORDERS = {
    "Название: А → Я": "title_asc",
    "Название: Я → А": "title_desc",
    "Дата: сначала новые": "date_desc",
    "Дата: сначала старые": "date_asc",
}
DEFAULT_SORT = "Дата: сначала новые"


def _title_key(entry: VaultEntry) -> tuple[tuple[int, int], ...]:
    """Получить ключ названия без регистра; русскую ё поместить после е.

    Остальные символы упорядочиваются по Unicode. Это не зависимая от
    настроек Windows сортировка: результат одинаков на разных компьютерах.
    """
    return tuple(
        (ord("е"), 1) if char == "ё" else (ord(char), 0)
        for char in entry.title.casefold()
    )


def _created_key(entry: VaultEntry) -> datetime:
    """Получить момент создания с часовым поясом для сравнения дат."""
    return datetime.fromisoformat(entry.created_at)


def select_entries(
    entries: Iterable[VaultEntry], query: str = "",
    sort_order: str = "date_desc",
) -> tuple[VaultEntry, ...]:
    """Вернуть отфильтрованные и отсортированные записи для таблицы.

    query — часть названия, без учёта регистра и крайних пробелов запроса.
    Пустой запрос возвращает все записи. Секретные поля не участвуют в поиске.
    sort_order — одно из четырёх значений SORT_ORDERS, иначе ValueError.
    Исходная коллекция и сами записи не изменяются, файл не читается заново.
    """
    if sort_order not in SORT_ORDERS.values():
        raise ValueError("Неизвестный порядок сортировки записей.")
    needle = query.strip().casefold()
    matches = [entry for entry in entries if needle in entry.title.casefold()]
    if sort_order.startswith("title"):
        key = _title_key
    else:
        # Сравниваем моменты времени, а не строки: разные часовые пояса
        # могут записывать один момент по-разному. Даты проверены при открытии.
        key = _created_key
    # sorted создаёт новый список. Стабильная сортировка сохраняет исходный
    # порядок при одинаковых ключах, не путая записи с одинаковыми названиями.
    return tuple(sorted(matches, key=key, reverse=sort_order.endswith("desc")))


def display_created_at(entry: VaultEntry) -> str:
    """Показать дату сохранения записи в локальном часовом поясе компьютера.

    Часовой пояс берётся у операционной системы, исходная дата UTC в файле
    остаётся прежней. Секунды и смещение помогают различать близкие записи.
    """
    date = datetime.fromisoformat(entry.created_at).astimezone()
    return date.strftime("%d.%m.%Y %H:%M:%S %z")
