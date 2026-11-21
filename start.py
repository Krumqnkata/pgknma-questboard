"""
Пуска цялата система с една команда:

    python start.py

Стартира две отделни програми:
  1. основното API и страниците (Django)
  2. услугата на асистента (FastAPI)

Портовете се четат от .env. Спиране – с Ctrl+C.
Ако асистентът спре, платформата продължава да работи без него.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"


def load_env():
    if not ENV_FILE.exists():
        sys.exit("Липсва файлът .env. Копирайте .env.example като .env и попълнете стойностите.")
    from dotenv import load_dotenv

    load_dotenv(ENV_FILE)


def start_django():
    host = os.getenv("DJANGO_HOST", "127.0.0.1")
    port = os.getenv("DJANGO_PORT", "8000")
    print(f"→ Questboard:  http://{host}:{port}")
    return subprocess.Popen(
        [sys.executable, "manage.py", "runserver", f"{host}:{port}"],
        cwd=ROOT / "backend",
    )


def start_assistant():
    # Асистентът слуша само на 127.0.0.1 – отвън не може да се стигне до него.
    port = os.getenv("ASSISTANT_PORT", "8001")
    print(f"→ Асистент:    http://127.0.0.1:{port}  (достъпен само за Django)")
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", port],
        cwd=ROOT / "assistant_service",
    )


def stop(process):
    """Спира програма заедно с дъщерните ѝ процеси."""
    if process.poll() is not None:
        return
    if os.name == "nt":
        # В Windows runserver пуска втори процес, затова спираме цялото дърво.
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True)
    else:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def main():
    # Съобщенията да излизат веднага, а не накуп при спиране.
    sys.stdout.reconfigure(line_buffering=True)
    load_env()
    django = start_django()
    assistant = start_assistant()
    assistant_reported = False
    print("Спиране: Ctrl+C\n")

    try:
        while True:
            if django.poll() is not None:
                print("\nОсновното API спря – спирам и асистента.")
                break
            if assistant.poll() is not None and not assistant_reported:
                print("\nВНИМАНИЕ: асистентът спря. Платформата продължава да работи без него.")
                assistant_reported = True
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nСпирам системата...")
    finally:
        stop(django)
        stop(assistant)


if __name__ == "__main__":
    main()
