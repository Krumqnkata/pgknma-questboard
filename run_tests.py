"""
Пуска всички автоматични тестове с една команда:

    python run_tests.py

Същото се пуска и в GitHub Actions при всяко качване.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

STEPS = [
    ("Проверка за липсващи миграции",
     [sys.executable, "manage.py", "makemigrations", "--check", "--dry-run"], ROOT / "backend"),
    ("Проверка на документацията на API-то",
     [sys.executable, "manage.py", "spectacular", "--file", os.devnull, "--fail-on-warn"], ROOT / "backend"),
    ("Тестове на основното API (Django)",
     [sys.executable, "manage.py", "test"], ROOT / "backend"),
    ("Тестове на асистента (FastAPI)",
     [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."], ROOT / "assistant_service"),
]


def main():
    failed = []
    for title, command, folder in STEPS:
        print(f"\n=== {title} ===", flush=True)
        if subprocess.run(command, cwd=folder).returncode != 0:
            failed.append(title)

    if failed:
        print("\nНЕУСПЕШНИ: " + "; ".join(failed))
        sys.exit(1)
    print("\nВсички тестове минаха успешно.")


if __name__ == "__main__":
    main()
