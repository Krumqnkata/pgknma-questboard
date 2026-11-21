"""
Класации по гилдии, класове и ученици (Ф7).

В класациите никога не се показват истинските имена – само псевдоними.
"""
from dataclasses import dataclass

from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce

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

    @property
    def average(self):
        return round(self.xp / self.members) if self.members else 0


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


def guild_ranking():
    guilds = Guild.objects.annotate(
        xp=Coalesce(Sum("members__xp_transactions__amount", filter=_active_students_filter("members__")), 0),
        member_count=Count("members", filter=_active_students_filter("members__"), distinct=True),
    ).order_by("-xp", "name")
    return [Row(rank=i, name=g.name, xp=g.xp, members=g.member_count) for i, g in enumerate(guilds, start=1)]


def class_ranking():
    classes = SchoolClass.objects.annotate(
        xp=Coalesce(Sum("students__xp_transactions__amount", filter=_active_students_filter("students__")), 0),
        member_count=Count("students", filter=_active_students_filter("students__"), distinct=True),
    ).filter(member_count__gt=0).order_by("-xp", "name")
    return [Row(rank=i, name=c.name, xp=c.xp, members=c.member_count) for i, c in enumerate(classes, start=1)]


def student_ranking(guild_id=None, class_id=None, limit=50):
    students = User.objects.filter(role=User.Role.STUDENT, is_active=True).select_related("guild").annotate(
        xp=Coalesce(Sum("xp_transactions__amount"), 0),
    ).order_by("-xp", "nickname")
    if guild_id:
        students = students.filter(guild_id=guild_id)
    if class_id:
        students = students.filter(school_class_id=class_id)

    level_of = _level_finder()
    return [
        Row(rank=i, name=s.nickname, xp=s.xp, level=level_of(s.xp), guild=s.guild.name if s.guild else "")
        for i, s in enumerate(students[:limit], start=1)
    ]
