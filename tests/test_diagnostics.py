"""Проверить исключение секретов из диагностического журнала."""

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from password_generator.diagnostics import SaveDiagnostics


class DiagnosticsTests(unittest.TestCase):
    """Журнал сохраняет этапы и ошибки, но не пользовательские значения."""

    def test_result_and_exception_are_not_logged(self):
        """Возврат и исключение сохраняют поведение, секрет остаётся вне файла."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'check.log'
            with patch('password_generator.diagnostics.faulthandler'):
                diagnostic = SaveDiagnostics(path)

                def echo(value):
                    """Вернуть искусственный секрет без изменения."""
                    return value

                def fail(value):
                    """Искусственная ошибка содержит секрет в тексте."""
                    raise ValueError(value)

                owner = SimpleNamespace(echo=echo, fail=fail)
                diagnostic.wrap(owner, 'echo')
                diagnostic.wrap(owner, 'fail')
                secret = 'ARTIFICIAL_SECRET_DO_NOT_LOG'
                self.assertEqual(owner.echo(secret), secret)
                with self.assertRaisesRegex(ValueError, secret):
                    owner.fail(secret)
                diagnostic.close()
                self.assertIs(owner.echo, echo)
                self.assertIs(owner.fail, fail)
            text = path.read_text(encoding='utf-8')
            self.assertNotIn(secret, text)
            self.assertIn('echo end', text)
            self.assertIn('error_type=ValueError', text)

    def test_timer_covers_worker_and_ui_completion(self):
        """Опрос занятой операции не отменяет таймер; завершение отменяет."""
        from password_generator.storage_ui import StorageFrame

        with tempfile.TemporaryDirectory() as directory, \
                patch('password_generator.diagnostics.faulthandler') as faults, \
                patch.object(StorageFrame, '_start') as start, \
                patch.object(StorageFrame, '_poll'):
            diagnostic = SaveDiagnostics(Path(directory) / 'check.log')
            diagnostic.install()
            try:
                frame = SimpleNamespace(busy=False)
                StorageFrame._start(frame, lambda: None, lambda result: None)
                self.assertTrue(start.called)
                faults.dump_traceback_later.assert_called_once()
                self.assertFalse(faults.dump_traceback_later.call_args.kwargs['exit'])
                frame.busy = True
                StorageFrame._poll(frame)
                faults.cancel_dump_traceback_later.assert_not_called()
                frame.busy = False
                StorageFrame._poll(frame)
                faults.cancel_dump_traceback_later.assert_called_once()
            finally:
                diagnostic.close()
