"""Реальные криптографические и файловые проверки на искусственных данных."""

import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from password_generator.encryption import (
    EncryptionError, decrypt_payload, derive_cipher,
)
from password_generator.storage import MAX_FILE_SIZE, VaultError, VaultSession

MASTER = "  educational-master-2026  "
SECRET = "Example-only-V7!mQ2#zR9@k"


class EncryptionTests(unittest.TestCase):
    """Проверить библиотечный ключ, соль, ошибки и сохранение пробелов."""

    def test_same_password_and_salt_derive_same_key(self) -> None:
        """Независимые объекты ключа должны расшифровывать один токен."""
        salt = b"educational-salt"
        token = derive_cipher(MASTER, salt).encrypt(b"artificial example")
        cipher = derive_cipher(MASTER, salt)
        self.assertEqual(
            decrypt_payload(cipher, token.decode("ascii")),
            b"artificial example",
        )

    def test_wrong_password_and_different_salt_fail(self) -> None:
        """Проверить неверный пароль, обрезанные пробелы и другую соль."""
        token = derive_cipher(MASTER, b"educational-salt").encrypt(b"example")
        for password, salt in (
            ("wrong-master-2026", b"educational-salt"),
            (MASTER.strip(), b"educational-salt"),
            (MASTER, b"different---salt"),
        ):
            with self.assertRaises(EncryptionError):
                decrypt_payload(
                    derive_cipher(password, salt), token.decode("ascii")
                )

    def test_invalid_master_and_salt(self) -> None:
        """Параметры проверяются до запуска дорогостоящего алгоритма."""
        for password in ("", "short", "x" * 1025, None, "\ud800" * 12):
            with self.assertRaises(EncryptionError):
                derive_cipher(password, b"educational-salt")
        with self.assertRaises(EncryptionError):
            derive_cipher(MASTER, b"short")


class StorageTests(unittest.TestCase):
    """Работать с отдельным временным каталогом в каждом тесте."""

    def setUp(self) -> None:
        """Создать пустое настоящее хранилище для проверки операций."""
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "example.vault"
        self.session = VaultSession.create(self.path, MASTER)

    def test_round_trip_and_encrypted_names(self) -> None:
        """Сохранить Unicode и пробелы без открытого текста на диске."""
        entry = self.session.add("  Учебная запись  ", " " + SECRET + " ")
        raw = self.path.read_bytes()
        for value in (MASTER, SECRET, "Учебная запись"):
            self.assertNotIn(value.encode("utf-8"), raw)
        reopened = VaultSession.open(self.path, MASTER)
        self.assertEqual(reopened.entries, self.session.entries)
        self.assertEqual(entry.title, "Учебная запись")
        self.assertEqual(reopened.entries[0].password, " " + SECRET + " ")
        self.assertNotIn(SECRET, repr(entry))

    def test_salts_and_ciphertexts_differ(self) -> None:
        """Новые хранилища с одним мастер-паролем имеют разные соли."""
        other = self.path.with_name("other.vault")
        VaultSession.create(other, MASTER)
        first = json.loads(self.path.read_bytes())
        second = json.loads(other.read_bytes())
        self.assertNotEqual(first["salt"], second["salt"])
        self.assertNotEqual(first["token"], second["token"])

    def test_existing_file_is_not_overwritten(self) -> None:
        """Создание по существующему имени не портит последнюю версию."""
        before = self.path.read_bytes()
        with self.assertRaises(FileExistsError):
            VaultSession.create(self.path, MASTER)
        self.assertEqual(self.path.read_bytes(), before)

    def test_create_race_is_not_overwritten(self) -> None:
        """Файл, появившийся непосредственно перед публикацией, сохраняется."""
        target = self.path.with_name("race.vault")

        def competing_writer(source, destination):
            """Имитировать появление файла между проверкой пути и os.link."""
            Path(destination).write_bytes(b"other writer")
            raise FileExistsError

        with patch("password_generator.storage.os.link", competing_writer):
            with self.assertRaises(FileExistsError):
                VaultSession.create(target, MASTER)
        self.assertEqual(target.read_bytes(), b"other writer")
        self.assertEqual(list(self.path.parent.glob(".vault-*")), [])

    def test_duplicate_titles_delete_by_id(self) -> None:
        """Удалить по ID, сохранив другую запись с тем же названием."""
        first = self.session.add("example", SECRET)
        second = self.session.add("example", "another artificial password")
        self.session.delete(first.identifier)
        self.assertEqual(self.session.entries, (second,))
        self.assertEqual(
            VaultSession.open(self.path, MASTER).entries, (second,)
        )
        with self.assertRaises(VaultError):
            self.session.delete(first.identifier)

    def test_failed_write_preserves_file_and_memory(self) -> None:
        """Отказ замены не приводит к ложному сохранению или удалению."""
        entry = self.session.add("example", SECRET)
        before = self.path.read_bytes()
        with patch("password_generator.storage.os.replace",
                   side_effect=PermissionError):
            with self.assertRaises(PermissionError):
                self.session.add("new", "new artificial password")
            with self.assertRaises(PermissionError):
                self.session.delete(entry.identifier)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.session.entries, (entry,))
        self.assertEqual(list(self.path.parent.glob(".vault-*")), [])

    def test_wrong_password_and_tampering(self) -> None:
        """Неверный ключ и изменение зашифрованного блока отклоняются."""
        before = self.path.read_bytes()
        with self.assertRaises(EncryptionError):
            VaultSession.open(self.path, "wrong-master-2026")
        self.assertEqual(self.path.read_bytes(), before)
        data = json.loads(before)
        token = bytearray(base64.urlsafe_b64decode(data["token"]))
        token[-5] ^= 1
        data["token"] = base64.urlsafe_b64encode(token).decode("ascii")
        self.path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(EncryptionError):
            VaultSession.open(self.path, MASTER)

    def test_invalid_header_is_rejected_before_kdf(self) -> None:
        """Не доверять версии, типам, соли и затратам Argon2id из файла."""
        original = json.loads(self.path.read_bytes())
        variants = []
        for field, value in (
            ("version", 2), ("version", True), ("cipher", "unknown"),
            ("kdf", []), ("salt", "bad"), ("salt", 12), ("token", None),
        ):
            variants.append({**original, field: value})
        for field, value in (("memory_cost", 10**12), ("iterations", 3.0)):
            variants.append({
                **original, "kdf": {**original["kdf"], field: value}
            })
        for variant in variants:
            self.path.write_text(json.dumps(variant), encoding="utf-8")
            with patch("password_generator.storage.derive_cipher") as derive:
                with self.assertRaises(VaultError):
                    VaultSession.open(self.path, MASTER)
                derive.assert_not_called()

    def test_invalid_json_duplicate_fields_and_size(self) -> None:
        """Отклонить мусор, дубли полей, неправильный корень и большой файл."""
        utf16_header = self.path.read_text(encoding="utf-8").encode("utf-16")
        for raw in (
            b"broken", b"[]", b'{"version":1,"version":1}', b"\xff",
            utf16_header,
        ):
            self.path.write_bytes(raw)
            with self.assertRaises(VaultError):
                VaultSession.open(self.path, MASTER)
        with self.path.open("wb") as output:
            output.seek(MAX_FILE_SIZE)
            output.write(b"x")
        with self.assertRaises(VaultError):
            VaultSession.open(self.path, MASTER)

    def test_invalid_encrypted_schema(self) -> None:
        """Даже успешно расшифрованные данные должны соответствовать схеме."""
        self.session.add("example", SECRET)
        header = json.loads(self.path.read_bytes())
        cipher = derive_cipher(
            MASTER, base64.urlsafe_b64decode(header["salt"])
        )
        for payload in ({"version": 2, "entries": []},
                        {"version": 1, "entries": [{}]}):
            header["token"] = cipher.encrypt(
                json.dumps(payload).encode("utf-8")
            ).decode("ascii")
            self.path.write_text(json.dumps(header), encoding="utf-8")
            with self.assertRaises(VaultError):
                VaultSession.open(self.path, MASTER)

    def test_invalid_records(self) -> None:
        """Ошибочные записи не меняют файл."""
        before = self.path.read_bytes()
        for title, password in (
            (" ", SECRET), ("x" * 101, SECRET), ("example", ""),
            ("example", "x" * 1025), (None, SECRET),
        ):
            with self.assertRaises(VaultError):
                self.session.add(title, password)
        self.assertEqual(self.path.read_bytes(), before)

    def test_lock_blocks_operations(self) -> None:
        """Заблокированный сеанс не отдаёт записи и не принимает правки."""
        entry = self.session.add("example", SECRET)
        self.session.lock()
        self.assertIsNone(self.session._cipher)
        for action in (
            lambda: self.session.entries,
            lambda: self.session.add("new", SECRET),
            lambda: self.session.delete(entry.identifier),
        ):
            with self.assertRaises(VaultError):
                action()

    def test_output_size_limit_preserves_previous_file(self) -> None:
        """Отказ при превышении лимита не меняет файл и сеанс."""
        before = self.path.read_bytes()
        with patch("password_generator.storage.MAX_FILE_SIZE", 1):
            with self.assertRaises(VaultError):
                self.session.add("example", SECRET)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.session.entries, ())

    def test_invalid_ids_dates_and_duplicate_ids(self) -> None:
        """Отклонить неверные ID, даты и дубли шифрованных записей."""
        self.session.add("example", SECRET)
        header = json.loads(self.path.read_bytes())
        cipher = derive_cipher(
            MASTER, base64.urlsafe_b64decode(header["salt"])
        )
        original = json.loads(decrypt_payload(cipher, header["token"]))
        entry = original["entries"][0]
        variants = [
            [{**entry, "id": "not-a-uuid"}],
            [{**entry, "created_at": "2026-10-31"}],
            [entry, entry],
        ]
        for entries in variants:
            header["token"] = cipher.encrypt(json.dumps({
                "version": 1, "entries": entries,
            }).encode("utf-8")).decode("ascii")
            self.path.write_text(json.dumps(header), encoding="utf-8")
            with self.assertRaises(VaultError):
                VaultSession.open(self.path, MASTER)


if __name__ == "__main__":
    unittest.main()
