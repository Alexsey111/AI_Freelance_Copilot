"""Скан дерева на секреты перед коммитом (ТЗ §30: ключи не попадают в Git).

Запуск: ./.venv/Scripts/python.exe scripts/check_secrets.py
Возвращает код 1 и список файлов, если что-то похоже на реальный ключ.
"""

from __future__ import annotations

import re
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
    ("присвоение ключа в коде", re.compile(r"(?i)\b(api[_-]?key|secret|token)\s*[:=]\s*[\"\']([A-Za-z0-9\-_]{24,})[\"\']")),
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


def main() -> int:
    findings: list[str] = []
    for path in iter_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for label, pattern in PATTERNS:
            for match in pattern.finditer(text):
                fragment = match.group(0)
                lowered = fragment.lower()
                if any(hint in lowered for hint in ALLOWED_HINTS):
                    continue
                line = text[: match.start()].count("\n") + 1
                findings.append(f"{path.relative_to(ROOT)}:{line} — похоже на {label}")
        # Файл .env не должен существовать в репозитории.
        if path.name == ".env":
            findings.append(f"{path.relative_to(ROOT)} — файл с секретами не должен лежать в репозитории")

    if not findings:
        print("Секретов не найдено. Проверено файлов:", sum(1 for _ in iter_files()))
        return 0
    print("Найдены подозрительные места:")
    for item in findings:
        print("  ", item)
    return 1


if __name__ == "__main__":
    sys.exit(main())
