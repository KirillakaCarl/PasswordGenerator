"""Окно генерации паролей с независимым от интерфейса алгоритмом.

Правила оценки находятся в assessment.py, хранилище — в storage_ui.py.
"""

import tkinter as tk
from tkinter import ttk

from password_generator import __version__
from password_generator.assessment import assess_password
from password_generator.generator import GenerationOptions, generate_password
from password_generator.storage_ui import StorageFrame


class PasswordGeneratorApp(tk.Tk):
    """Главное окно с настройками и текущим паролем в памяти сеанса."""

    def __init__(self) -> None:
        """Создать окно и переменные; без графики возможен TclError."""
        super().__init__()
        self.title(f"PasswordGenerator {__version__} — учебный проект")
        self.geometry("760x640")
        self.minsize(640, 620)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        # StringVar сохраняет ошибочный текст длины для понятной проверки,
        # тогда как IntVar может вызвать ошибку уже при чтении этого текста.
        self.length = tk.StringVar(self, value="16")
        self.lowercase = tk.BooleanVar(self, value=True)
        self.uppercase = tk.BooleanVar(self, value=True)
        self.digits = tk.BooleanVar(self, value=True)
        self.special = tk.BooleanVar(self, value=True)
        self.password = tk.StringVar(self)
        self.show_password = tk.BooleanVar(self, value=False)
        self.status = tk.StringVar(
            self, value="Выберите настройки и нажмите «Сгенерировать»."
        )
        self.manual_password = tk.StringVar(self)
        self.show_manual_password = tk.BooleanVar(self, value=False)
        self.assessment_title = tk.StringVar(
            self, value="Введите пароль для оценки."
        )
        self.generated_assessment = tk.StringVar(self)
        self._build_widgets()
        # Изменение строки сбрасывает прежнюю оценку, чтобы она не относилась
        # к уже изменённому паролю. Оценивание запускается отдельной кнопкой.
        self.manual_password.trace_add("write", self._clear_assessment)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build_widgets(self) -> None:
        """Разместить настройки, результат и кнопки; ничего не возвращать."""
        content = ttk.Frame(self, padding=24)
        content.grid(row=0, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        ttk.Label(
            content, text="PasswordGenerator", font=("Segoe UI", 20, "bold")
        ).grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        ttk.Label(content, text="Создайте пароль по выбранным правилам.").grid(
            row=1, column=0, sticky="w", pady=(0, 16)
        )
        self.notebook = ttk.Notebook(content)
        # Notebook переключает вкладки внутри одного окна. grid размещает
        # элементы по строкам и столбцам; sticky="nsew" растягивает область
        # во все стороны, а weight=1 отдаёт ей свободное место при увеличении.
        self.notebook.grid(row=2, column=0, sticky="nsew")
        content.rowconfigure(2, weight=1)
        generation = ttk.Frame(self.notebook, padding=12)
        generation.columnconfigure(0, weight=1)
        assessment = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(generation, text="Генерация")
        self.notebook.add(assessment, text="Оценка сложности")
        self._build_assessment_tab(assessment)
        self.storage = StorageFrame(
            self.notebook, self.password.get, self.manual_password.get,
            self._clear_secrets, self.status,
        )
        self.notebook.add(self.storage, text="Хранилище")

        settings = ttk.LabelFrame(
            generation, text="Настройки генерации", padding=12
        )
        settings.grid(row=0, column=0, sticky="ew")
        settings.columnconfigure(1, weight=1)
        ttk.Label(settings, text="Длина (4–128):").grid(
            row=0, column=0, sticky="w"
        )
        self.length_input = ttk.Spinbox(
            settings, from_=4, to=128, textvariable=self.length, width=8
        )
        self.length_input.grid(
            row=0, column=1, sticky="w", padx=12, pady=(0, 8)
        )
        for row, (label, variable) in enumerate((
            ("Строчные буквы (a–z)", self.lowercase),
            ("Прописные буквы (A–Z)", self.uppercase),
            ("Цифры (0–9)", self.digits),
            ("Специальные символы (!, @, # и другие)", self.special),
        ), start=1):
            ttk.Checkbutton(settings, text=label, variable=variable).grid(
                row=row, column=0, columnspan=2, sticky="w", pady=2
            )
        self.generate_button = ttk.Button(
            # Передаём сам метод в command, без скобок вызова: Tkinter вызовет
            # его только после нажатия кнопки, а не при построении окна.
            generation, text="Сгенерировать", command=self._generate
        )
        self.generate_button.grid(row=1, column=0, sticky="w", pady=12)
        result = ttk.LabelFrame(
            generation, text="Полученный пароль", padding=12
        )
        result.grid(row=2, column=0, sticky="ew")
        result.columnconfigure(0, weight=1)
        # readonly исключает случайную правку результата. Длинную строку
        # можно прокручивать в поле; значение обновляется через StringVar.
        self.password_input = ttk.Entry(
            result, textvariable=self.password, state="readonly", show="*"
        )
        self.password_input.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Checkbutton(
            result, text="Показать пароль", variable=self.show_password,
            command=self._toggle_visibility,
        ).grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.copy_button = ttk.Button(
            result, text="Копировать", command=self._copy_password,
            state="disabled",
        )
        self.copy_button.grid(row=1, column=1, sticky="e", pady=(8, 0))
        ttk.Label(
            generation, textvariable=self.generated_assessment, wraplength=500,
        ).grid(row=3, column=0, sticky="nw", pady=8)
        ttk.Button(content, text="Закрыть", command=self._close).grid(
            row=3, column=0, sticky="e", pady=(8, 0)
        )
        ttk.Label(
            self, textvariable=self.status, padding=(16, 8), relief="sunken",
            anchor="w", wraplength=600,
        ).grid(row=1, column=0, sticky="ew")

    def _build_assessment_tab(self, tab: ttk.Frame) -> None:
        """Разместить ввод и прокручиваемые пояснения во вкладке tab."""
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(5, weight=1)
        ttk.Label(tab, text="Пароль для оценки (до 1024 символов):").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )
        self.manual_input = ttk.Entry(
            tab, textvariable=self.manual_password, show="*"
        )
        self.manual_input.grid(row=1, column=0, columnspan=2, sticky="ew")
        ttk.Checkbutton(
            tab, text="Показать ввод", variable=self.show_manual_password,
            command=self._toggle_manual_visibility,
        ).grid(row=2, column=0, sticky="w", pady=8)
        self.assess_button = ttk.Button(
            tab, text="Оценить", command=self._assess_manual
        )
        self.assess_button.grid(row=2, column=1, sticky="e")
        ttk.Label(tab, textvariable=self.assessment_title).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=8
        )
        ttk.Label(
            tab,
            text="Учебная оценка: не гарантия стойкости и не время взлома.",
            wraplength=480,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(0, 8))
        self.assessment_details = tk.Text(
            tab, height=7, width=40, wrap="word", state="disabled"
        )
        self.assessment_details.grid(row=5, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(
            tab, orient="vertical", command=self.assessment_details.yview
        )
        scrollbar.grid(row=5, column=1, sticky="ns")
        self.assessment_details.configure(yscrollcommand=scrollbar.set)

    def _set_assessment_details(self, text: str) -> None:
        """Обновить пояснения в защищённом от редактирования поле."""
        self.assessment_details.configure(state="normal")
        self.assessment_details.delete("1.0", "end")
        self.assessment_details.insert("1.0", text)
        self.assessment_details.configure(state="disabled")

    def _clear_assessment(self, *_args: str) -> None:
        """Сбросить оценку; служебные аргументы приходят от Tkinter."""
        self.assessment_title.set("Нажмите «Оценить» для текущего ввода.")
        self._set_assessment_details("")

    def _assess_manual(self) -> None:
        """Оценить ввод без обрезания пробелов и показать пояснения."""
        try:
            result = assess_password(self.manual_password.get())
        except ValueError as error:
            self.assessment_title.set(str(error))
            self._set_assessment_details("")
            return
        title = "Введите пароль для оценки."
        if self.manual_password.get():
            title = f"{result.category} · {result.score} из 100"
        self.assessment_title.set(title)
        self._set_assessment_details("\n\n".join(result.explanations))

    def _toggle_manual_visibility(self) -> None:
        """Изменить маскирование ввода, сохранив его содержимое."""
        self.manual_input.configure(
            show="" if self.show_manual_password.get() else "*"
        )

    def _generate(self) -> None:
        """Прочитать форму и показать пароль или ошибку; ничего не возвращать.

        Старый результат очищается, чтобы при ошибке он не выглядел созданным
        по новым настройкам. Новый пароль всегда изначально скрыт.
        """
        self.password.set("")
        self.generated_assessment.set("")
        self.copy_button.state(["disabled"])
        self.show_password.set(False)
        self._toggle_visibility()
        try:
            raw_length = self.length.get().strip()
            if (
                not raw_length.isascii()
                or not raw_length.isdecimal()
                or len(raw_length) > 3
            ):
                raise ValueError("Введите целую длину от 4 до 128.")
            options = GenerationOptions(
                length=int(raw_length), lowercase=self.lowercase.get(),
                uppercase=self.uppercase.get(), digits=self.digits.get(),
                special=self.special.get(),
            )
            password = generate_password(options)
        except ValueError as error:
            self.status.set(str(error))
            return
        self.password.set(password)
        # Автоматически оцениваем результат. Подробности доступны во второй
        # вкладке, которую затем можно использовать для произвольного ввода.
        self.show_manual_password.set(False)
        self._toggle_manual_visibility()
        self.manual_password.set(password)
        self._assess_manual()
        self.generated_assessment.set(
            f"Оценка: {self.assessment_title.get()}. "
            "Учебная эвристика; подробности во вкладке оценки."
        )
        self.copy_button.state(["!disabled"])
        self.status.set("Пароль создан. Он не сохранён в файл.")

    def _toggle_visibility(self) -> None:
        """Показать или скрыть результат без изменения самого пароля."""
        self.password_input.configure(
            show="" if self.show_password.get() else "*"
        )

    def _copy_password(self) -> None:
        """Скопировать пароль по запросу, обработав возможную ошибку Tkinter.

        Ничего не возвращает. В строку состояния секрет не включается.
        Буфер обмена автоматически не очищается и доступен другим программам.
        """
        if not self.password.get():
            self.status.set("Сначала сгенерируйте пароль.")
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(self.password.get())
        except tk.TclError:
            self.status.set("Не удалось скопировать пароль в буфер обмена.")
            return
        self.status.set(
            "Пароль скопирован. Буфер доступен другим приложениям."
        )

    def _clear_secrets(self) -> None:
        """Очистить пароли и оценки после закрытия или смены хранилища.

        Системный буфер обмена не изменяется: он может содержать чужие данные.
        Строки Python могут сохраняться в памяти до освобождения сборщиком.
        """
        self.password.set("")
        self.manual_password.set("")
        self.generated_assessment.set("")
        self.assessment_title.set("Введите пароль для оценки.")
        self._set_assessment_details("")
        self.show_password.set(False)
        self.show_manual_password.set(False)
        self._toggle_visibility()
        self._toggle_manual_visibility()
        self.copy_button.state(["disabled"])

    def _close(self) -> None:
        """Закрыть окно с очисткой сеанса, если файловая операция закончилась.

        Во время записи только показываем сообщение: пользователь сможет
        повторить закрытие после её окончания. Автозакрытия по таймеру нет.
        """
        if self.storage.busy:
            self.status.set("Дождитесь окончания операции перед закрытием.")
            return
        self.storage.lock()
        self.destroy()
