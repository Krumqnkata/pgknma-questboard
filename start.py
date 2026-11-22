"""
Пуска цялата система с една команда:

    python start.py               # за разработка (сървърът се рестартира при промяна на кода)
    python start.py --production  # за публикуване (waitress, подготвени статични файлове)

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
PRODUCTION = "--production" in sys.argv


def load_env():
    if not ENV_FILE.exists():
        sys.exit("Липсва файлът .env. Копирайте .env.example като .env и попълнете стойностите.")
    from dotenv import load_dotenv

    load_dotenv(ENV_FILE)


def manage(*args):
    """Изпълнява команда на Django и спира, ако тя е неуспешна."""
    if subprocess.run([sys.executable, "manage.py", *args], cwd=ROOT / "backend").returncode != 0:
        sys.exit(f"Командата „manage.py {' '.join(args)}“ е неуспешна.")


def prepare_production():
    """Преди публикуване: проверка на настройките, миграции на базата и статични файлове."""
    if os.getenv("DJANGO_DEBUG", "").lower() in ("1", "true", "yes", "on"):
        sys.exit("За --production сложете DJANGO_DEBUG=False в .env.")
    print("Подготовка за публикуване...")
    manage("migrate", "--noinput")
    manage("collectstatic", "--noinput", "--verbosity", "0")
    manage("check", "--deploy")


def proxy_args():
    """
    Зад прокси сървър (Apache, nginx) на същата машина: waitress приема от него
    истинския адрес на потребителя и дали връзката е по HTTPS. Без тези флагове
    waitress маха заглавките X-Forwarded-* и всички потребители изглеждат като
    127.0.0.1 – тогава защитата на входа би заключила всички наведнъж.
    Вярваме само на един прокси и само на 127.0.0.1, за да не може някой отвън
    да подправи адреса си.
    """
    if os.getenv("DJANGO_BEHIND_PROXY", "").lower() not in ("1", "true", "yes", "on"):
        return []
    return ["--trusted-proxy=127.0.0.1", "--trusted-proxy-count=1",
            "--trusted-proxy-headers=x-forwarded-for x-forwarded-proto"]


def start_django():
    host = os.getenv("DJANGO_HOST", "127.0.0.1")
    port = os.getenv("DJANGO_PORT", "8000")
    print(f"→ Questboard:  http://{host}:{port}")
    if PRODUCTION:
        # waitress – сървър за реална работа, работи и под Windows, и под Linux
        # --max-request-body-size: заявка над 64 MB се спира още в сървъра (качените файлове са много по-малки)
        command = [sys.executable, "-m", "waitress", f"--listen={host}:{port}", "--threads=8",
                   "--max-request-body-size=67108864", *proxy_args(),
                   "questboard.wsgi:application"]
    else:
        command = [sys.executable, "manage.py", "runserver", f"{host}:{port}"]
    return subprocess.Popen(command, cwd=ROOT / "backend")


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
    if PRODUCTION:
        prepare_production()
    django = start_django()
    assistant = start_assistant()
    assistant_reported = False
    print("Спиране: Ctrl+C\n")

    crashed = False
    try:
        while True:
            if django.poll() is not None:
                print("\nОсновното API спря – спирам и асистента.")
                crashed = True
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
    if crashed:
        # Код за грешка – така systemd (Restart=on-failure) пуска системата отново.
        sys.exit(1)


if __name__ == "__main__":
    main()
