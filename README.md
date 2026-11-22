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

- **Уеб клиент (браузърът)**: страниците се генерират от Django шаблони (HTML
  и CSS). Чатът с асистента е на обикновен JavaScript и говори с REST API-то.
- **Основно API (Django + Django REST Framework)**: страниците, REST API-то и
  всички правила на играта. Само то пише в базата и проверява правата.
- **Асистент (FastAPI)**: отделна програма. Ключовете за езиковите модели
  стоят само тук. Приема заявки само от Django и слуша само на `127.0.0.1`.
  Не чете базата: Django му праща само нужните данни, без лични данни на ученици.
- Ако асистентът е спрян или изключен от администрацията, платформата
  продължава да работи без него.

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
  main.py               адресите: /hint, /mission-draft, /query/plan, /query/answer
  logic.py              подготовка на заявките към модела и проверка на отговорите
  prompts.py            инструкциите към модела
  providers/            OpenAI, Gemini и Claude зад общ интерфейс
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

Примерни данни (класове, мисии, разписание и тестов акаунт за всяка роля,
само с измислени хора) се зареждат така, след като сложите `DEMO_PASSWORD` в `.env`:

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

Името и логото на училището се качват от администрацията → „Настройки на
играта“ → „Училище“ (PNG, JPG или WebP до 1 MB). Логото е собственост на
училището, затова не е в GitHub и не е под лиценза GPL; файлът стои само на
сървъра (папка `backend/media/`).

Сайтът има светла и тъмна тема (бутонът горе вдясно). По подразбиране следва
настройката на устройството, а изборът се запомня в браузъра.

## Публикуване

1. В `.env` на сървъра: `DJANGO_DEBUG=False`, нов `DJANGO_SECRET_KEY`,
   `DJANGO_ALLOWED_HOSTS` с домейна, `DJANGO_CSRF_TRUSTED_ORIGINS` с пълния
   адрес (напр. `https://questboard.example.bg`) и `DB_ENGINE=mysql` с данните
   за базата.
2. Ако пред приложението има прокси сървър с HTTPS (nginx или хостинг):
   `DJANGO_BEHIND_PROXY=True`, а когато HTTPS работи – `DJANGO_SSL_REDIRECT=True`
   и `DJANGO_HSTS_SECONDS=31536000`.
3. Стартиране:

```powershell
python start.py --production
```

Това прави миграциите, подготвя статичните файлове (WhiteNoise), проверява
настройките за сигурност (`manage.py check --deploy`) и пуска сървъра waitress
вместо сървъра за разработка. Асистентът остава достъпен само локално.

## Асистентът

Асистентът ползва и трите доставчика: **Claude, OpenAI и Gemini**. Първо пита
основния, а ако той не отговори (няма ключ, грешка, забавяне или невалиден
отговор), опитва следващия. В журнала се вижда кой модел е отговорил.

1. В `.env` сложете API ключовете (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
   `GEMINI_API_KEY`). Доставчик без ключ просто се пропуска.
2. В администрацията → „Настройки на играта“ изберете основния доставчик,
   попълнете името на модела за всеки (за Claude по подразбиране е
   `claude-opus-5-5`) и включете асистента. Индикаторът там показва дали
   асистентът работи и за кои доставчици има ключ.

Какво може:

- **Подсказка (Ф10)**: ученикът харчи Hint Token и получава насока по мисия.
  Ако моделът не отговори, токенът не се харчи.
- **Чернова на мисия (Ф11)**: учителят описва идея и асистентът попълва
  формата. Нищо не се публикува без учителя.
- **Справки (Ф17, Ф18, Ф22, Ф14)**: моделът само избира коя справка да се
  изпълни (извикване на функции). Django я изпълнява с правата на питащия.
  Имената на учителите се заменят с кодове, преди да отидат към модела.
- Всяко ползване се записва в журнала. Има дневен лимит на потребител.

Контролните случаи (20 броя) се пускат срещу истинските модели. С
`--provider all` всеки от трите се проверява поотделно, за сравнение:

```powershell
cd backend
python manage.py evaluate_assistant --provider all
```

Резултатите се записват в `docs/assistant-evaluation-<доставчик>.md`.

## Потребители

Няма свободна регистрация: акаунтите се създават от администратора, за да са в
платформата само истински ученици и учители с правилните роли. Много хора
наведнъж се внасят от CSV: администрация → Потребители → „Внеси от CSV“.
Първият ред е:

```
имейл,име,фамилия,роля,псевдоним,клас,гилдия
```

Пример: [backend/accounts/sample/potrebiteli_primer.csv](backend/accounts/sample/potrebiteli_primer.csv).
Всеки нов потребител получава временна парола, която се показва само веднъж
(и може да се свали като CSV), и трябва да я смени при първия вход.

## Разписание

Разписанието се внася от CSV файл: от администрацията (Разписание → „Внеси
от CSV“) или с `python manage.py import_timetable файл.csv`. Първият ред е:

```
ден,час,начало,край,клас,предмет,учител,кабинет
```

Пример: [backend/timetable/sample/razpisanie_primer.csv](backend/timetable/sample/razpisanie_primer.csv)
(измислени учители). Справките са на страница „Справки“ и работят и без асистента.

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
| [Pydantic](https://docs.pydantic.dev/) | проверка на заявките и отговорите на асистента | MIT |
| [anthropic](https://github.com/anthropics/anthropic-sdk-python) | връзка с Claude | Apache-2.0 |
| [openai](https://github.com/openai/openai-python) | връзка с OpenAI | Apache-2.0 |
| [google-genai](https://github.com/googleapis/python-genai) | връзка с Gemini | Apache-2.0 |
| [mysqlclient](https://github.com/PyMySQL/mysqlclient) | връзка с MySQL (по избор) | GPL-2.0-or-later |
| [Pillow](https://python-pillow.org/) | проверка, че каченото лого е изображение | MIT-CMU |
| [WhiteNoise](https://whitenoise.readthedocs.io/) | статичните файлове в публикуваната версия | MIT |
| [waitress](https://docs.pylonsproject.org/projects/waitress/) | уеб сървър в публикуваната версия | ZPL-2.1 |
| [Sofia Sans](https://github.com/lettersoup/Sofia-Sans) | шрифтът на сайта и администрацията – с българска кирилица (в `static/fonts/`) | SIL OFL 1.1 |
| [Cascadia Mono](https://github.com/microsoft/cascadia-code) | шрифтът в панелите с код – с български форми на буквите (в `static/fonts/`) | SIL OFL 1.1 |
| [Material Symbols](https://fonts.google.com/icons) | иконите в администрацията (идват с django-unfold) | Apache-2.0 |

django-unfold включва и свои JavaScript библиотеки (Alpine.js, htmx, Chart.js
и др.). Лицензите им са в пакета на django-unfold.
