"""Версионированное зашифрованное хранилище с атомарным сохранением.

Файлы содержат только технический заголовок и Fernet-токен; названия записей
тоже шифруются. После ошибки записи состояние сеанса не изменяется.
Одновременная запись разными экземплярами приложения не поддерживается.
"""

import base64
import binascii
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import tempfile
from uuid import UUID, uuid4

from cryptography.fernet import Fernet

from password_generator.encryption import (
    KDF_PARAMETERS, SALT_LENGTH, decrypt_payload, derive_cipher,
)

MAX_FILE_SIZE = 5 * 1024 * 1024


class VaultError(ValueError):
    """Некорректное хранилище или недопустимая операция над записями."""


@dataclass(frozen=True)
class VaultEntry:
    """Запись сеанса. Секрет и название исключены из стандартного repr.

    identifier — UUID, title — название, password — исходный пароль,
    created_at — время создания с часовым поясом в формате ISO 8601.
    """

    identifier: str
    title: str = field(repr=False)
    password: str = field(repr=False)
    created_at: str


def _unique_object(pairs: list[tuple]) -> dict:
    """Собрать JSON-объект, отклонив повторяющиеся имена полей."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise VaultError("В файле повторяются поля JSON.")
        result[key] = value
    return result


def _parse_json(data: bytes) -> dict:
    """Прочитать UTF-8 JSON-объект или вызвать VaultError без содержимого."""
    try:
        value = json.loads(
            data.decode("utf-8"), object_pairs_hook=_unique_object
        )
    except VaultError:
        raise
    except (ValueError, RecursionError):
        raise VaultError("Некорректный JSON хранилища.") from None
    if not isinstance(value, dict):
        raise VaultError("Хранилище должно содержать JSON-объект.")
    return value


def _validate_record(title: str, password: str) -> str:
    """Проверить запись и вернуть название без крайних пробелов.

    Пароль не обрезается. Ограничение пароля 1024 совпадает с ручной оценкой.
    Некорректные строки вызывают VaultError без включения их содержимого.
    """
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 100:
        raise VaultError("Название должно содержать 1–100 символов.")
    if not isinstance(password, str) or not 1 <= len(password) <= 1024:
        raise VaultError("Пароль записи должен содержать 1–1024 символа.")
    try:
        title.encode("utf-8")
        password.encode("utf-8")
    except UnicodeEncodeError:
        raise VaultError("Запись содержит некорректный Unicode.") from None
    return title.strip()


def _read_header(path: Path) -> tuple[dict, bytes]:
    """Проверить размер и заголовок до дорогостоящего получения ключа.

    Возвращает заголовок и соль. OSError передаётся вызывающему коду,
    ошибки формата вызывают VaultError. Чтение ограничено даже при росте файла.
    """
    with path.open("rb") as source:
        raw = source.read(MAX_FILE_SIZE + 1)
    if len(raw) > MAX_FILE_SIZE:
        raise VaultError("Размер хранилища превышает 5 МиБ.")
    header = _parse_json(raw)
    if set(header) != {"version", "cipher", "kdf", "salt", "token"}:
        raise VaultError("Некорректные поля заголовка хранилища.")
    if type(header["version"]) is not int or header["version"] != 1:
        raise VaultError("Неподдерживаемая версия хранилища.")
    if header["cipher"] != "fernet" or header["kdf"] != KDF_PARAMETERS:
        raise VaultError("Неподдерживаемый алгоритм или параметры ключа.")
    # Отдельно исключаем bool и float: в Python True == 1 и 3.0 == 3.
    if any(
        type(header["kdf"][key]) is not type(expected)
        for key, expected in KDF_PARAMETERS.items()
    ):
        raise VaultError("Некорректные типы параметров ключа.")
    if not isinstance(header["salt"], str):
        raise VaultError("Некорректная соль хранилища.")
    try:
        salt = base64.b64decode(header["salt"], altchars=b"-_", validate=True)
    except (ValueError, binascii.Error):
        raise VaultError("Некорректная соль хранилища.") from None
    if len(salt) != SALT_LENGTH:
        raise VaultError("Некорректная длина соли хранилища.")
    if not isinstance(header["token"], str) or not header["token"]:
        raise VaultError("Отсутствует зашифрованный блок.")
    return header, salt


def _read_entries(payload: bytes) -> list[VaultEntry]:
    """Проверить схему и уникальность идентификаторов после расшифрования."""
    data = _parse_json(payload)
    if (
        set(data) != {"version", "entries"}
        or type(data["version"]) is not int or data["version"] != 1
        or not isinstance(data["entries"], list)
    ):
        raise VaultError("Некорректная схема записей хранилища.")
    entries = []
    identifiers = set()
    for item in data["entries"]:
        if not isinstance(item, dict) or set(item) != {
            "id", "title", "password", "created_at",
        }:
            raise VaultError("Некорректные поля записи.")
        title = _validate_record(item["title"], item["password"])
        try:
            if not isinstance(item["id"], str):
                raise ValueError
            if str(UUID(item["id"])) != item["id"]:
                raise ValueError
            if not isinstance(item["created_at"], str):
                raise ValueError
            date = datetime.fromisoformat(item["created_at"])
            if date.tzinfo is None:
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise VaultError(
                "Некорректный идентификатор или дата записи."
            ) from None
        if item["id"] in identifiers:
            raise VaultError("Повторяющийся идентификатор записи.")
        identifiers.add(item["id"])
        entries.append(VaultEntry(
            item["id"], title, item["password"], item["created_at"]
        ))
    return entries


def _atomic_write(path: Path, data: bytes, *, create: bool = False) -> None:
    """Записать зашифрованные байты через временный файл в том же каталоге.

    При создании используем жёсткую ссылку: она атомарно создаёт новое имя
    и отказывает, если имя уже существует. Обновление использует os.replace.
    OSError передаётся выше. Временный файл убирается и после ошибки записи.
    """
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=".vault-", delete=False
        ) as output:
            temporary = Path(output.name)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        if create:
            os.link(temporary, path)
        else:
            os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class VaultSession:
    """Открытое хранилище: путь, соль, ключ Fernet и записи в памяти.

    Создаётся через create/open. Список entries отдаёт неизменяемый снимок.
    После lock любые операции с записями запрещены до нового открытия.
    """

    def __init__(
        self, path: Path, salt: bytes, cipher: Fernet,
        entries: list[VaultEntry],
    ) -> None:
        """Запомнить параметры проверенного хранилища без записи на диск."""
        self.path = path
        self._salt = salt
        self._cipher = cipher
        self._entries = entries

    @classmethod
    def create(cls, path: Path, master_password: str) -> "VaultSession":
        """Создать пустой файл без перезаписи; пароль 12–1024 символа.

        Возвращает открытый сеанс. При существующем пути FileExistsError;
        ошибки параметров — ValueError, файловой системы — OSError.
        """
        path = Path(path)
        if path.exists():
            raise FileExistsError("Хранилище уже существует.")
        salt = secrets.token_bytes(SALT_LENGTH)
        session = cls(path, salt, derive_cipher(master_password, salt), [])
        session._write([], create=True)
        return session

    @classmethod
    def open(cls, path: Path, master_password: str) -> "VaultSession":
        """Проверить файл и расшифровать записи, вернув новый сеанс.

        ValueError означает ошибку формата или мастер-пароля, OSError — чтения.
        При неверном ключе существующий файл никогда не изменяется.
        """
        path = Path(path)
        header, salt = _read_header(path)
        cipher = derive_cipher(master_password, salt)
        entries = _read_entries(decrypt_payload(cipher, header["token"]))
        return cls(path, salt, cipher, entries)

    def _require_open(self) -> None:
        """Запретить обращение к заблокированному сеансу через VaultError."""
        if self._cipher is None:
            raise VaultError("Хранилище заблокировано.")

    @property
    def entries(self) -> tuple[VaultEntry, ...]:
        """Вернуть неизменяемый список записей открытого сеанса."""
        self._require_open()
        return tuple(self._entries)

    def _write(
        self, entries: list[VaultEntry], *, create: bool = False,
    ) -> None:
        """Зашифровать новый список и записать, не меняя память при ошибке."""
        self._require_open()
        payload = {
            "version": 1,
            "entries": [
                {"id": entry.identifier, "title": entry.title,
                 "password": entry.password, "created_at": entry.created_at}
                for entry in entries
            ],
        }
        token = self._cipher.encrypt(
            json.dumps(payload, ensure_ascii=False).encode("utf-8")
        )
        header = {
            "version": 1, "cipher": "fernet", "kdf": KDF_PARAMETERS,
            "salt": base64.urlsafe_b64encode(self._salt).decode("ascii"),
            "token": token.decode("ascii"),
        }
        raw = json.dumps(header, ensure_ascii=True).encode("utf-8")
        if len(raw) > MAX_FILE_SIZE:
            raise VaultError("Хранилище превысит ограничение 5 МиБ.")
        _atomic_write(self.path, raw, create=create)

    def add(self, title: str, password: str) -> VaultEntry:
        """Сохранить новую запись; одинаковые названия разрешены.

        Возвращает сохранённую запись. При ошибке проверки или записи
        список в памяти и последняя сохранённая версия остаются прежними.
        """
        self._require_open()
        title = _validate_record(title, password)
        entry = VaultEntry(
            str(uuid4()), title, password,
            datetime.now(timezone.utc).isoformat(),
        )
        updated = [*self._entries, entry]
        self._write(updated)
        self._entries = updated
        return entry

    def delete(self, identifier: str) -> None:
        """Удалить запись по ID; неизвестный ID вызывает VaultError."""
        self._require_open()
        updated = [e for e in self._entries if e.identifier != identifier]
        if len(updated) == len(self._entries):
            raise VaultError("Запись не найдена.")
        self._write(updated)
        self._entries = updated

    def lock(self) -> None:
        """Убрать ссылки на ключ и записи без гарантии обнуления памяти."""
        self._cipher = None
        self._entries = []
