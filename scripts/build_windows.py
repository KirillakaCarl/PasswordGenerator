"""Воспроизводимая команда сборки самостоятельного Windows x64 приложения.

Запускать Python из окружения с requirements.txt и requirements-build.txt.
PyInstaller включает интерпретатор, Tcl/Tk и зависимости в exe. Хранилища,
tests и временные материалы в сборку не добавляются.
"""

from datetime import datetime, timezone
import hashlib
from importlib.metadata import distribution, version
import json
from pathlib import Path
import platform
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from password_generator import __version__  # noqa: E402


def build() -> None:
    """Собрать exe, метаданные, контрольную сумму и переносной ZIP.

    Пишет только в build/ и dist/ внутри проекта. При ошибке сборщика
    subprocess.run вызывает CalledProcessError и успешный архив не создаётся.
    """
    if sys.platform != "win32" or platform.machine().lower() not in (
        "amd64", "x86_64",
    ):
        raise RuntimeError("Эта команда предназначена для Windows x64.")
    output = ROOT / "dist"
    work = ROOT / "build"
    output.mkdir(exist_ok=True)
    work.mkdir(exist_ok=True)
    name = f"PasswordGenerator-{__version__}-windows-x64"
    # Ресурс Windows берёт ту же версию, что и заголовок окна приложения.
    numbers = tuple(int(part) for part in __version__.split(".")) + (0,)
    version_file = work / "windows-version.txt"
    version_file.write_text(
        "VSVersionInfo(ffi=FixedFileInfo(filevers=" + repr(numbers)
        + ", prodvers=" + repr(numbers) + ", mask=0x3f, flags=0, OS=0x40004, "
        "fileType=0x1, subtype=0, date=(0,0)), kids=[StringFileInfo(["
        "StringTable('040904B0', [StringStruct('FileDescription', "
        "'PasswordGenerator'), "
        "StringStruct('ProductName', 'PasswordGenerator'),"
        f" StringStruct('FileVersion', '{__version__}'),"
        f" StringStruct('ProductVersion', '{__version__}')])]),"
        " VarFileInfo([VarStruct('Translation', [1033,1200])])])",
        encoding="utf-8",
    )
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile",
        "--windowed", "--noupx", "--name", name,
        "--distpath", str(output), "--workpath", str(work / "pyinstaller"),
        "--specpath", str(work), "--version-file", str(version_file),
        str(ROOT / "main.py"),
    ], cwd=ROOT, check=True)
    executable = output / f"{name}.exe"
    checksum = hashlib.sha256(executable.read_bytes()).hexdigest()
    inputs = [
        ROOT / "main.py", *sorted((ROOT / "password_generator").glob("*.py")),
        ROOT / "requirements.txt", ROOT / "requirements-build.txt",
        Path(__file__),
    ]
    metadata = {
        "version": __version__, "platform": "Windows x64",
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(), "exe_sha256": checksum,
        "packages": {p: version(p) for p in (
            "cryptography", "cffi", "pycparser", "PyInstaller",
            "pyinstaller-hooks-contrib",
        )},
        "source_sha256": {
            p.relative_to(ROOT).as_posix():
            hashlib.sha256(p.read_bytes()).hexdigest()
            for p in inputs
        },
    }
    (output / "BUILD_INFO.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "SHA256SUMS.txt").write_text(
        f"{checksum}  {executable.name}\n", encoding="ascii"
    )
    quick_start = output / "START_HERE.txt"
    quick_start.write_text(
        f"PasswordGenerator {__version__} / Windows x64\n\n"
        "Запустите exe двойным щелчком. Установка Python не нужна.\n"
        "Храните файлы .vault отдельно от программы.\n"
        "Мастер-пароль: 12–1024 символа. Восстановления пароля нет.\n"
        "Создайте хранилище, сгенерируйте пароль и сохраните запись.\n"
        "Дата в таблице означает дату сохранения записи.\n"
        "Поиск работает по названию, сортировка — по названию и дате.\n"
        "Закрытие хранилища очищает поля. Буфер обмена не очищается.\n"
        "Не открывайте один файл для записи из нескольких экземпляров.\n",
        encoding="utf-8-sig",
    )
    # Передаём тексты лицензий включённых компонентов вместе с программой.
    # В этой установке Python лицензии Tcl/Tk находятся внутри ZIP-библиотек.
    license_dir = output / "THIRD_PARTY_LICENSES"
    license_dir.mkdir(exist_ok=True)
    license_files = []
    for package in ("cryptography", "cffi", "pycparser", "pyinstaller"):
        installed = distribution(package)
        for file in installed.files or ():
            if "/licenses/" in str(file).replace("\\", "/"):
                target = license_dir / f"{package}-{Path(file).name}"
                source = Path(installed.locate_file(file))
                target.write_bytes(source.read_bytes())
                license_files.append(target)
    python_license = license_dir / "Python-LICENSE.txt"
    python_license.write_bytes(
        (Path(sys.base_prefix) / "LICENSE.txt").read_bytes()
    )
    license_files.append(python_license)
    for library in (Path(sys.base_prefix) / "tcl").glob("*.zip"):
        with zipfile.ZipFile(library) as archive:
            for member in archive.namelist():
                if member.endswith("/license.terms"):
                    target = license_dir / f"{library.stem}-license.terms"
                    target.write_bytes(archive.read(member))
                    license_files.append(target)
    with zipfile.ZipFile(
        output / f"{name}.zip", "w", zipfile.ZIP_DEFLATED
    ) as bundle:
        for path in (executable, quick_start, output / "BUILD_INFO.json",
                     output / "SHA256SUMS.txt"):
            bundle.write(path, arcname=path.name)
        for path in license_files:
            bundle.write(path, arcname=path.relative_to(output).as_posix())
    print(f"Готово: {executable}")


if __name__ == "__main__":
    build()
