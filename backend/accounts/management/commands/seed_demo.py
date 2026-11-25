"""
Зарежда примерни данни: класове, акаунти за всяка роля, мисии, домашни, външни награди,
тестове на гилдиите и примерно седмично разписание.

    python manage.py seed_demo

Всички хора са измислени (вижте accounts/demo/). Паролата на тестовите акаунти се взема
от DEMO_PASSWORD в .env, за да не стои в кода. Командата може да се пуска многократно:
не създава дубликати, а обновява паролите.
"""
import os
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.demo import content, questions
from accounts.demo.story import at, demo_file
from accounts.models import Guild, SchoolClass, User
from badges.models import Badge
from economy.models import Privilege, Sponsor
from missions.evidence import prepare
from missions.models import Mission
from missions.services import attach_to_mission
from quizzes.models import GuildTest, Question
from timetable.importer import import_timetable
from timetable.models import Lesson

SAMPLE_TIMETABLE = Path(settings.BASE_DIR) / "timetable" / "sample" / "razpisanie_primer.csv"
TERM = timedelta(days=65)  # преди толкова са създадени акаунтите и тестовете
OWN_FIELDS = ("nickname", "guild", "second_guild", "avatar_seed")  # ученикът може вече да ги е сменил


class Command(BaseCommand):
    help = "Зарежда примерни класове, акаунти, мисии, тестове и разписание (само измислени хора)."

    @transaction.atomic
    def handle(self, *args, **options):
        password = os.getenv("DEMO_PASSWORD", "")
        if len(password) < 8:
            raise CommandError("Сложете DEMO_PASSWORD в .env (поне 8 символа).")
        self.password = make_password(password)
        self.now = timezone.now()
        self.guilds = {guild.code: guild for guild in Guild.objects.all()}
        classes = {name: SchoolClass.objects.get_or_create(name=name)[0] for name in content.CLASSES}

        self.save_user(role=User.Role.ADMIN, **content.ADMIN)
        self.teachers = [self.save_user(email=email, first_name=first, last_name=last, role=User.Role.TEACHER)
                         for email, first, last in content.TEACHERS]
        for number, (first, last, nickname, class_name, guild, _active) in enumerate(content.STUDENTS, start=1):
            self.save_user(email=f"uchenik{number if number > 1 else ''}{content.DOMAIN}", first_name=first,
                           last_name=last, role=User.Role.STUDENT, nickname=nickname,
                           school_class=classes[class_name], guild=self.guilds.get(guild),
                           second_guild=self.guilds.get(content.SECOND_GUILDS.get(nickname)), avatar_seed=number * 37)

        for code, numbers in content.LEADERS.items():
            if code in self.guilds and not self.guilds[code].leaders.exists():
                self.guilds[code].leaders.set([self.teachers[number] for number in numbers])

        self.save_rewards()
        for quest in content.MISSIONS:
            self.save_quest(quest)
        for quest in content.HOMEWORK:
            self.save_quest(quest, classes)
        self.save_tests()

        # Примерното разписание се внася само ако още няма друго.
        if not Lesson.objects.exists():
            timetable = import_timetable(SAMPLE_TIMETABLE.read_text(encoding="utf-8"))
            if not timetable.ok:
                raise CommandError("Примерното разписание има грешки: " + "; ".join(timetable.errors))
        for teacher in self.teachers:
            Lesson.objects.filter(teacher_name=teacher.get_full_name(), teacher__isnull=True).update(teacher=teacher)

        last = f"uchenik{len(content.STUDENTS)}{content.DOMAIN}"
        self.stdout.write(self.style.SUCCESS(
            f"Готово: {len(content.STUDENTS)} ученици, {len(self.teachers)} учители, {Mission.objects.count()} мисии и "
            f"домашни, {GuildTest.objects.count()} теста."))
        self.stdout.write(f"  администратор: {content.ADMIN['email']}")
        self.stdout.write("  учители: " + ", ".join(row[0] for row in content.TEACHERS))
        self.stdout.write(f"  ученици: uchenik{content.DOMAIN}, uchenik2{content.DOMAIN} до {last}")
        self.stdout.write("Паролата е стойността на DEMO_PASSWORD от .env.")

    def save_user(self, email, **fields):
        user = User.objects.filter(email=email).first() or User(email=email, date_joined=self.now - TERM)
        for name, value in fields.items():
            if user.pk is None or name not in OWN_FIELDS:
                setattr(user, name, value)
        user.password = self.password
        user.full_clean()
        user.save()
        return user

    def save_rewards(self):
        sponsors = [Sponsor.objects.get_or_create(name=name)[0] for name in content.SPONSORS]
        for code, name, description, price, level, sponsor, person, stock, only_from_mission in content.REWARDS:
            Privilege.objects.get_or_create(code=code, defaults={
                "kind": Privilege.Kind.SPONSOR, "name": name, "description": description, "price": price,
                "min_level": level, "sponsor": sponsors[sponsor], "stock": stock,
                "responsible": self.teachers[person],
                "only_from_mission": only_from_mission,
            })

    def save_quest(self, quest, classes=None):
        """Мисия или (с класове) домашна. Създадена е в миналото, за да има време за заявките."""
        if Mission.objects.filter(title=quest.title).exists():
            return
        last_day = timezone.localtime(self.now + timedelta(days=quest.end))
        mission = Mission(
            title=quest.title, description=quest.description, criteria=quest.criteria, xp=quest.xp,
            deadline=last_day.replace(hour=23, minute=59, second=0, microsecond=0), created_by=self.teachers[quest.teacher],
            hints_allowed=quest.hints,
            reward_badge=Badge.objects.filter(name=quest.badge).first() if quest.badge else None,
            reward_item=Privilege.objects.filter(code=quest.item).first() if quest.item else None,
        )
        if classes:
            mission.kind, mission.subject = Mission.Kind.HOMEWORK, quest.source
        else:
            mission.guild = self.guilds[quest.source]
        if quest.team:
            mission.is_group, (mission.team_min, mission.team_max) = True, quest.team
        with at(self.now - timedelta(days=quest.start)):
            mission.full_clean()
            mission.save()
            mission.reviewers.set([self.teachers[number] for number in quest.deputies])
            mission.school_classes.set([classes[name] for name in quest.classes])
            if quest.handout:
                attach_to_mission(mission, [prepare(demo_file(quest.handout), 5 * 1024 * 1024)])

    def save_tests(self):
        for code, (teacher, entry, monthly) in questions.TESTS.items():
            guild = self.guilds[code]
            self.save_test(guild, GuildTest.Kind.ENTRY, f"Входен тест: {guild.name}", teacher, entry, 6, 0)
            self.save_test(guild, GuildTest.Kind.MONTHLY, f"Месечен тест: {guild.name}", teacher, monthly, 5, 40)

    def save_test(self, guild, kind, title, teacher, rows, count, xp):
        if GuildTest.objects.filter(guild=guild, kind=kind).exists():
            return
        with at(self.now - TERM):
            test = GuildTest(guild=guild, kind=kind, title=title, created_by=self.teachers[teacher],
                             questions_count=count, seconds=15, xp=xp,
                             description="Решава се пред учител, с код от него.")
            test.full_clean()
            test.save()
            self.save_questions(test, rows)
            if (guild.code, kind) == ("techies", GuildTest.Kind.MONTHLY):
                self.save_questions(test, questions.DRAFTS, approved=False)

    def save_questions(self, test, rows, approved=True):
        for kind, text, answers in rows:
            question = Question(test=test, kind=kind, text=text, answers=answers, is_approved=approved,
                                seconds=None if kind == Question.Kind.CHOICE else 60)
            question.full_clean()
            question.save()
