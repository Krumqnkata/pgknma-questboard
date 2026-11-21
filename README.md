# Questboard

Уеб платформа, която превръща участието в училищния живот в игра. Учителите
пускат мисии, учениците ги изпълняват и получават XP, нива и монети, а с
монетите купуват привилегии. Вграденият асистент дава подсказки, помага на
учителите да съставят мисии и отговаря на справки по разписанието.

## Архитектура

Системата е от отделни части, които общуват по мрежата:

```
Браузър ──HTTP──▶ Основно API (Django) ──SQL──▶ База данни (SQLite / MySQL)
                        │
                        └──HTTP + таен ключ──▶ Асистент (FastAPI) ──HTTPS──▶ Езиков модел
```

- **Основно API (Django + Django REST Framework)**: страниците за ученици и
  учители, REST API-то и всички правила на играта. Само то пише в базата.
- **Асистент (FastAPI)**: отделна програма. Ключът за езиковия модел стои
  само тук. Приема заявки само от Django и слуша само на `127.0.0.1`.
- Ако асистентът е спрян, платформата продължава да работи без него.

## Структура на папките

```
backend/                Основно API (Django)
  questboard/           настройки и главни адреси
  accounts/             потребители, роли, класове, гилдии
  missions/             мисии и заявки
  economy/              XP, монети, нива, магазин, настройки на играта
  timetable/            разписание: часове, предмети, кабинети
  assistant_bridge/     връзка с асистента и журнал на ползването
  api/                  REST API (JSON)
  web/                  страниците (Django шаблони)
  templates/, static/   HTML шаблони и CSS
assistant_service/      Услуга на асистента (FastAPI)
start.py                пуска цялата система с една команда
run_tests.py            пуска всички тестове с една команда
.env.example            пример за файла с тайните и портовете
```

## Инсталиране (Windows, PowerShell)

Нужен е Python 3.12 или по-нов.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Отворете `.env` и сменете `DJANGO_SECRET_KEY` и `ASSISTANT_TOKEN` с дълги
случайни низове. Случаен низ се прави така:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

После създайте базата и първия администратор:

```powershell
cd backend
python manage.py migrate
python manage.py createsuperuser
cd ..
```

За MySQL вместо SQLite: `pip install -r backend/requirements-mysql.txt` и
`DB_ENGINE=mysql` с данните за базата в `.env`.

## Стартиране

```powershell
python start.py
```

- Questboard: http://127.0.0.1:8000
- Администрация: http://127.0.0.1:8000/admin/
- Документация на API-то: http://127.0.0.1:8000/api/docs/

Спиране: **Ctrl+C**. Портовете се сменят от `.env` (`DJANGO_PORT`, `ASSISTANT_PORT`).

## Тестове

```powershell
python run_tests.py
```

Тестовете се пускат автоматично и в GitHub Actions при всяко качване.

## Настройки: какво къде е

| В Django admin („Настройки на играта“) | Във файла `.env` |
|---|---|
| курс XP към монети, седмичен лимит, пренасяне на остатъка | портове и адрес на асистента |
| най-много XP за мисия, граници на нивата | връзка с базата данни |
| цени на привилегиите | `DJANGO_SECRET_KEY`, `ASSISTANT_TOKEN` |
| асистентът включен/изключен, доставчик и модел, лимит на заявките | ключовете за езиковите модели |

В `.env` са само стойностите, нужни при стартиране, и тайните. Файлът не се
качва в GitHub.
