"""Генерация паролей по настройкам пользователя, независимо от Tkinter.

Сначала проверяются длина и выбранные группы. Затем строится общий алфавит
и с помощью secrets выбираются случайные символы. Кандидат принимается,
только если содержит каждую выбранную группу. Неудачный кандидат заменяется
новым. Проверка не закрепляет группы за определёнными позициями.
Результат возвращается интерфейсу; этот модуль не работает с файлами.
"""

from dataclasses import dataclass
import secrets
import string

MIN_LENGTH = 4
MAX_LENGTH = 128


@dataclass(frozen=True)
class GenerationOptions:
    """Настройки: длина 4–128 и четыре переключателя групп символов.

    Проверка выполняется при генерации. frozen запрещает случайно изменять
    уже созданные настройки. По умолчанию включены все группы, длина 16.
    """

    length: int = 16
    # dataclass создаёт конструктор с этими полями. Аннотации объясняют типы,
    # но сами не проверяют вход: это делает generate_password ниже.
    lowercase: bool = True
    uppercase: bool = True
    digits: bool = True
    special: bool = True


def generate_password(options: GenerationOptions) -> str:
    """Вернуть пароль заданной длины с каждой выбранной группой символов.

    options содержит настройки. Некорректный тип или значение вызывает
    ValueError с понятным сообщением без включения входных данных.
    Функция не сохраняет пароль и не выводит его в журнал.
    """
    if not isinstance(options, GenerationOptions):
        raise ValueError("Передайте настройки генерации GenerationOptions.")
    # bool — подкласс int: точный тип исключает True вместо числовой длины.
    if type(options.length) is not int or not MIN_LENGTH <= options.length <= MAX_LENGTH:
        raise ValueError(f"Длина должна быть целым числом от {MIN_LENGTH} до {MAX_LENGTH}.")
    groups = []
    for enabled, alphabet in (
        (options.lowercase, string.ascii_lowercase),
        (options.uppercase, string.ascii_uppercase),
        (options.digits, string.digits),
        (options.special, string.punctuation),
    ):
        if type(enabled) is not bool:
            raise ValueError("Переключатели групп должны иметь значения True или False.")
        if enabled:
            groups.append(alphabet)
    if not groups:
        raise ValueError("Выберите хотя бы одну группу символов.")
    alphabet = "".join(groups)
    # join склеивает алфавиты без разделителя: лишних пробелов не появляется.
    # Отбрасываем строки без обязательных групп. Так все допустимые строки
    # остаются равновероятными, без закрепления групп за определёнными позициями.
    # Длина от 4 позволяет вместить все четыре группы. random не используем:
    # secrets предназначен для секретов и берёт случайность у операционной системы.
    while True:
        candidate = "".join(secrets.choice(alphabet) for _ in range(options.length))
        # Внутренний any ищет хотя бы один символ нужной группы; внешний all
        # требует успеха для всех групп. Пароль из одних букв не пройдёт,
        # если пользователь дополнительно включил цифры.
        if all(any(symbol in group for symbol in candidate) for group in groups):
            return candidate
