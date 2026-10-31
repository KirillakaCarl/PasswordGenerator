"""Проверки пользовательского сценария до запуска создания файла.

Диалоги подменены, но валидация настоящая. Графическая среда и файловые
операции не нужны: проверяем, что невалидный ввод не запускает создание,
а после исправления не приходится заново выбирать путь.
"""

from functools import partial
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from password_generator.storage_ui import StorageFrame


class MasterDialogTests(unittest.TestCase):
    """Проверить предупреждение, повторный ввод и отмену."""

    def setUp(self) -> None:
        """Подготовить только состояние, необходимое сценарию создания."""
        self.frame = SimpleNamespace(
            busy=False, session=None, _status=Mock(), _start=Mock(),
            _opened=Mock(),
        )
        self.frame._ask_master = partial(StorageFrame._ask_master, self.frame)

    def test_invalid_password_does_not_start_creation(self) -> None:
        """После короткого/длинного ввода и отмены файл не создаётся."""
        for password in ("short", "", "x" * 1025):
            with (
                self.subTest(length=len(password)),
                patch(
                    "password_generator.storage_ui.filedialog."
                    "asksaveasfilename", return_value="example.vault",
                ),
                patch(
                    "password_generator.storage_ui.simpledialog.askstring",
                    side_effect=[password, None],
                ),
                patch(
                    "password_generator.storage_ui.messagebox.showwarning"
                ) as warning,
            ):
                StorageFrame._create(self.frame)
                self.frame._start.assert_not_called()
                warning.assert_called_once()
                message = warning.call_args.args[1]
                self.assertIn("Хранилище не создано", message)
                self.assertIn("12 до 1024", message)
                self.assertIn("Пробелы", message)

    def test_retry_keeps_selected_path(self) -> None:
        """После исправления создание запускается ровно один раз."""
        valid = "example-master-2026"
        with (
            patch(
                "password_generator.storage_ui.filedialog.asksaveasfilename",
                return_value="example.vault",
            ) as choose_path,
            patch(
                "password_generator.storage_ui.simpledialog.askstring",
                side_effect=["short", valid, valid],
            ),
            patch("password_generator.storage_ui.messagebox.showwarning"),
        ):
            StorageFrame._create(self.frame)
            choose_path.assert_called_once()
            self.frame._start.assert_called_once()

    def test_confirmation_mismatch_warns_and_retries(self) -> None:
        """При несовпадении показать предупреждение и повторить ввод."""
        valid = "example-master-2026"
        with (
            patch(
                "password_generator.storage_ui.simpledialog.askstring",
                side_effect=[valid, "different-master", valid, valid],
            ),
            patch(
                "password_generator.storage_ui.messagebox.showwarning"
            ) as warning,
        ):
            self.assertEqual(self.frame._ask_master(confirm=True), valid)
            self.assertIn("не совпадают", warning.call_args.args[1])

    def test_valid_boundaries_and_confirmation_cancel(self) -> None:
        """Длины 12 и 1024 допустимы, отмена подтверждения возвращает None."""
        for size in (12, 1024):
            password = "x" * size
            with patch(
                "password_generator.storage_ui.simpledialog.askstring",
                side_effect=[password, password],
            ):
                self.assertEqual(
                    self.frame._ask_master(confirm=True), password
                )
        with patch(
            "password_generator.storage_ui.simpledialog.askstring",
            side_effect=["example-master-2026", None],
        ):
            self.assertIsNone(self.frame._ask_master(confirm=True))

    def test_open_warning_does_not_claim_creation(self) -> None:
        """Предупреждение при открытии описывает именно открытие файла."""
        with (
            patch(
                "password_generator.storage_ui.simpledialog.askstring",
                side_effect=["short", None],
            ),
            patch(
                "password_generator.storage_ui.messagebox.showwarning"
            ) as warning,
        ):
            self.assertIsNone(self.frame._ask_master(confirm=False))
            self.assertIn("Хранилище не открыто", warning.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
