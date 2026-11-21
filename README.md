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

Примерни данни (класове, мисии и тестов акаунт за всяка роля, само с
измислени хора) се зареждат така, след като сложите `DEMO_PASSWORD` в `.env`:

```powershell
cd backend
python manage.py seed_demo
cd ..
```

Тестовите акаунти са `admin@questboard.test`, `uchitel@questboard.test` и
`uchenik@questboard.test` до `uchenik4@questboard.test`.

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

## Лиценз

Questboard се разпространява под лиценза GNU General Public License,
версия 3 (GPL-3.0). Пълният текст е във файла [LICENSE](LICENSE).

## Използвани библиотеки

| Библиотека | За какво се ползва | Лиценз |
|---|---|---|
| [Django](https://www.djangoproject.com/) | основното API, страниците, администрацията | BSD-3-Clause |
| [Django REST Framework](https://www.django-rest-framework.org/) | REST API | BSD-3-Clause |
| [drf-spectacular](https://github.com/tfranzel/drf-spectacular) | автоматична документация на API-то | BSD-3-Clause |
| [django-unfold](https://github.com/unfoldadmin/django-unfold) | тема на администрацията | MIT |
| [FastAPI](https://fastapi.tiangolo.com/) | услугата на асистента | MIT |
| [Uvicorn](https://www.uvicorn.org/) | сървър за услугата на асистента | BSD-3-Clause |
| [HTTPX](https://www.python-httpx.org/) | заявки от Django към асистента | BSD-3-Clause |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | четене на файла `.env` | BSD-3-Clause |
| [mysqlclient](https://github.com/PyMySQL/mysqlclient) | връзка с MySQL (по избор) | GPL-2.0-or-later |
| [Material Symbols](https://fonts.google.com/icons) | иконите в администрацията (идват с django-unfold) | Apache-2.0 |
| [Inter](https://rsms.me/inter/) | шрифтът на администрацията (идва с django-unfold) | SIL OFL 1.1 |

django-unfold включва и свои JavaScript библиотеки (Alpine.js, htmx, Chart.js
и др.). Лицензите им са в пакета на django-unfold.
