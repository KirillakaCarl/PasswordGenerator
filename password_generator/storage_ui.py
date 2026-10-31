"""Вкладка хранилища: диалоги Tkinter и фоновые файловые операции.

Рабочий поток не обращается к виджетам. Он кладёт результат в Queue,
которую основной поток проверяет через after. В каждый момент работает
только одна операция; повторные действия до её окончания недоступны.
"""

from collections.abc import Callable
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from password_generator.encryption import validate_master_password
from password_generator.storage import VaultSession


class StorageFrame(ttk.Frame):
    """Вкладка одного хранилища с доступом к паролям соседних вкладок."""

    def __init__(
        self, parent: ttk.Notebook, generated: Callable[[], str],
        manual: Callable[[], str], clear_secrets: Callable[[], None],
        status: tk.StringVar,
    ) -> None:
        """Сохранить функции чтения/очистки и построить вкладку.

        generated/manual читаются только в основном потоке при сохранении.
        clear_secrets очищает секреты других вкладок при блокировке.
        status — общая строка состояния. Возвращаемого значения нет.
        """
        super().__init__(parent, padding=12)
        self._generated = generated
        self._manual = manual
        self._clear_secrets = clear_secrets
        self._status = status
        self.session = None
        self.busy = False
        self._results = Queue()
        self._on_success = None
        self._controls = []
        self.title_input = tk.StringVar(self)
        self.source = tk.StringVar(self, value="Сгенерированный пароль")
        self.selected_password = tk.StringVar(self)
        self.revealed = tk.BooleanVar(self, value=False)
        self.vault_status = tk.StringVar(
            self, value="Хранилище закрыто."
        )
        self._build()
        self._refresh()

    def _button(
        self, parent: ttk.Frame, text: str, command: Callable, column: int,
    ) -> ttk.Button:
        """Создать кнопку, учитываемую при блокировке на время записи."""
        button = ttk.Button(parent, text=text, command=command)
        button.grid(row=0, column=column, padx=(0, 6), pady=4)
        self._controls.append(button)
        return button

    def _build(self) -> None:
        """Создать кнопки, список и форму; файловые операции не запускать."""
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        toolbar = ttk.Frame(self)
        toolbar.grid(row=0, column=0, sticky="w")
        self.create_button = self._button(toolbar, "Создать", self._create, 0)
        self.open_button = self._button(toolbar, "Открыть", self._open, 1)
        self.lock_button = self._button(
            toolbar, "Закрыть хранилище", self.lock, 2
        )
        ttk.Label(
            self, textvariable=self.vault_status, wraplength=480
        ).grid(row=1, column=0, sticky="w", pady=6)

        listing = ttk.Frame(self)
        listing.grid(row=2, column=0, sticky="nsew")
        listing.columnconfigure(0, weight=1)
        listing.rowconfigure(0, weight=1)
        self.records = ttk.Treeview(
            listing, columns=("title",), show="headings", height=4,
            selectmode="browse",
        )
        self.records.heading("title", text="Сохранённые записи")
        self.records.column("title", width=250, minwidth=100)
        self.records.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(
            listing, orient="vertical", command=self.records.yview
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.records.configure(yscrollcommand=scrollbar.set)
        self.records.bind("<<TreeviewSelect>>", self._selection_changed)

        selected = ttk.Frame(self)
        selected.grid(row=3, column=0, sticky="ew", pady=6)
        selected.columnconfigure(0, weight=1)
        self.secret_field = ttk.Entry(
            selected, textvariable=self.selected_password,
            state="readonly", show="*",
        )
        self.secret_field.grid(row=0, column=0, sticky="ew")
        self.show_button = ttk.Checkbutton(
            selected, text="Показать", variable=self.revealed,
            command=self._show_selected,
        )
        self.show_button.grid(row=0, column=1, padx=6)
        self._controls.append(self.show_button)
        self.delete_button = self._button(
            selected, "Удалить", self._delete, 2
        )

        form = ttk.LabelFrame(self, text="Сохранить новую запись", padding=8)
        form.grid(row=4, column=0, sticky="ew", pady=6)
        form.columnconfigure(1, weight=1)
        ttk.Label(form, text="Название:").grid(row=0, column=0, sticky="w")
        self.name_field = ttk.Entry(form, textvariable=self.title_input)
        self.name_field.grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Label(form, text="Источник:").grid(row=1, column=0, sticky="w")
        self.source_field = ttk.Combobox(
            form, textvariable=self.source, state="readonly",
            values=("Сгенерированный пароль", "Пароль из оценки"),
        )
        self.source_field.grid(row=1, column=1, sticky="ew", padx=6, pady=6)
        self.save_button = ttk.Button(
            form, text="Сохранить", command=self._save
        )
        self.save_button.grid(row=2, column=1, sticky="e", padx=6)
        self._controls.extend((self.name_field, self.save_button))
        ttk.Label(
            self,
            text="При закрытии пароли скрываются, поля очищаются.\n"
            "Для открытия нужен мастер-пароль. Восстановления нет.",
            wraplength=480,
        ).grid(row=5, column=0, sticky="w", pady=(4, 0))

    def _refresh(self) -> None:
        """Обновить список и доступность действий после операции."""
        self.selected_password.set("")
        self.revealed.set(False)
        self.secret_field.configure(show="*")
        children = self.records.get_children()
        if children:
            self.records.delete(*children)
        if self.session is not None:
            for entry in self.session.entries:
                self.records.insert(
                    "", "end", iid=entry.identifier, values=(entry.title,)
                )
        for control in self._controls:
            control.state(["!disabled"])
        self.source_field.configure(state="readonly")
        if self.session is None:
            for control in (
                self.lock_button, self.save_button, self.name_field,
            ):
                control.state(["disabled"])
            self.source_field.configure(state="disabled")
        else:
            # Для смены файла сначала блокируем текущий сеанс. Это исключает
            # смешение записей разных хранилищ и сохраняет простой сценарий.
            self.create_button.state(["disabled"])
            self.open_button.state(["disabled"])
        self.delete_button.state(["disabled"])
        self.show_button.state(["disabled"])

    def _selection_changed(self, _event=None) -> None:
        """Скрыть прошлый секрет при выборе записи; событие даёт Tkinter."""
        self.selected_password.set("")
        self.revealed.set(False)
        self.secret_field.configure(show="*")
        enabled = bool(self.records.selection()) and not self.busy
        for control in (self.show_button, self.delete_button):
            control.state(["!disabled"] if enabled else ["disabled"])

    def _show_selected(self) -> None:
        """Загрузить пароль выбранной записи только после явного действия."""
        selection = self.records.selection()
        if self.session is None or self.busy or not selection:
            return
        if self.revealed.get():
            entry = next(
                e for e in self.session.entries if e.identifier == selection[0]
            )
            self.selected_password.set(entry.password)
            self.secret_field.configure(show="")
        else:
            self.selected_password.set("")
            self.secret_field.configure(show="*")

    def _ask_master(self, *, confirm: bool) -> str | None:
        """Запросить скрытый мастер-пароль и при создании его повторение.

        При отмене возвращает None. Проверка не удаляет пробелы; ошибки
        показываются отдельным предупреждением без включения самого пароля.
        После ошибки повторяем ввод, сохраняя уже выбранное имя файла.
        """
        action = "создано" if confirm else "открыто"
        cancelled = "Создание" if confirm else "Открытие"
        while True:
            password = simpledialog.askstring(
                "Мастер-пароль", "Введите мастер-пароль (12–1024 символа):",
                show="*", parent=self,
            )
            if password is None:
                self._status.set(f"{cancelled} хранилища отменено.")
                return None
            try:
                validate_master_password(password)
            except ValueError as error:
                summary = (
                    f"Хранилище не {action}: требования к мастер-паролю "
                    "не соблюдены."
                )
                self._status.set(summary)
                messagebox.showwarning(
                    "Требования к мастер-паролю",
                    f"{summary}\n\nПричина: {error}\n\n"
                    "Требования:\n"
                    "• Длина от 12 до 1024 символов включительно.\n"
                    "• Разрешены буквы, цифры, пробелы "
                    "и специальные символы.\n"
                    "• Пробелы считаются частью пароля.\n\n"
                    "Попробуйте ввести мастер-пароль ещё раз.",
                    parent=self,
                )
                continue
            if confirm:
                repeated = simpledialog.askstring(
                    "Подтверждение",
                    "Повторите мастер-пароль. Восстановления пароля нет.",
                    show="*", parent=self,
                )
                if repeated is None:
                    self._status.set("Создание хранилища отменено.")
                    return None
                if password != repeated:
                    summary = (
                        "Хранилище не создано: мастер-пароли не совпадают."
                    )
                    self._status.set(summary)
                    messagebox.showwarning(
                        "Подтверждение мастер-пароля",
                        f"{summary}\n\nВведите мастер-пароль и повторите его "
                        "ещё раз. Учитываются регистр и пробелы.",
                        parent=self,
                    )
                    continue
            return password

    def _create(self) -> None:
        """Выбрать новое имя и запустить создание в рабочем потоке."""
        if self.busy or self.session is not None:
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="Новое зашифрованное хранилище",
            defaultextension=".vault",
            filetypes=[("Хранилище паролей", "*.vault")],
        )
        if not path:
            return
        password = self._ask_master(confirm=True)
        if password is not None:
            self._start(
                lambda: VaultSession.create(Path(path), password),
                self._opened,
            )

    def _open(self) -> None:
        """Выбрать файл и запустить проверку/расшифрование в рабочем потоке."""
        if self.busy or self.session is not None:
            return
        path = filedialog.askopenfilename(
            parent=self, title="Открыть зашифрованное хранилище",
            filetypes=[("Хранилище паролей", "*.vault"), ("Все файлы", "*.*")],
        )
        if not path:
            return
        password = self._ask_master(confirm=False)
        if password is not None:
            self._start(
                lambda: VaultSession.open(Path(path), password), self._opened
            )

    def _opened(self, session: VaultSession) -> None:
        """Принять готовый сеанс в основном потоке и убрать название формы."""
        self.session = session
        self.title_input.set("")
        self.vault_status.set("Хранилище открыто. Записи сохраняются сразу.")
        self._status.set("Хранилище открыто.")

    def _save(self) -> None:
        """Снять значения формы и сохранить выбранный источник в фоне."""
        if self.busy or self.session is None:
            return
        title = self.title_input.get()
        password = (
            self._generated() if self.source.get() == "Сгенерированный пароль"
            else self._manual()
        )
        self._start(lambda: self.session.add(title, password), self._saved)

    def _saved(self, _entry) -> None:
        """Показать успех только после успешной записи файла."""
        self.title_input.set("")
        self._status.set("Запись сохранена в зашифрованном виде.")

    def _delete(self) -> None:
        """Удалить выбранный ID после подтверждения без раскрытия секрета."""
        selection = self.records.selection()
        if self.busy or self.session is None or not selection:
            return
        if messagebox.askyesno(
            "Удаление записи",
            "Удалить выбранную запись без возможности отмены?",
            parent=self,
        ):
            self._start(
                lambda: self.session.delete(selection[0]),
                lambda _result: self._status.set("Запись удалена."),
            )

    def lock(self) -> None:
        """Закрыть сеанс и очистить секреты; при busy дождаться записи."""
        if self.busy:
            self._status.set("Дождитесь окончания операции хранилища.")
            return
        if self.session is not None:
            self.session.lock()
        self.session = None
        self.title_input.set("")
        self._clear_secrets()
        self.vault_status.set("Хранилище закрыто.")
        self._status.set(
            "Хранилище закрыто. Для открытия нужен мастер-пароль."
        )
        self._refresh()

    def _start(self, operation: Callable, on_success: Callable) -> None:
        """Запустить одну операцию без передачи Tkinter в рабочий поток."""
        if self.busy:
            return
        self.busy = True
        self._on_success = on_success
        self._selection_changed()
        for control in self._controls:
            control.state(["disabled"])
        self.source_field.configure(state="disabled")
        self._status.set("Выполняется операция хранилища…")

        def work() -> None:
            """Положить в очередь результат или безопасное сообщение ошибки."""
            try:
                result = operation()
            except FileExistsError:
                self._results.put((
                    False, "Файл уже существует. Выберите новое имя."
                ))
            except ValueError as error:
                self._results.put((False, str(error)))
            except OSError:
                self._results.put((
                    False, "Не удалось прочитать или записать файл."
                ))
            except Exception:
                # Не выводим repr исключения: он может включать входные данные.
                self._results.put((
                    False, "Не удалось выполнить операцию хранилища."
                ))
            else:
                self._results.put((True, result))

        Thread(target=work, daemon=True).start()
        self.after(50, self._poll)

    def _poll(self) -> None:
        """Проверить очередь и обновить виджеты в основном потоке."""
        try:
            success, result = self._results.get_nowait()
        except Empty:
            self.after(50, self._poll)
            return
        self.busy = False
        callback = self._on_success
        self._on_success = None
        if success:
            callback(result)
        else:
            self._status.set(result)
        self._refresh()
