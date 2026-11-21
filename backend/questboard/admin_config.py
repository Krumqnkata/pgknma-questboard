"""
Помощни функции за темата на администрацията (django-unfold).
Извикват се от настройката UNFOLD в settings.py.
"""
from django.conf import settings


def environment_label(request):
    """Етикет горе вдясно, за да не се бърка локалната версия с публикуваната."""
    if settings.DEBUG:
        return ["Разработка", "warning"]
    return ["Публикувана версия", "success"]


def pending_claims_badge(request):
    """Число до „Заявки“ в менюто: колко заявки чакат проверка."""
    from missions.models import Claim

    count = Claim.objects.filter(status=Claim.Status.PENDING).count()
    return count or None  # при 0 не показваме нищо
