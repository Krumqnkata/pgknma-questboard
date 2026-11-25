"""
Справките на асистента за самия сайт: мисии, магазин, значки, класация, правила.

Всяка справка връща данни за модела и връзки за бутоните под отговора. Връзките ги
прави сървърът, а не моделът, затова не може да има измислен адрес. Към модела не
отиват имена, псевдоними и текстове на ученици, а само числа и публични заглавия.
"""
from dataclasses import dataclass, field

from django.db.models import Count, Min, Q
from django.urls import reverse
from django.utils import timezone

from accounts.models import MAX_GUILDS
from badges.services import badge_cards
from economy import leaderboard
from economy.models import GameSettings, Level, Privilege
from economy.services import active_privileges, is_unlocked, student_stats, unused_purchases
from missions.deadlines import apply_extensions
from missions.models import Claim, Mission
from missions.services import claims_to_decide, missions_for_student, missions_reviewed_by, open_first

MAX_MISSIONS = 12
MAX_LINKS = 3


@dataclass
class Link:
    label: str
    url: str
    match: str = ""  # показва се само ако този текст е в отговора; празно – винаги


@dataclass
class ToolResult:
    data: dict
    links: list = field(default_factory=list)


def visible_links(links, answer):
    """Кои бутони се показват: споменатите в отговора и накрая общият."""
    mentioned = [link for link in links if link.match and link.match.lower() in answer.lower()]
    general = [link for link in links if not link.match]
    return [{"label": link.label, "url": link.url} for link in (mentioned[:MAX_LINKS - 1] + general)[:MAX_LINKS]]


def _date(moment):
    return timezone.localtime(moment).strftime("%d.%m %H:%M")


def _tier(xp, max_xp):
    share = xp / (max_xp or 1)
    return "бронзова (лесна)" if share <= 1 / 3 else "сребърна (средна)" if share <= 2 / 3 else "златна (трудна)"


def _mission_links(missions):
    return [Link(f"Отвори „{mission.title}“", reverse("mission_detail", args=[mission.pk]), mission.title)
            for mission in missions]


# ---------- За ученика ----------

def open_missions(user, arguments):
    """Активните мисии, които ученикът още не е заявил; първо тези на гилдиите му."""
    missions = missions_for_student(user).select_related("reward_badge", "reward_item").exclude(claims__student=user)
    kind = str(arguments.get("kind") or "").strip().lower()
    if kind.startswith("отбор"):
        missions = missions.filter(is_group=True)
    elif kind.startswith("индив"):
        missions = missions.filter(is_group=False)
    elif kind.startswith("домаш"):
        missions = missions.filter(kind=Mission.Kind.HOMEWORK)
    guild = str(arguments.get("guild") or "").strip()
    guild = "" if guild.lower() in ("всички", "няма", "празно") else guild
    in_guild = missions.filter(guild__name=guild) if guild else missions
    # В тази гилдия няма такива – показваме останалите, вместо да кажем „няма“.
    note = f"в гилдия „{guild}“ няма такива; това са мисиите от другите гилдии" if guild and not in_guild else None
    missions = missions if note else in_guild
    total = missions.count()
    missions = sorted(apply_extensions(user, missions), key=lambda m: (not m.is_homework and m.guild_id not in user.guild_ids, m.deadline))[:MAX_MISSIONS]
    max_xp = GameSettings.load().max_xp_per_mission
    return ToolResult(
        data={
            "own_guilds": [guild.name for guild in user.guilds],
            "total": total, "note": note,
            "missions": [{
                "title": m.title, "guild": None if m.is_homework else m.guild.name,
                "homework_subject": m.subject if m.is_homework else None, "xp": m.xp, "card": _tier(m.xp, max_xp),
                "deadline": _date(m.deadline), "description": m.description[:200],
                "team": f"от {m.team_min} до {m.team_max} ученици" if m.is_group else "индивидуална",
                "special_reward": ", ".join(item.name for item in (m.reward_badge, m.reward_item) if item) or None,
            } for m in missions],
        },
        links=_mission_links(missions) + [Link("Всички мисии", reverse("mission_list"))],
    )


def my_claims(user, arguments):
    claims = list(Claim.objects.filter(student=user).select_related("mission").order_by("-submitted_at")[:8])
    count = {status: sum(c.status == status for c in claims) for status in Claim.Status.values}
    return ToolResult(
        data={"summary": f"върнати за поправяне (отказани): {count['rejected']}, чакат проверка: {count['pending']}, "
                         f"потвърдени: {count['approved']}",
              "claims": [{"mission": c.mission.title, "status": c.get_status_display(), "xp": c.mission.xp,
                          "submitted": _date(c.submitted_at), "as_teammate": c.captain_id is not None}
                         for c in claims]},
        links=_mission_links([c.mission for c in claims]) + [Link("Към мисиите", reverse("mission_list"))],
    )


def shop(user, arguments):
    stats = student_stats(user)
    kinds = dict(Privilege.Kind.choices)
    return ToolResult(
        data={
            "my_coins": stats.coins,
            "my_level": stats.level.number if stats.level else None,
            "items": [{
                "name": item.name, "kind": kinds[item.kind], "description": item.description[:150],
                "price": item.price, "contributor": item.sponsor.name if item.sponsor else None,
                "handed_over_by": "отговорника, вижда се в магазина" if item.handed_over_by else None, "left": item.left,
                "from_level": item.min_level,
                "can_buy_now": is_unlocked(item, stats.level) and stats.coins >= item.price and not item.is_sold_out,
            } for item in active_privileges()],
        },
        links=[Link("Към магазина", reverse("shop"))],
    )


def my_badges(user, arguments):
    cards = badge_cards(user)
    return ToolResult(
        data={
            "earned": [card.badge.name for card in cards if card.earned],
            "next": [{"name": card.badge.name, "how": card.badge.description,
                      "progress": f"{card.value} от {card.badge.threshold}"}
                     for card in sorted((c for c in cards if not c.earned), key=lambda c: -c.percent)[:6]],
        },
        links=[Link("Моят профил", reverse("profile"))],
    )


# ---------- За ученика и учителя ----------

def ranking(user, arguments):
    """Класациите на гилдиите и класовете. От учениците се дава само мястото на питащия."""
    data = {
        "guilds": [{"rank": row.rank, "name": row.name, "xp": row.xp, "members": row.members}
                   for row in leaderboard.guild_ranking()],
        "classes": [{"rank": row.rank, "name": row.name, "xp": row.xp, "average": row.average}
                    for row in leaderboard.class_ranking()],
    }
    if user.is_student:
        mine = next((row for row in leaderboard.student_ranking(limit=None) if row.user.pk == user.pk), None)
        data["my_rank"] = mine.rank if mine else None
        data["my_guilds"] = [guild.name for guild in user.guilds]
        data["my_main_guild"] = user.guild.name if user.guild else None
    return ToolResult(data=data, links=[Link("Класация", reverse("leaderboard"))])


def game_rules(user, arguments):
    """Правилата на играта, както са настроени в момента."""
    rules = GameSettings.load()
    return ToolResult(
        data={
            "asker": "питащият е учител: монети, магазин, подсказки и заявки имат само учениците, затова не му казвай „можеш да купиш“"
                     if not user.is_student else "питащият е ученик",
            "coins": f"{rules.xp_per_coin} XP дават 1 монета, най-много {rules.weekly_coin_limit} монети на седмица",
            "xp_over_limit": "XP се пази винаги, дори когато седмичният лимит на монетите е достигнат",
            "carry_over": "остатъкът под курса се пренася за следващата седмица" if rules.carry_over_remainder
                          else "остатъкът не се пренася",
            "max_xp_per_mission": rules.max_xp_per_mission,
            "cards": "бронзова, сребърна и златна карта според XP на мисията",
            "claim": "ученикът изпълнява мисията и подава заявка с текст или файлове, учителят я потвърждава или отказва; "
                     f"отказана заявка може да се подаде отново поне {rules.resubmit_days} дни, дори срокът да е минал",
            "evidence_files": f"до {rules.evidence_max_files} файла по {rules.evidence_max_mb} MB: снимки, PDF, Word, "
                              "Excel, PowerPoint",
            "teams": "при отборна мисия капитанът подава заявката и изписва псевдонимите на съотборниците; "
                     "всеки получава пълната награда",
            "guilds": f"ученикът е в най-много {MAX_GUILDS} гилдии, едната е основна и неговият XP се брои за нея; "
                      "в гилдия се влиза с входен тест пред учител, с код от него; минава се с поне 80 процента, ако учителят "
                      "не е задал друго; месечният тест е само за членовете и дава XP; кой учител отговаря за всяка гилдия се вижда на страница „Гилдии“",
            "deadlines": f"след срока не се подава; с „Удължен срок“ от магазина ученикът мести срока само за себе си с "
                         f"{rules.extension_days} дни, от страницата на мисията, веднъж за мисия и най-късно "
                         f"{rules.extension_late_days} дни след срока; учителят може да го забрани за мисия; върната заявка "
                         f"може да се поправи поне {rules.resubmit_days} дни след връщането",
            "homework": f"домашните са за определени класове и дават до {rules.max_xp_per_homework} XP за предадена и приета "
                        "работа; не са оценка",
            "levels": [{"level": level.number, "title": level.title, "from_xp": level.min_xp}
                       for level in Level.objects.order_by("min_xp")],
            "streak": "серията брои поредните седмици с поне една потвърдена мисия",
            "nickname": "псевдонимът се сменя от профила"
                        + (f" веднъж на {rules.nickname_change_days} дни" if rules.nickname_change_days else ""),
            "grades": "платформата не влияе на оценките",
        },
        links=[Link("Към мисиите", reverse("mission_list"))],
    )


# ---------- За учителя ----------

def my_missions(user, arguments):
    missions = list(open_first(missions_reviewed_by(user).annotate(
        pending=Count("claims", filter=Q(claims__status=Claim.Status.PENDING, claims__captain__isnull=True)),
        approved=Count("claims", filter=Q(claims__status=Claim.Status.APPROVED)),
        rejected=Count("claims", filter=Q(claims__status=Claim.Status.REJECTED)),
    ))[:MAX_MISSIONS])
    return ToolResult(
        data={"missions": [{
            "title": m.title, "guild": m.source, "xp": m.xp, "deadline": _date(m.deadline),
            "accepts_claims": m.is_open(), "waiting": m.pending, "approved": m.approved,
            "returned": m.rejected,
            "role": "автор" if m.created_by_id == user.pk else "заместник",
        } for m in missions]},
        links=_mission_links(missions) + [Link("Моите мисии", reverse("mission_list"))],
    )


def pending_reviews(user, arguments):
    rows = list(claims_to_decide().filter(mission__in=missions_reviewed_by(user))
                .values("mission_id", "mission__title").annotate(waiting=Count("id"), oldest=Min("submitted_at"))
                .order_by("oldest"))
    return ToolResult(
        data={"total": sum(row["waiting"] for row in rows),
              "by_mission": [{"mission": row["mission__title"], "waiting": row["waiting"],
                              "oldest_days": (timezone.now() - row["oldest"]).days} for row in rows[:MAX_MISSIONS]]},
        links=[Link("Провери заявките", reverse("review_list"))],
    )


def to_hand_over(user, arguments):
    """Колко привилегии и награди чакат да бъдат предадени – без имената на учениците."""
    counts = {}
    for purchase in unused_purchases(user):
        counts[purchase.privilege.name] = counts.get(purchase.privilege.name, 0) + 1
    return ToolResult(
        data={"total": sum(counts.values()), "items": [{"name": name, "count": n} for name, n in counts.items()]},
        links=[Link("Към привилегиите", reverse("purchase_list"))],
    )
