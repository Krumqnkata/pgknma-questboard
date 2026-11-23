"""
Таблото на администрацията (началната страница на /admin/).

Тук само се събират числата. Как изглеждат е в templates/admin/index.html,
а стиловете – в static/css/admin.css. Графиките са обикновен HTML и CSS,
без JavaScript библиотека, затова се четат и от екранни четци.
"""
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from django.db.models import Avg, Count, Q, Sum
from django.urls import reverse
from django.utils import timezone

from accounts.models import Guild, User
from assistant_bridge.models import AssistantLog
from economy.models import GameSettings, XPTransaction
from economy.services import week_start_for
from missions.models import Claim
from web.models import BotKnock

WEEKS_SHOWN = 8
MONTHS = ["яну", "фев", "мар", "апр", "май", "юни", "юли", "авг", "сеп", "окт", "ное", "дек"]


def number(value):
    """1240 → „1 240“ (с неделим интервал, както се пишат числата на български)."""
    return f"{value:,}".replace(",", " ")


def short_date(day):
    return f"{day.day} {MONTHS[day.month - 1]}"


def start_of(day):
    """Началото на деня (00:00) в часовата зона на сайта."""
    return timezone.make_aware(datetime.combine(day, time.min))


def nice_max(value):
    """Горната граница на оста – кръгло число: 1, 2, 5, 10, 20, 50..."""
    if value <= 0:
        return 1
    step = 1
    while True:
        for factor in (1, 2, 5):
            if step * factor >= value:
                return step * factor
        step *= 10


@dataclass
class Kpi:
    label: str
    value: str
    note: str = ""
    link: str = ""


def kpis(week_start):
    since = start_of(week_start)
    pending = Claim.objects.filter(status=Claim.Status.PENDING).count()
    return [
        Kpi("Ученици", number(User.objects.filter(role=User.Role.STUDENT, is_active=True).count()),
            link=reverse("admin:accounts_user_changelist") + "?role__exact=student"),
        Kpi("Активни тази седмица",
            number(Claim.objects.filter(submitted_at__gte=since).values("student").distinct().count()),
            note="ученици с подадена заявка"),
        Kpi("Чакащи заявки", number(pending), note="чакат учител" if pending else "няма чакащи",
            link=reverse("admin:missions_claim_changelist") + "?status__exact=pending"),
        Kpi("XP тази седмица", number(XPTransaction.objects.filter(created_at__gte=since)
                                      .aggregate(total=Sum("amount"))["total"] or 0),
            note=f"от {short_date(week_start)}"),
        # Ботовете, които търсят /wp-admin/ и подобни – получават „Това не е WordPress“.
        Kpi("Ботове, търсили WordPress", number(BotKnock.objects.filter(day__gte=week_start)
                                                .aggregate(total=Sum("hits"))["total"] or 0),
            note="тази седмица", link=reverse("admin:web_botknock_changelist")),
    ]


def weekly_approved(week_start):
    """Колко заявки са потвърдени във всяка от последните седмици (най-старата първа)."""
    weeks = []
    for back in range(WEEKS_SHOWN - 1, -1, -1):
        start = week_start - timedelta(weeks=back)
        count = Claim.objects.filter(status=Claim.Status.APPROVED, reviewed_at__gte=start_of(start),
                                     reviewed_at__lt=start_of(start + timedelta(days=7))).count()
        weeks.append({"start": start, "count": count, "label": short_date(start),
                      "range": f"{short_date(start)} – {short_date(start + timedelta(days=6))}"})
    top = nice_max(max(week["count"] for week in weeks))
    for week in weeks:
        week["percent"] = round(week["count"] * 100 / top, 1)
    middle = top // 2 if top % 2 == 0 else None  # средната черта е с число само ако е цяло
    return {"weeks": weeks, "axis": [top, middle, 0],
            "total": sum(week["count"] for week in weeks)}


def xp_by_guild():
    """Общо XP на учениците от всяка гилдия, най-голямото първо."""
    rows = (Guild.objects
            .annotate(xp=Sum("members__xp_transactions__amount"),
                      students=Count("members", filter=Q(members__role=User.Role.STUDENT), distinct=True))
            .values("name", "xp", "students"))
    rows = sorted(({**row, "xp": row["xp"] or 0} for row in rows), key=lambda row: -row["xp"])
    top = max((row["xp"] for row in rows), default=0) or 1
    for row in rows:
        row["percent"] = round(row["xp"] * 100 / top, 1)
        row["xp_text"] = number(row["xp"])
    return rows


def top_missions(limit=5):
    """Мисиите с най-много потвърдени заявки."""
    claims = (Claim.objects
              .values("mission_id", "mission__title", "mission__guild__name")
              .annotate(approved=Count("id", filter=Q(status=Claim.Status.APPROVED)),
                        pending=Count("id", filter=Q(status=Claim.Status.PENDING)))
              .filter(approved__gt=0)
              .order_by("-approved", "mission__title")[:limit])
    return [{**row, "link": reverse("admin:missions_mission_change", args=[row["mission_id"]])} for row in claims]


def assistant_usage(days=7):
    """Заявките към асистента за последните дни, по доставчик (кой е отговорил)."""
    names = dict(GameSettings.LlmProvider.choices)
    rows = (AssistantLog.objects.filter(created_at__gte=timezone.now() - timedelta(days=days))
            .values("provider")
            .annotate(requests=Count("id"), ok=Count("id", filter=Q(success=True)), ms=Avg("duration_ms"))
            .order_by("-requests"))
    return [{
        "name": names.get(row["provider"], "без отговор"),
        "requests": row["requests"],
        "ok": row["ok"],
        "seconds": f"{row['ms'] / 1000:.1f}".replace(".", ",") if row["ms"] else "—",
    } for row in rows]


def dashboard_callback(request, context):
    """Вика се от django-unfold при отваряне на /admin/ (настройката DASHBOARD_CALLBACK)."""
    week_start = week_start_for()
    context["dashboard"] = {
        "kpis": kpis(week_start),
        "weekly": weekly_approved(week_start),
        "guilds": xp_by_guild(),
        "missions": top_missions(),
        "assistant": assistant_usage(),
    }
    return context
