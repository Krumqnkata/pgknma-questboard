"""
Добавя „живот“ към демо данните: още ученици и мисии и няколко седмици
активност – потвърдени, чакащи и отказани заявки (някои със снимки), бонуси,
покупки, титли, рамки и значки. Така класацията, сериите и таблото в
администрацията изглеждат истински още от първата минута на демонстрацията.

    python manage.py seed_demo       # първо основните демо данни
    python manage.py seed_activity

Всички хора са измислени. Всичко минава през правилата на играта (същите
функции като страниците), затова XP, монетите и значките са верни. Командата
отказва да работи, ако в базата има потребители извън демо домейна –
за да не се смеси с истински данни.
"""
import os
import random
from datetime import timedelta
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from PIL import Image, ImageDraw

from accounts.models import Guild, SchoolClass, User
from badges.models import Badge
from badges.services import give_badge
from economy.models import Privilege, XPTransaction
from economy.services import approve_claim, buy_privilege, coin_balance, give_bonus, reject_claim, wear
from missions.models import Claim, EvidenceFile, Mission
from missions.services import GameRuleError, submit_claim

DOMAIN = "@questboard.test"

TEACHER2 = {"email": "uchitel2@questboard.test", "first_name": "Петър", "last_name": "Николов"}

# име, фамилия, псевдоним, клас, гилдия
STUDENTS = [
    ("Ивана", "Димова", "Нова", "9В", "Изследователи"), ("Георги", "Тодоров", "Титан", "9В", "Техничари"),
    ("Виктория", "Ангелова", "Искра", "9В", "Организатори"), ("Николай", "Христов", "Орион", "10А", "Помощници"),
    ("Мартина", "Желева", "Луна", "10А", "Изследователи"), ("Александър", "Василев", "Пиксел", "10А", "Техничари"),
    ("Теодора", "Маркова", "Аврора", "11Б", "Организатори"), ("Стефан", "Илиев", "Ракета", "11Б", "Помощници"),
    ("Дарина", "Николова", "Мълния", "11Б", "Техничари"), ("Кристиан", "Петров", "Байт", "12А", "Изследователи"),
    ("Ралица", "Стоянова", "Звезда", "12А", "Организатори"), ("Йоан", "Костов", "Вектор", "12А", "Помощници"),
    ("Елица", "Митева", "Пеперуда", "9В", "Организатори"), ("Самуил", "Генов", "Компас", "10А", "Изследователи"),
    ("Надежда", "Русева", "Кристал", "11Б", "Помощници"), ("Борислав", "Енчев", "Гранит", "12А", "Техничари"),
]

# заглавие, гилдия, XP, описание, критерий, учител (1 или 2)
MISSIONS = [
    ("Модератор на училищния сървър", "Техничари", 90,
     "Помогни на учителя по информатика да поддържа сървъра на кабинета една седмица.",
     "Дневник с направеното и потвърждение от учителя.", 2),
    ("Кампания „Без пластмаса“", "Организатори", 50,
     "Организирай с класа си събиране на пластмаса за рециклиране.",
     "Снимки от събирането и брой събрани торби.", 1),
    ("Ден на отворените врати", "Изследователи", 70,
     "Покажи училището на бъдещите ученици и техните родители.",
     "Присъствие поне 3 часа, потвърдено от организатора.", 2),
    ("Охрана на тишината в библиотеката", "Помощници", 20,
     "Помогни на библиотекаря през едно междучасие.",
     "Потвърждение от библиотекаря.", 1),
    ("Видео за спорта в училище", "Изследователи", 60,
     "Заснеми кратко видео за спортния ден.",
     "Връзка към видеото в YouTube или Google Drive.", 1),
    ("Карта на училищните растения", "Организатори", 40,
     "Направи карта на растенията в двора с имената им.",
     "PDF с картата и поне 10 растения.", 2),
]

COLORS = [(200, 16, 46), (37, 99, 184), (31, 138, 84), (122, 75, 196), (194, 124, 14)]


def demo_photo(number):
    """Измислена „снимка“ – цветен фон с прости фигури (без хора и лични данни)."""
    rng = random.Random(number)
    base = COLORS[number % len(COLORS)]
    image = Image.new("RGB", (1200, 900), base)
    draw = ImageDraw.Draw(image)
    for _ in range(14):
        x, y, size = rng.randint(-100, 1100), rng.randint(-100, 800), rng.randint(80, 320)
        shade = tuple(min(255, channel + rng.randint(20, 120)) for channel in base)
        draw.ellipse((x, y, x + size, y + size), fill=shade)
    buffer = BytesIO()
    image.save(buffer, "JPEG", quality=80)
    return SimpleUploadedFile(f"snimka-{number}.jpg", buffer.getvalue(), content_type="image/jpeg")


class Command(BaseCommand):
    help = "Добавя няколко седмици измислена активност към демо данните."

    def handle(self, *args, **options):
        if User.objects.exclude(email__endswith=DOMAIN).exists():
            raise CommandError("В базата има истински потребители – командата е само за демо база.")
        teacher = User.objects.filter(email="uchitel@questboard.test").first()
        if not teacher:
            raise CommandError("Първо пуснете python manage.py seed_demo.")
        password = os.getenv("DEMO_PASSWORD", "")
        rng = random.Random(2026)
        now = timezone.now()

        teacher2 = self.user(password, role=User.Role.TEACHER, **TEACHER2)
        guilds = {guild.name: guild for guild in Guild.objects.all()}
        for number, (first, last, nickname, class_name, guild) in enumerate(STUDENTS, start=5):
            school_class, _ = SchoolClass.objects.get_or_create(name=class_name)
            self.user(password, email=f"uchenik{number}{DOMAIN}", first_name=first, last_name=last,
                      role=User.Role.STUDENT, nickname=nickname, school_class=school_class, guild=guilds[guild])
        for title, guild, xp, description, criteria, who in MISSIONS:
            Mission.objects.get_or_create(title=title, defaults={
                "guild": guilds[guild], "xp": xp, "description": description, "criteria": criteria,
                "deadline": now + timedelta(days=rng.randint(6, 25)), "created_by": teacher if who == 1 else teacher2,
            })

        students = list(User.objects.filter(role=User.Role.STUDENT, email__endswith=DOMAIN))
        missions = list(Mission.objects.filter(is_active=True))
        photo = 0

        # Четири седмици назад: всеки ученик изпълнява мисии с различно темпо.
        for student in students:
            pace = rng.choice([0, 1, 1, 2, 2, 3])
            done = rng.sample(missions, k=min(len(missions), pace * 2))
            for index, mission in enumerate(done):
                if Claim.objects.filter(student=student, mission=mission).exists():
                    continue
                weeks_ago = index % 4
                moment = now - timedelta(weeks=weeks_ago, days=rng.randint(0, 2), hours=rng.randint(1, 8))
                files = []
                if rng.random() < 0.5:
                    photo += 1
                    files = [demo_photo(photo)]
                claim = submit_claim(student, mission, rng.choice([
                    "Готово! Снимките са прикачени.", "Направих го заедно с класа.",
                    "Ето връзка към публикацията: https://example.com/statia", "Учителят беше там и видя.",
                ]), files)
                approve_claim(claim, mission.created_by, rng.choice(["", "Браво!", "Много добре."]), now=moment)
                self.backdate(claim, moment)

        # Няколко заявки чакат проверка – учителят има какво да види на демонстрацията.
        for student in rng.sample(students, k=4):
            mission = next((m for m in missions if m.created_by == teacher
                            and not Claim.objects.filter(student=student, mission=m).exists()), None)
            if mission:
                photo += 1
                submit_claim(student, mission, "Изпълних мисията, ето снимка.", [demo_photo(photo)])

        # Една отказана заявка с коментар
        for student in students:
            mission = next((m for m in missions if not Claim.objects.filter(student=student, mission=m).exists()), None)
            if mission:
                claim = submit_claim(student, mission, "Мисля, че е готово.")
                reject_claim(claim, mission.created_by, "Липсва снимка или връзка. Добави и подай пак.")
                break

        # Бонуси и значка от учител
        for student, reason in zip(rng.sample(students, k=3),
                                   ["Помощ при подреждането на актовата зала", "Отлично представяне на олимпиадата",
                                    "Организира класа за благотворителния базар"]):
            try:
                give_bonus(teacher, student, rng.choice([20, 30, 50]), reason)
            except GameRuleError:
                pass
        star = Badge.objects.filter(rule=Badge.Rule.MANUAL, is_active=True).first()
        if star:
            try:
                give_badge(teacher, rng.choice(students), star, "Най-активен тази седмица")
            except GameRuleError:
                pass

        # Покупки: привилегии и неща за профила
        items = list(Privilege.objects.filter(is_active=True).order_by("price"))
        for student in students:
            for item in sorted(items, key=lambda _: rng.random()):
                if coin_balance(student) >= item.price and rng.random() < 0.5:
                    try:
                        buy_privilege(student, item)
                    except GameRuleError:
                        continue
            if student.shown_frame_id and rng.random() < 0.3:
                wear(student, None, kind=Privilege.Kind.FRAME)

        self.stdout.write(self.style.SUCCESS(
            f"Готово: {len(students)} ученици, {Claim.objects.count()} заявки "
            f"({EvidenceFile.objects.count()} снимки), {XPTransaction.objects.filter(amount__gt=0).count()} движения на XP."))

    def user(self, password, email, **fields):
        user = User.objects.filter(email=email).first() or User(email=email)
        for name, value in fields.items():
            setattr(user, name, value)
        if not user.pk:
            user.set_password(password)
        user.full_clean()
        user.save()
        return user

    def backdate(self, claim, moment):
        """Премества заявката и наградите от нея назад във времето (за серии и графики по седмици)."""
        Claim.objects.filter(pk=claim.pk).update(submitted_at=moment - timedelta(hours=3), reviewed_at=moment)
        claim.xp_transactions.update(created_at=moment)
        claim.coin_transactions.update(created_at=moment)
        claim.student.notifications.filter(created_at__gte=timezone.now() - timedelta(minutes=5)).update(
            created_at=moment, read_at=moment)
