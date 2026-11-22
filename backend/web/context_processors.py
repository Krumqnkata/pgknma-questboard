"""Данни, нужни на всяка страница (броят чакащи заявки, името и логото на училището)."""
from django.urls import reverse

from economy.models import GameSettings
from missions.models import Claim


def navigation(request):
    user = request.user
    if user.is_authenticated and user.is_teacher:
        count = Claim.objects.filter(mission__created_by=user, status=Claim.Status.PENDING).count()
        return {"pending_review_count": count}
    return {}


def school(request):
    """Името и логото на училището от „Настройки на играта“ (ако са качени)."""
    rules = GameSettings.load()
    logo_url = None
    if rules.school_logo:
        # ?v=… се сменя при всяка промяна на настройките – браузърът взима новото лого.
        logo_url = f"{reverse('school_logo')}?v={int(rules.updated_at.timestamp())}"
    return {"school": {"name": rules.school_name, "logo_url": logo_url}}
