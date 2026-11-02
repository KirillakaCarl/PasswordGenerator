"""Отдельный exe для расследования сбоя сохранения версии 1.0.0.

Обычный main.py не включает журналирование. Эта сборка сохраняет технический
журнал в профиле пользователя и использует прежние алгоритмы хранилища.
"""

from datetime import datetime, timezone
import os
from pathlib import Path
import platform
import sys
import tkinter as tk
from tkinter import messagebox

if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from password_generator.diagnostics import SaveDiagnostics
from password_generator.gui import PasswordGeneratorApp


def main() -> None:
    """Запустить диагностику; сообщить о невозможности создать журнал."""
    app = None
    diagnostic = None
    try:
        directory = Path(os.environ.get('LOCALAPPDATA', Path.home()))
        directory /= 'PasswordGenerator/diagnostics'
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
        path = directory / f'save-{stamp}-{os.getpid()}.log'
        diagnostic = SaveDiagnostics(path)
        diagnostic.install()
        diagnostic.log.info('diagnostic_build=1 python=%s windows=%s',
                            platform.python_version(), platform.win32_ver()[0])
        if len(sys.argv) == 3 and sys.argv[1] == '--self-check':
            from password_generator.release_check import run_release_check
            raise SystemExit(run_release_check(Path(sys.argv[2])))
        app = PasswordGeneratorApp()
        app.title('PasswordGenerator 1.0.0 — диагностика сохранения')

        def callback_error(kind, error, trace):
            """Сохранить сведения об ошибке Tk без её потенциально секретного текста."""
            diagnostic.error('tk_callback', error)
            app.status.set('Ошибка интерфейса. Сведения записаны в журнал диагностики.')

        app.report_callback_exception = callback_error
        diagnostic.log.info('tk=%s', app.tk.call('info', 'patchlevel'))
        messagebox.showinfo(
            'Диагностика сохранения',
            'Проверьте сохранение на новом учебном хранилище.\n'
            'При зависании подождите 30 секунд перед закрытием программы.\n\n'
            'Журнал без паролей и названий записей:\n' + str(path), parent=app
        )
        diagnostic.log.info('mainloop begin')
        app.mainloop()
        diagnostic.log.info('mainloop end')
    except Exception as error:
        if diagnostic is not None:
            diagnostic.error('main', error)
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror('Диагностика',
                             'Не удалось запустить диагностику. Тип ошибки: '
                             + type(error).__name__, parent=root)
        root.destroy()
    finally:
        if diagnostic is not None:
            diagnostic.close()


if __name__ == '__main__':
    main()
