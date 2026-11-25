"""
Животът на училището през последните осем седмици, разказан през правилата на играта.

Всяко събитие (заявка, проверка, тест, покупка) минава през същите функции като
страниците, но в своя момент от миналото. Затова XP, монетите, сериите, значките и
известията са верни и се нареждат по дати, без да се пипат на ръка.
"""
import random
from contextlib import contextmanager
from datetime import datetime, time, timedelta
from pathlib import Path
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from accounts.models import User
from accounts.nicknames import change_nickname
from assistant_bridge.models import Hint
from badges.models import Badge
from badges.services import give_badge
from economy.models import Privilege
from economy.services import (approve_claim, buy_privilege, give_bonus, mark_purchase_used, reject_claim,
                              undo_bonus, unused_purchases)
from missions.errors import GameRuleError
from missions.models import Claim, Mission
from missions.services import submit_claim
from notifications.models import Notification
from quizzes.models import GuildTest
from quizzes.services import (answer_question, current_question, note_left_page, open_session, start_attempt,
                              void_attempt)

from . import content
from .content import DOMAIN

FILES = Path(__file__).parent / "files"
TYPES = {".jpg": "image/jpeg", ".pdf": "application/pdf"}


@contextmanager
def at(moment):
    """Всичко вътре се случва в този момент (timezone.now() го връща)."""
    with patch("django.utils.timezone.now", return_value=moment):
        yield


def demo_file(name):
    path = FILES / name
    return SimpleUploadedFile(name, path.read_bytes(), content_type=TYPES[path.suffix])


class Story:
    def __init__(self, seed=21):
        self.rng = random.Random(seed)
        self.now = timezone.now()
        self.events = []      # (кога, ред на добавяне, какво)
        self.teachers = [User.objects.get(email=row[0]) for row in content.TEACHERS]
        self.students = {user.nickname: user for user in User.objects.filter(
            role=User.Role.STUDENT, email__endswith=DOMAIN).select_related("school_class", "guild", "second_guild").order_by("pk")}
        self.active = {row[2]: row[5] for row in content.STUDENTS}

    def run(self):
        self.plan_missions()
        self.plan_awards()
        self.plan_tests()
        self.plan_shopping()
        for moment, _order, action in sorted(self.events, key=lambda event: event[:2]):
            with at(moment):
                action()
        # Старите известия са прочетени, само последните чакат.
        Notification.objects.filter(created_at__lt=self.now - timedelta(days=2), read_at__isnull=True).update(
            read_at=self.now - timedelta(days=1))

    def add(self, moment, action):
        self.events.append((moment, len(self.events), action))

    def fresh(self, nickname):
        """Ученикът, както е в базата сега (псевдонимът може да е сменен)."""
        return User.objects.select_related("guild").get(pk=self.students[nickname].pk)

    def day(self, days_ago, hour):
        """Делничен ден, преди толкова дни."""
        date = timezone.localdate(self.now) - timedelta(days=days_ago)
        while date.weekday() > 4:
            date -= timedelta(days=1)
        return timezone.make_aware(datetime.combine(date, time(hour, self.rng.randint(0, 59))))

    def school_time_after(self, moment):
        """Учителят проверява след ден-два, в работно време (но не в бъдещето)."""
        date = timezone.localdate(moment) + timedelta(days=self.rng.randint(1, 2))
        while date.weekday() > 4:
            date += timedelta(days=1)
        review = timezone.make_aware(datetime.combine(date, time(self.rng.randint(8, 16), self.rng.randint(0, 59))))
        return review if review < self.now else moment + (self.now - moment) / 2

    # ---------- Мисии и домашни ----------

    def plan_missions(self):
        self.done = dict.fromkeys(self.students, 0)
        self.weeks = set()    # (ученик, седмица), за да имат активните серии
        for quest in [*content.MISSIONS, *content.HOMEWORK]:
            mission = Mission.objects.get(title=quest.title)
            candidates = [student for student in self.students.values()
                          if not quest.classes or student.school_class.name in quest.classes]
            # По отворените мисии последните едно-две доказателства чакат проверка.
            waiting = 0
            if quest.end > 0 and len(quest.proofs) > 1:
                waiting = 2 if len(quest.proofs) > 3 else 1
            reviewed = len(quest.proofs) - waiting
            first, last = quest.start - 1, max(-quest.end, 1)
            for index, (text, file) in enumerate(quest.proofs):
                pending = index >= reviewed
                if pending:
                    moment = self.now - timedelta(hours=self.rng.uniform(2, 40))
                else:
                    share = (index + self.rng.random() * 0.8) / reviewed
                    moment = self.day(round(first - share * (first - last)), self.rng.randint(13, 19))
                    moment = max(moment, mission.created_at + timedelta(hours=2))
                crew = self.pick(quest, candidates, moment)
                self.add(moment, self.submit(mission, crew, text, file))
                if not pending:
                    self.plan_review(quest, mission, crew, moment, text, file)

    def pick(self, quest, candidates, moment):
        """
        Капитан и съотборници. По-активните и членовете на гилдията участват по-често,
        но никой два пъти в една мисия.
        """
        week = moment.isocalendar()[:2]

        def weight(student):
            active = self.active[student.nickname]
            value = active ** 1.6 / (1 + self.done[student.nickname] * 0.35)
            if quest.source in [guild.code for guild in student.guilds]:
                value *= 2
            if active >= 8 and (student.nickname, week) not in self.weeks:
                value *= 15 if active == 10 else 4  # Феникс е за демонстрация: има дълга серия
            return value

        crew = []
        for _ in range(self.rng.randint(*quest.team) if quest.team else 1):
            student = self.rng.choices(candidates, [weight(student) for student in candidates])[0]
            candidates.remove(student)
            self.done[student.nickname] += 1
            self.weeks.add((student.nickname, week))
            crew.append(student.nickname)
        return crew

    def submit(self, mission, crew, text, file):
        def action():
            submit_claim(self.fresh(crew[0]), mission, text, [demo_file(file)] if file else [],
                         teammates=[self.fresh(nickname).nickname for nickname in crew[1:]])
        return action

    def plan_review(self, quest, mission, crew, moment, text, file):
        reviewer = self.teachers[self.rng.choice([quest.teacher, quest.teacher, *quest.deputies])]
        review = self.school_time_after(moment)

        def claim():
            return Claim.objects.get(mission=mission, student=self.students[crew[0]])

        # Понякога първо е отказана и се подава пак.
        again = review + timedelta(hours=6)
        if not quest.team and self.rng.random() < 0.2 and again < min(mission.deadline, self.now - timedelta(days=4)):
            self.add(review, lambda: reject_claim(claim(), reviewer, self.rng.choice(content.REJECTIONS)))
            self.add(again, self.submit(mission, crew, text + " Допълних го.", file))
            review = self.school_time_after(again)
        self.add(review, lambda: approve_claim(claim(), reviewer, self.rng.choice(content.PRAISE)))

    # ---------- Бонуси и значки от учител ----------

    def plan_awards(self):
        def bonus(teacher, nickname, xp, reason):
            return lambda: give_bonus(self.teachers[teacher], self.fresh(nickname), xp, reason)

        def badge(teacher, nickname, name, note):
            def action():
                item = Badge.objects.filter(name=name, rule=Badge.Rule.MANUAL, is_active=True).first()
                if item:
                    give_badge(self.teachers[teacher], self.fresh(nickname), item, note)
            return action

        for days, *row in content.BONUSES:
            self.add(self.day(days, 12), bonus(*row))
        for days, *row in content.BADGES:
            self.add(self.day(days, 11), badge(*row))

        # Един бонус е даден на грешния ученик и е отменен: вижда се в журнала.
        mistake = self.day(6, 10)
        self.add(mistake, bonus(1, "Маяк", 20, "Помощ в час"))
        self.add(mistake + timedelta(hours=2), lambda: undo_bonus(
            self.teachers[1], self.fresh("Маяк").xp_transactions.get(is_bonus=True, amount__gt=0), "Грешен ученик"))
        self.add(self.day(20, 17), lambda: change_nickname(self.fresh("Феномен"), "Квант"))

    # ---------- Тестове на гилдиите ----------

    def plan_tests(self):
        for days, code, nickname, good in content.ENTRY_TESTS:
            self.add(self.day(days, 9), self.sitting(code, GuildTest.Kind.ENTRY, [(nickname, good)]))
        for days, (code, nicknames) in enumerate(content.MONTHLY_TESTS.items(), start=2):
            moment = self.day(days, 10)
            results = [(nickname, number < 2) for number, nickname in enumerate(nicknames)]
            self.add(moment, self.sitting(code, GuildTest.Kind.MONTHLY, results, cheater="Мълния"))

    def sitting(self, code, kind, results, cheater=""):
        """Един учебен час: учителят пуска теста, учениците го решават."""
        def action():
            test = GuildTest.objects.get(guild__code=code, kind=kind)
            session = open_session(test.created_by, test, 10)
            for nickname, good in results:
                attempt = start_attempt(self.fresh(nickname), session.code)
                clock = timezone.now()
                for number in range(attempt.total):
                    question, _left = current_question(attempt, now=clock)
                    clock += timedelta(seconds=self.rng.uniform(4, 10))
                    right = good or number % 2 == 0
                    answer_question(attempt, question.pk, self.answer(question, attempt.secret, right), now=clock)
                    if not good and number == 1:
                        note_left_page(attempt)
                if nickname == cheater:
                    void_attempt(test.created_by, attempt, "Преписваше от телефона")
        return action

    def answer(self, question, secret, right):
        options = question.shuffled(secret)
        if question.kind == question.Kind.TEXT:
            return question.lines[0] if right else "не знам"
        numbers = {value: number for number, value in options}
        if question.kind == question.Kind.ORDER:
            picked = [str(numbers[line]) for line in question.lines]
            return ",".join(picked if right else picked[::-1])
        correct = next(numbers[line.removeprefix("*").strip()] for line in question.lines if line.startswith("*"))
        return str(correct if right else (correct + 1) % len(options))

    # ---------- Магазин ----------

    def plan_shopping(self):
        self.wishes = {}
        self.add(self.day(10, 18), lambda: self.buy(self.fresh("Феникс"), "hint_token"))
        for days in (38, 31, 24, 17, 11, 4):
            self.add(self.day(days, 20), self.shopping_evening)
        self.add(self.day(2, 13), self.teacher_marks_used)
        self.add(self.now - timedelta(hours=20), self.use_hint)

    def buy(self, student, code):
        item = Privilege.objects.filter(code=code, is_active=True).first()
        try:
            return item and buy_privilege(student, item)
        except GameRuleError:
            return None  # няма монети, нивото е ниско или вече го има

    def shopping_evening(self):
        items = list(Privilege.objects.filter(is_active=True, only_from_mission=False))
        for nickname in self.students:
            if nickname == "Феникс":  # пести за демонстрацията
                continue
            # Всеки си е харесал едно нещо и пести за него.
            wish = self.wishes.setdefault(nickname, self.rng.choices(items, [1 / item.price for item in items])[0].code)
            if self.buy(self.fresh(nickname), wish):
                del self.wishes[nickname]

    def teacher_marks_used(self):
        for teacher in self.teachers:
            for purchase in list(unused_purchases(teacher))[::2]:
                mark_purchase_used(purchase, teacher)

    def use_hint(self):
        student = self.fresh("Феникс")
        mission = Mission.objects.get(title=content.HINT_MISSION)
        token = student.purchases.filter(privilege__code="hint_token", used_at__isnull=True).first()
        if token:
            token.used_at, token.used_for_mission = timezone.now(), mission
            token.save()
            Hint.objects.create(student=student, mission=mission, purchase=token, text=content.HINT)
