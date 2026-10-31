"""Получение ключа из мастер-пароля библиотечной реализацией Argon2id.

Шифрование и проверку подлинности выполняет Fernet из cryptography.
Собственных криптографических алгоритмов здесь нет. Ключ и мастер-пароль
существуют только в памяти, гарантированное обнуление строк не заявляется.
"""

import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

SALT_LENGTH = 16
# Для формата 1 допускается ровно этот профиль. Файл не может заставить
# приложение выделить неограниченную память или выполнить миллионы проходов.
KDF_PARAMETERS = {
    "name": "argon2id",
    "length": 32,
    "iterations": 3,
    "lanes": 4,
    "memory_cost": 65536,
}


class EncryptionError(ValueError):
    """Ошибка параметров или расшифрования с безопасным сообщением."""


def validate_master_password(password: str) -> None:
    """Проверить длину 12–1024 без удаления пробелов; иначе EncryptionError."""
    if not isinstance(password, str) or not 12 <= len(password) <= 1024:
        raise EncryptionError(
            "Мастер-пароль должен содержать 12–1024 символа."
        )
    try:
        password.encode("utf-8")
    except UnicodeEncodeError:
        raise EncryptionError(
            "Мастер-пароль содержит некорректный Unicode."
        ) from None


def derive_cipher(master_password: str, salt: bytes) -> Fernet:
    """Получить Fernet из мастер-пароля и 16-байтовой соли.

    Возвращает объект шифрования, хранящий ключ в памяти. Одинаковые пароль
    и соль дают тот же ключ. Ошибки параметров вызывают EncryptionError;
    ошибки нехватки ресурсов и неподдерживаемого алгоритма передаются выше.
    """
    validate_master_password(master_password)
    if not isinstance(salt, bytes) or len(salt) != SALT_LENGTH:
        raise EncryptionError("Некорректная соль хранилища.")
    # Соль не является секретом: она делает ключи разных хранилищ различными
    # даже при одинаковом мастер-пароле. Argon2id требует памяти и вычислений,
    # чтобы затруднить массовую проверку вариантов мастер-пароля.
    # Ключ вычисляется заново при открытии: отдельный файл ключа не нужен.
    kdf = Argon2id(
        salt=salt,
        length=KDF_PARAMETERS["length"],
        iterations=KDF_PARAMETERS["iterations"],
        lanes=KDF_PARAMETERS["lanes"],
        memory_cost=KDF_PARAMETERS["memory_cost"],
    )
    # Fernet ожидает не произвольную строку пароля, а 32 байта ключа,
    # закодированные URL-safe Base64. Base64 само по себе не шифрует данные.
    key = kdf.derive(master_password.encode("utf-8"))
    return Fernet(base64.urlsafe_b64encode(key))


def decrypt_payload(cipher: Fernet, token: str) -> bytes:
    """Расшифровать токен; неверный ключ и повреждение дают общую ошибку.

    Времени жизни у записей нет. Подлинность проверяется Fernet до возврата
    расшифрованных байтов. Текст токена не включается в исключение.
    """
    try:
        return cipher.decrypt(token.encode("ascii"))
    except (InvalidToken, UnicodeEncodeError):
        raise EncryptionError(
            "Неверный мастер-пароль или повреждённый файл."
        ) from None
