"""Объяснимая учебная оценка сложности без сети и передачи паролей.

Формула и ограничения описаны в docs/ASSESSMENT_RULES.md. Балл не является
энтропией или прогнозом времени взлома. Базовая функция сохранена для сравнения
с улучшением, предложенным ИИ, и не используется в пользовательском окне.
"""

from collections import Counter
from dataclasses import dataclass

MAX_PASSWORD_LENGTH = 1024
COMMON_FRAGMENTS = (
    "password", "qwerty", "admin", "welcome", "letmein", "changeme", "пароль",
)
SEQUENCES = (
    "abcdefghijklmnopqrstuvwxyz", "0123456789",
    "qwertyuiop", "asdfghjkl", "zxcvbnm",
)
SUBSTITUTIONS = str.maketrans({
    "@": "a", "$": "s", "0": "o", "1": "i",
    "3": "e", "4": "a", "5": "s", "7": "t",
})


@dataclass(frozen=True)
class AssessmentResult:
    """Балл, категория и пояснения, не содержащие сам пароль.

    score находится в пределах 0–100. category — русское название категории.
    explanations — неизменяемый кортеж общих пояснений без копий ввода.
    """

    score: int
    category: str
    explanations: tuple[str, ...]


def _make_result(score: int, reasons: list[str]) -> AssessmentResult:
    """Ограничить целый балл и вернуть категорию с пояснениями."""
    score = max(0, min(100, score))
    if score < 40:
        category = "Слабый"
    elif score < 75:
        category = "Средний"
    else:
        category = "Сильный"
    return AssessmentResult(score, category, tuple(reasons))


def assess_baseline(password: str) -> AssessmentResult:
    """Оценить строку по длине и группам для учебного сравнения.

    Возвращает AssessmentResult. Пустая строка не получает категорию сложности.
    При неправильном типе или длине больше 1024 вызывает ValueError.
    Строка не обрезается, не изменяется и никуда не сохраняется.
    """
    if not isinstance(password, str):
        raise ValueError("Пароль для оценки должен быть строкой.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError("Для оценки введите не более 1024 символов.")
    if not password:
        return AssessmentResult(0, "Не задан", ("Введите пароль для оценки.",))

    groups = sum((
        any(char.islower() for char in password),
        any(char.isupper() for char in password),
        any(char.isdigit() for char in password),
        any(
            not (char.islower() or char.isupper() or char.isdigit())
            for char in password
        ),
    ))
    score = min(60, 3 * len(password)) + 10 * groups
    reasons = [f"Длина: {len(password)}. Групп символов: {groups} из 4."]
    if len(password) < 8:
        score = min(score, 39)
        reasons.append("Меньше 8 символов: оценка ограничена слабой.")
    elif len(password) < 12:
        score = min(score, 74)
        reasons.append("Меньше 12 символов: оценка ограничена средней.")
    return _make_result(score, reasons)


def _has_repeated_block(text: str) -> bool:
    """Вернуть True, если непустая строка целиком состоит из повторов блока.

    text — вспомогательная строка без учёта регистра. Проверяем только длины,
    делящие её длину без остатка, поэтому неполный повтор не распознаётся.
    """
    return any(
        len(text) % size == 0
        and text[:size] * (len(text) // size) == text
        for size in range(1, len(text) // 2 + 1)
    )


def _has_sequence(text: str) -> bool:
    """Найти фрагмент длиной 4 в прямых и обратных известных алфавитах.

    Любая более длинная последовательность тоже содержит такой фрагмент.
    Проверка применяется к представлению без учёта регистра, без подстановок.
    """
    return any(
        text[index:index + 4] in sequence
        or text[index:index + 4] in sequence[::-1]
        for index in range(len(text) - 3)
        for sequence in SEQUENCES
    )


def assess_password(password: str) -> AssessmentResult:
    """Вернуть улучшенную оценку с ограничениями за узнаваемые шаблоны.

    Вход и ошибки те же, что у assess_baseline. Для поиска шаблонов создаётся
    временное представление без регистра; исходный пароль не меняется.
    Пояснения содержат признаки, но не обнаруженный секретный фрагмент.
    """
    baseline = assess_baseline(password)
    if not password:
        return baseline
    score = baseline.score
    reasons = list(baseline.explanations)
    folded = password.casefold()
    # Представление используется только для поиска простых подстановок.
    # Оно не подменяет пароль и не используется в подсчёте исходной длины.
    normalized = "".join(
        char for char in folded.translate(SUBSTITUTIONS) if char.isalpha()
    )
    if any(fragment in normalized for fragment in COMMON_FRAGMENTS):
        score = min(score, 39)
        reasons.append("Найден распространённый фрагмент: максимум 39 баллов.")
    if _has_repeated_block(folded):
        score = min(score, 39)
        reasons.append("Строка состоит из повторяющегося блока: максимум 39.")
    counts = Counter(folded)
    if len(counts) <= 2 or max(counts.values()) * 2 >= len(folded):
        score = min(score, 39)
        reasons.append(
            "Мало разных символов или один преобладает: максимум 39."
        )
    if any(
        folded[index] == folded[index + 1] == folded[index + 2]
        for index in range(len(folded) - 2)
    ):
        score = min(score, 74)
        reasons.append("Есть три одинаковых символа подряд: максимум 74.")
    if _has_sequence(folded):
        score = min(score - 20, 74)
        reasons.append(
            "Есть последовательность символов: минус 20, максимум 74."
        )
    if len(reasons) == len(baseline.explanations):
        reasons.append("Известные этому алгоритму шаблоны не обнаружены.")
    return _make_result(score, reasons)
