"""Последно раздадените награди: значки, бонус XP и предмети от мисии (за таблото и началната страница)."""
from dataclasses import dataclass
from datetime import datetime

from accounts.models import User
from badges.models import StudentBadge

from .models import Purchase, XPTransaction


@dataclass
class Award:
    student: User
    kind: str       # „значка“, „бонус“ или „награда“
    text: str
    note: str
    at: datetime


def recent_awards(limit=8):
    """
    Най-новите награди от трите вида, смесени по време. Отменените не се показват.
    За учениците в страниците се показва само псевдонимът.
    """
    badges = (StudentBadge.objects.filter(student__is_active=True)
              .select_related("student__guild", "badge").order_by("-awarded_at")[:limit])
    bonuses = (XPTransaction.objects.filter(student__is_active=True, is_bonus=True, amount__gt=0, reversal__isnull=True)
               .select_related("student__guild").order_by("-created_at")[:limit])
    items = (Purchase.objects.filter(student__is_active=True, claim__isnull=False)
             .select_related("student__guild", "privilege", "claim__mission").order_by("-purchased_at")[:limit])
    awards = [Award(row.student, "значка", row.badge.name, row.note, row.awarded_at) for row in badges]
    awards += [Award(row.student, "бонус", f"+{row.amount} XP", row.reason.removeprefix("Бонус: "), row.created_at)
               for row in bonuses]
    awards += [Award(row.student, "награда", row.privilege.name, f"Мисия „{row.claim.mission.title}“",
                     row.purchased_at) for row in items]
    return sorted(awards, key=lambda award: award.at, reverse=True)[:limit]
