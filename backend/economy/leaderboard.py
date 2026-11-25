"""
Класации по гилдии, класове и ученици (Ф7).

В класациите никога не се показват истинските имена – само псевдоними.
Всяка класация може да е за цялото време или само от началото на седмицата
(since), за да имат шанс и учениците, които са започнали по-късно.
"""
from dataclasses import dataclass
from datetime import datetime, time

from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from accounts.models import Guild, SchoolClass, User

from .models import Level


@dataclass
class Row:
    rank: int
    name: str
    xp: int
    members: int = 0
    level: Level | None = None
    guild: str = ""
    code: str = ""            # Guild.code – за цвета на гилдията
    user: User | None = None  # само за ученици – за аватара, титлата и рамката
    movement: int = 0         # с колко места се е качил (+) или паднал (-) от началото на седмицата

    @property
    def average(self):
        return round(self.xp / self.members) if self.members else 0

    @property
    def moved(self):
        """С колко места (без знака) – за стрелката ▲2 или ▼1."""
        return abs(self.movement)


def _level_finder():
    """Връща функция XP → ниво, без отделна заявка към базата за всеки ученик."""
    levels = list(Level.objects.order_by("min_xp"))

    def find(xp):
        current = None
        for level in levels:
            if xp >= level.min_xp:
                current = level
        return current

    return find


def _active_students_filter(prefix):
    return Q(**{f"{prefix}role": User.Role.STUDENT, f"{prefix}is_active": True})


def _xp_sum(path, prefix, since=None):
    """Сбор на XP по връзката path; само от активни ученици и (по желание) от дата нататък."""
    condition = _active_students_filter(prefix) if prefix else Q()
    if since:
        condition &= Q(**{f"{path}__created_at__gte": since})
    return Coalesce(Sum(f"{path}__amount", filter=condition), 0)


def guild_ranking(since=None):
    """XP на ученика се брои само за основната му гилдия."""
    guilds = Guild.objects.annotate(
        xp=_xp_sum("members__xp_transactions", "members__", since),
        member_count=Count("members", filter=_active_students_filter("members__"), distinct=True),
    ).order_by("-xp", "name")
    return [Row(rank=i, name=g.name, code=g.code, xp=g.xp, members=g.member_count) for i, g in enumerate(guilds, start=1)]


def class_ranking(since=None):
    classes = SchoolClass.objects.annotate(
        xp=_xp_sum("students__xp_transactions", "students__", since),
        member_count=Count("students", filter=_active_students_filter("students__"), distinct=True),
    ).filter(member_count__gt=0).order_by("-xp", "name")
    return [Row(rank=i, name=c.name, xp=c.xp, members=c.member_count) for i, c in enumerate(classes, start=1)]


def _ranks(students, key):
    """Място на всеки ученик при подреждане по key (при равен XP – по псевдоним)."""
    ordered = sorted(students, key=lambda s: (-key(s), (s.nickname or "").casefold()))
    return {s.pk: i for i, s in enumerate(ordered, start=1)}


def student_ranking(guild_id=None, class_id=None, limit=50, since=None, week_start=None):
    """
    Учениците по XP. since – само XP от тази дата (класация „тази седмица“).
    week_start – ако е дадено при общата класация, всеки ред казва с колко
    места е мръднал ученикът от началото на седмицата.
    """
    students = User.objects.filter(role=User.Role.STUDENT, is_active=True).select_related(
        "guild", "second_guild", "shown_title", "shown_frame").annotate(xp=_xp_sum("xp_transactions", "", since))
    if week_start and not since:
        students = students.annotate(week_xp=_xp_sum("xp_transactions", "", week_start))
    if guild_id:
        students = students.filter(Q(guild_id=guild_id) | Q(second_guild_id=guild_id))
    if class_id:
        students = students.filter(school_class_id=class_id)

    if since:  # нивото е по целия XP, не само по този за седмицата
        students = students.annotate(total_xp=_xp_sum("xp_transactions", ""))
    students = list(students)
    now = _ranks(students, lambda s: s.xp)
    before = _ranks(students, lambda s: s.xp - s.week_xp) if week_start and not since else now
    students.sort(key=lambda s: now[s.pk])

    level_of = _level_finder()
    return [
        Row(rank=now[s.pk], name=s.nickname, xp=s.xp, level=level_of(s.total_xp if since else s.xp),
            guild=s.guild.name if s.guild else "", code=s.guild.code if s.guild else "", user=s, movement=before[s.pk] - now[s.pk])
        for s in students[:limit]
    ]


def rankings(period="all", guild_id=None, class_id=None, limit=50):
    """
    Трите класации наведнъж: period="week" – само XP от началото на седмицата,
    иначе за цялото време (тогава учениците имат и движение от началото на седмицата).
    """
    from .services import week_start_for  # тук, за да няма кръгов import

    week_start = timezone.make_aware(datetime.combine(week_start_for(), time.min))
    since = week_start if period == "week" else None
    return {
        "guilds": guild_ranking(since),
        "classes": class_ranking(since),
        "students": student_ranking(guild_id, class_id, limit=limit, since=since, week_start=week_start),
    }
