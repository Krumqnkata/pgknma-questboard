"""
„Проверка на системата“: намира проблеми в данните и предлага поправка.

Проблемите се откриват с обикновени правила (тук), а не от езиковия модел – така
резултатът е сигурен и се тества. Асистентът само обяснява намереното и подрежда
кое е най-важно. Нищо не се променя, докато администраторът не натисне „Приложи“,
а всяка поправка се записва в журнала на администрацията.

Поправките са само тези от FIXES. Асистентът не може да измисли друга.
"""
from dataclasses import dataclass
from datetime import timedelta

from django.db.models import Count, F, Q, Sum
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from assistant_bridge.models import AssistantLog
from economy.models import Level, Privilege
from economy.services import owned_cosmetics
from missions.models import Claim, Mission
from missions.services import claims_to_decide

WAITING_DAYS = 3


@dataclass
class Problem:
    code: str
    title: str
    count: int
    advice: str          # какво да се направи (без имена – този текст вижда и асистентът)
    link: str = ""       # къде в администрацията
    fix_label: str = ""  # надписът на бутона; празно – поправя се само ръчно


# ---------- Заявки за всеки проблем ----------

def expired_missions():
    return Mission.objects.filter(is_active=True, deadline__lt=timezone.now())


def sold_out_items():
    return (Privilege.objects.filter(is_active=True, stock__isnull=False)
            .annotate(sold=Count("purchases")).filter(sold__gte=F("stock")))


def wrong_reviewers():
    """Връзки „мисия – заместник“, при които заместникът вече не е активен учител."""
    return Mission.reviewers.through.objects.filter(
        Q(user__is_active=False) | ~Q(user__role=User.Role.TEACHER))


def students_with_wrong_look():
    """Ученици, които носят титла или рамка, без да я притежават."""
    wrong = []
    worn = User.objects.filter(role=User.Role.STUDENT).filter(
        Q(shown_title__isnull=False) | Q(shown_frame__isnull=False))
    for student in worn:
        owned = set(owned_cosmetics(student).values_list("pk", flat=True))
        if {student.shown_title_id, student.shown_frame_id} - {None} - owned:
            wrong.append((student, owned))
    return wrong


def find_problems():
    """Всички намерени проблеми. Празен списък – всичко е наред."""
    now = timezone.now()
    students = User.objects.filter(role=User.Role.STUDENT, is_active=True)
    late = claims_to_decide().filter(submitted_at__lt=now - timedelta(days=WAITING_DAYS))
    abandoned = claims_to_decide().filter(mission__created_by__is_active=False).exclude(
        mission__reviewers__is_active=True)
    small_teams = claims_to_decide().filter(mission__is_group=True).annotate(size=Count("team") + 1).filter(
        size__lt=F("mission__team_min"))
    no_xp = Claim.objects.filter(status=Claim.Status.APPROVED).exclude(xp_transactions__amount__gt=0)
    debt = students.annotate(coins=Sum("coin_transactions__amount")).filter(coins__lt=0)
    errors = AssistantLog.objects.filter(success=False, created_at__gte=now - timedelta(days=7))

    claims_link = reverse("admin:missions_claim_changelist") + "?status__exact=pending"
    missions_link = reverse("admin:missions_mission_changelist")
    users_link = reverse("admin:accounts_user_changelist") + "?role__exact=student"
    found = [
        Problem("abandoned_claims", "Заявки, които никой не може да провери", abandoned.distinct().count(),
                "Авторът на мисията вече не е активен и няма заместник. Добавете заместник към мисията.", claims_link),
        Problem("late_claims", f"Заявки, чакащи над {WAITING_DAYS} дни", late.count(),
                "Напомнете на учителите или добавете заместници към мисиите.", claims_link),
        Problem("claims_without_xp", "Потвърдени заявки без начислен XP", no_xp.count(),
                "Състоянието е променено извън правилата на играта. Прегледайте заявките.",
                reverse("admin:missions_claim_changelist") + "?status__exact=approved"),
        Problem("no_start_level", "Няма ниво от 0 XP", 0 if Level.objects.filter(min_xp=0).exists() else 1,
                "Новите ученици са без ниво. Добавете ниво с 0 XP.", reverse("admin:economy_level_changelist")),
        Problem("no_guild", "Ученици без гилдия", students.filter(guild__isnull=True).count(),
                "Могат да влязат с входен тест или гилдията да се попълни ръчно.", users_link),
        Problem("no_class", "Ученици без клас", students.filter(school_class__isnull=True).count(),
                "Попълнете класа – без него няма разписание и класация на класа.", users_link),
        Problem("expired_missions", "Активни мисии с изтекъл срок", expired_missions().count(),
                "Не приемат заявки. Могат да се спрат; чакащите заявки по тях пак се проверяват.",
                missions_link + "?is_active__exact=1", "Спри мисиите"),
        Problem("sold_out", "Изчерпани предмети, които още се предлагат", sold_out_items().count(),
                "Могат да се скрият от магазина.", reverse("admin:economy_privilege_changelist"), "Скрий от магазина"),
        Problem("wrong_reviewers", "Заместници, които вече не са активни учители", wrong_reviewers().count(),
                "Могат да се махнат от мисиите – и без това нямат право да проверяват.", missions_link,
                "Махни заместниците"),
        Problem("wrong_look", "Ученици с титла или рамка, която нямат", len(students_with_wrong_look()),
                "Могат да се махнат от профила.", users_link, "Махни от профила"),
        Problem("small_teams", "Отбори, останали под минималния брой", small_teams.count(),
                "Съотборник е напуснал. Учителят решава дали да приеме заявката.", claims_link),
        Problem("coin_debt", "Ученици с отрицателен брой монети", debt.count(),
                "Отменена е награда, от която монетите вече са похарчени. Изравнява се със следващите мисии.",
                reverse("admin:economy_cointransaction_changelist")),
        Problem("assistant_errors", "Грешки на асистента за 7 дни", errors.count(),
                "Проверете ключа и модела с бутона „Провери асистента“ в „Настройки на играта“.",
                reverse("admin:assistant_bridge_assistantlog_changelist") + "?success__exact=0"),
    ]
    return [problem for problem in found if problem.count]


# ---------- Поправките ----------

def fix_expired_missions():
    return expired_missions().update(is_active=False, updated_at=timezone.now())


def fix_sold_out():
    pks = list(sold_out_items().values_list("pk", flat=True))  # MySQL не позволява промяна със същата подзаявка
    return Privilege.objects.filter(pk__in=pks).update(is_active=False)


def fix_wrong_reviewers():
    pks = list(wrong_reviewers().values_list("pk", flat=True))
    Mission.reviewers.through.objects.filter(pk__in=pks).delete()
    return len(pks)


def fix_wrong_look():
    students = students_with_wrong_look()
    for student, owned in students:
        if student.shown_title_id not in owned:
            student.shown_title = None
        if student.shown_frame_id not in owned:
            student.shown_frame = None
        student.save(update_fields=["shown_title", "shown_frame"])
    return len(students)


FIXES = {
    "expired_missions": fix_expired_missions,
    "sold_out": fix_sold_out,
    "wrong_reviewers": fix_wrong_reviewers,
    "wrong_look": fix_wrong_look,
}
