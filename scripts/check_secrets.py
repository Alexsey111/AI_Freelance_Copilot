"""Скан дерева на секреты перед коммитом (ТЗ §30: ключи не попадают в Git).

Две независимые проверки:

1. **Ключи внутри файлов** — регулярки по всем файлам дерева. Заготовки, плейсхолдеры и
   чтение из окружения не считаются находкой.
2. **Игнорируемые файлы** — то, что лежит в рабочем каталоге, но не попадает в Git
   (`.gitignore`), и при этом содержит секреты. Такой файл безопасен для репозитория, но
   проверку он не должен «заваливать»: это нормальное рабочее окружение разработчика.

Именно поэтому `.env` с реальным ключом даёт предупреждение, а не ошибку. Ошибка (код 1) —
только то, что действительно может уехать в репозиторий: ключ в отслеживаемом файле или
файл с ключом, который Git не игнорирует.

Запуск: ./.venv/Scripts/python.exe scripts/check_secrets.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {".venv", ".git", "__pycache__", ".pytest_cache", ".ruff_cache", "node_modules"}
SKIP_FILES = {".env.example", "check_secrets.py"}
SKIP_SUFFIXES = {".db", ".sqlite", ".png", ".jpg", ".jpeg", ".pdf", ".ico", ".woff", ".woff2"}

PATTERNS = [
    ("OpenAI-ключ", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("ключ Anthropic", re.compile(r"sk-ant-[A-Za-z0-9\-_]{20,}")),
    ("Telegram bot token", re.compile(r"\b\d{8,10}:[A-Za-z0-9_\-]{35}\b")),
    ("GitHub token", re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}")),
    ("ключ proxyapi", re.compile(r"\bsk-[A-Za-z0-9]{16,}")),
    ("присвоение ключа в коде", re.compile(r"(?i)\b(api[_-]?key|secret|token)\s*[:=]\s*[\"']([A-Za-z0-9\-_]{24,})[\"']")),
]

ALLOWED_HINTS = ("example", "sample", "your", "замените", "placeholder", "os.getenv", "settings.")


def iter_files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.name in SKIP_FILES or path.suffix.lower() in SKIP_SUFFIXES:
            continue
        yield path


def scan_file(path: Path) -> list[tuple[int, str]]:
    """Найти фрагменты, похожие на секреты, в одном файле."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    found: list[tuple[int, str]] = []
    for label, pattern in PATTERNS:
        for match in pattern.finditer(text):
            if any(hint in match.group(0).lower() for hint in ALLOWED_HINTS):
                continue
            found.append((text[: match.start()].count("\n") + 1, label))
    return found


def git(*args: str) -> tuple[int, str]:
    """Вызвать git и вернуть код возврата и вывод (пустой вывод при отсутствии git)."""
    try:
        completed = subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return 128, ""
    return completed.returncode, completed.stdout.strip()


def is_repository() -> bool:
    return git("rev-parse", "--is-inside-work-tree")[0] == 0


def is_ignored(relative: str) -> bool:
    return git("check-ignore", "-q", relative)[0] == 0


def is_tracked(relative: str) -> bool:
    return git("ls-files", "--error-unmatch", relative)[0] == 0


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    checked = 0
    repository = is_repository()

    for path in iter_files():
        checked += 1
        relative = str(path.relative_to(ROOT)).replace("\\", "/")
        for line, label in scan_file(path):
            ignored = repository and is_ignored(relative)
            where = f"{relative}:{line} — похоже на {label}"
            in_repo = repository and is_tracked(relative)
            if ignored and not in_repo:
                warnings.append(f"{where} (файл игнорируется Git — в репозиторий не попадёт)")
            else:
                errors.append(where)

        if path.name == ".env":
            if not repository:
                warnings.append(f"{relative} — рабочий файл с ключами (git ещё не инициализирован)")
            elif is_ignored(relative) and not is_tracked(relative):
                warnings.append(f"{relative} — рабочий файл с ключами, Git его игнорирует (это норма)")
            else:
                errors.append(f"{relative} — файл с секретами НЕ игнорируется Git: это утечка")

    if warnings:
        print("Предупреждения (безопасно, но знайте):")
        for item in warnings:
            print("  ", item)

    if errors:
        print("\nОШИБКИ — это может уехать в репозиторий:")
        for item in errors:
            print("  ", item)
        print("\nУберите ключ из отслеживаемого файла, добавьте файл в .gitignore")
        print("и, если ключ уже попал в коммит, отзовите его у провайдера.")
        return 1

    print(f"\nВ репозиторий секреты не уезжают. Проверено файлов: {checked}")
    if not repository:
        print("Примечание: Git ещё не инициализирован, проверка выполнена только по содержимому.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
