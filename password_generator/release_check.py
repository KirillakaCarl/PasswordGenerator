"""Проверка готового exe: встроенный Python, Tkinter и учебное хранилище.

Режим вызывается только явным аргументом --self-check. Он не открывает
пользовательские файлы, не обращается к сети и не включает секреты в отчёт.
Отдельный модуль не усложняет обычный пользовательский интерфейс.
"""

import json
from pathlib import Path
import sys
import tempfile

import cryptography

from password_generator import __version__
from password_generator.assessment import assess_password
from password_generator.entry_view import select_entries
from password_generator.gui import PasswordGeneratorApp
from password_generator.storage import VaultSession


def run_release_check(report_path: Path) -> int:
    """Проверить основные компоненты, записать JSON и вернуть код 0 или 1.

    report_path — выбранный разработчиком путь отчёта. Все пароли искусственные,
    хранилище создаётся в отдельном временном каталоге и затем удаляется.
    Отчёт содержит только имя класса ошибки, без текста исключения.
    """
    report = {
        "version": __version__, "frozen": bool(getattr(sys, "frozen", False)),
        "checks": [], "ok": False,
    }
    app = None
    try:
        if report["frozen"]:
            bundle = Path(sys._MEIPASS).resolve()
            library = Path(cryptography.__file__).resolve()
            if not library.is_relative_to(bundle):
                raise RuntimeError("Dependency outside bundle")
            report["checks"].append("cryptography_loaded_from_bundle")
        app = PasswordGeneratorApp()
        app.withdraw()
        app.update()
        app.generate_button.invoke()
        if len(app.password.get()) != 16:
            raise RuntimeError("Generation failed")
        report["checks"].append("tkinter_and_generation")
        if assess_password("Password123!").category != "Слабый":
            raise RuntimeError("Assessment failed")
        report["checks"].append("assessment")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artificial-check.vault"
            master = "educational-master-2026"
            session = VaultSession.create(path, master)
            first = session.add("Учебная почта", app.password.get())
            second = session.add("Учебный банк", "artificial-example-123!")
            session.lock()
            reopened = VaultSession.open(path, master)
            if reopened.entries != (first, second):
                raise RuntimeError("Storage round trip failed")
            report["checks"].append("argon2_fernet_save_reopen")
            if select_entries(reopened.entries, "ПОЧТА") != (first,):
                raise RuntimeError("Search failed")
            if select_entries(
                reopened.entries, sort_order="title_desc"
            ) != (second, first):
                raise RuntimeError("Sorting failed")
            report["checks"].append("search_and_sorting")
            reopened.delete(first.identifier)
            if reopened.entries != (second,):
                raise RuntimeError("Deletion failed")
            reopened.lock()
            report["checks"].append("delete_and_close")
        report["ok"] = True
    except Exception as error:
        report["error_type"] = type(error).__name__
    finally:
        if app is not None:
            app.destroy()
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0 if report["ok"] else 1
