"""Точка входа в учебное приложение PasswordGenerator.

Запускайте этот файл из корня проекта командой `.venv/Scripts/python main.py`.
Создание интерфейса вынесено в отдельный модуль, чтобы точка входа оставалась
короткой, а будущая логика генерации не зависела от способа запуска программы.
"""

import argparse
from pathlib import Path

from password_generator.gui import PasswordGeneratorApp


def main() -> None:
    """Создать главное окно и запустить обработку действий пользователя.

    Параметров нет. Функция завершится без возвращаемого значения, когда
    пользователь закроет окно. Ошибки запуска Tkinter не скрываются: их текст
    в терминале помогает найти проблему с установкой Python или графикой.
    """
    # Служебный режим проверяет именно упакованное приложение на искусственных
    # данных. При обычном двойном щелчке аргументов нет и открывается окно.
    parser = argparse.ArgumentParser(description="PasswordGenerator")
    parser.add_argument("--self-check", type=Path, metavar="REPORT_JSON")
    args = parser.parse_args()
    if args.self_check is not None:
        from password_generator.release_check import run_release_check

        raise SystemExit(run_release_check(args.self_check))
    app = PasswordGeneratorApp()

    # mainloop передаёт управление Tkinter: он обрабатывает нажатия,
    # перерисовывает окно и ожидает следующих действий до закрытия приложения.
    app.mainloop()


# При импорте main из другого модуля окно не открывается автоматически.
# Условие выполняется только при непосредственном запуске этого файла.
if __name__ == "__main__":
    main()
