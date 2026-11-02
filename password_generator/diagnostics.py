"""Диагностика сохранения; включается только специальной точкой входа.

Журнал содержит фиксированные имена этапов, типы ошибок и позиции в коде.
Аргументы, результаты функций, тексты исключений и локальные переменные
не записываются: в них могут находиться пароли и названия записей.
"""

import faulthandler
from functools import wraps
import logging
from pathlib import Path
import traceback


class SaveDiagnostics:
    """Отслеживать этапы и получать снимок потоков при долгом сохранении."""

    def __init__(self, path: Path) -> None:
        """Открыть новый журнал; OSError передать вызывающему коду."""
        self.stream = path.open('x', encoding='utf-8', buffering=1)
        self.log = logging.Logger('save-diagnostics')
        handler = logging.StreamHandler(self.stream)
        handler.setFormatter(logging.Formatter(
            '%(asctime)s %(threadName)s %(message)s'
        ))
        self.log.addHandler(handler)
        self._patches = []
        # Файл остаётся открытым до отключения обоих обработчиков.
        faulthandler.enable(file=self.stream, all_threads=True)

    def error(self, event: str, error: BaseException) -> None:
        """Записать тип и позиции ошибки, исключая её сообщение и значения."""
        self.log.info('%s error_type=%s', event, type(error).__name__)
        for frame, line in traceback.walk_tb(error.__traceback__):
            self.log.info('frame=%s:%d function=%s',
                          Path(frame.f_code.co_filename).name, line,
                          frame.f_code.co_name)

    def wrap(self, owner, name: str) -> None:
        """Обернуть этап без изменения результата и распространения ошибок."""
        original = getattr(owner, name)

        @wraps(original)
        def traced(*args, **kwargs):
            """Записать начало/конец, не сериализуя аргументы и результат."""
            self.log.info('%s begin', name)
            try:
                result = original(*args, **kwargs)
            except Exception as error:
                self.error(name, error)
                raise
            self.log.info('%s end', name)
            return result

        self._patches.append((owner, name, original))
        setattr(owner, name, traced)

    def install(self) -> None:
        """Подключить этапы файла и окна только в диагностическом процессе."""
        from password_generator import storage
        from password_generator.storage_ui import StorageFrame

        for owner, names in (
            (storage, ('_atomic_write',)),
            (storage.VaultSession, ('_write', 'add', 'delete')),
            (StorageFrame, ('_saved', '_opened', '_refresh', '_render_entries')),
        ):
            for name in names:
                self.wrap(owner, name)

        start = StorageFrame._start
        poll = StorageFrame._poll

        def start_traced(frame, operation, on_success):
            """Включить независимый таймер до начала фоновой операции."""
            if not frame.busy:
                self.log.info('operation begin')
                # Таймер работает и при блокировке Python. exit=False означает,
                # что диагностика сама не завершает приложение и запись файла.
                faulthandler.dump_traceback_later(
                    20, repeat=True, file=self.stream, exit=False
                )
            return start(frame, operation, on_success)

        def poll_traced(frame):
            """Отключить таймер после обработки результата и перерисовки."""
            try:
                poll(frame)
            except Exception as error:
                self.error('ui_completion', error)
                raise
            if not frame.busy:
                self.log.info('operation ui_complete')
                faulthandler.cancel_dump_traceback_later()

        self._patches.extend(((StorageFrame, '_start', start),
                              (StorageFrame, '_poll', poll)))
        StorageFrame._start = start_traced
        StorageFrame._poll = poll_traced

    def close(self) -> None:
        """Отключить таймер, восстановить функции, затем закрыть журнал."""
        faulthandler.cancel_dump_traceback_later()
        faulthandler.disable()
        for owner, name, original in reversed(self._patches):
            setattr(owner, name, original)
        self.log.info('diagnostics closed')
        self.stream.close()
