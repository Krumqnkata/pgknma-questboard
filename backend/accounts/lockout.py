"""
Защита на входа от отгатване на пароли.

Всеки неуспешен вход се записва (имейл, IP адрес, час). Ако за един имейл има
твърде много грешки за кратко време, входът с него спира за няколко минути –
дори с вярна парола. Така никой не може да пробва хиляди пароли една след друга.

От един IP адрес се позволяват повече грешки, отколкото за един имейл, защото
в училище много ученици излизат в интернет през един и същ рутер.

Ограниченията се променят от администрацията: „Настройки на играта“ → „Защита на входа“.
"""
import logging
import math
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger("questboard.security")

# От един адрес – толкова пъти повече грешки, колкото за един имейл
IP_FACTOR = 4
# Записите по-стари от това се трият, за да не трупа таблицата
KEEP_FOR = timedelta(days=7)


def normalize(email):
    return (email or "").strip().lower()


def client_ip(request):
    """
    IP адресът на потребителя. Зад обратен прокси сървър (DJANGO_BEHIND_PROXY)
    истинският адрес е последният в X-Forwarded-For – него го добавя нашият прокси.
    Иначе заглавката не се чете, защото всеки може да я подправи.
    """
    if request is None:
        return None
    if getattr(settings, "BEHIND_PROXY", False):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[-1].strip() or None
    return request.META.get("REMOTE_ADDR") or None


def _limits():
    from economy.models import GameSettings  # тук, за да няма кръгов import

    game = GameSettings.load()
    return game.login_max_attempts, timedelta(minutes=game.login_lockout_minutes)


def _locked_until(attempts, limit, window):
    """
    Кога изтича забраната. `attempts` са часовете на грешките, най-новите първи.
    Забраната трае, докато грешката с номер `limit` не излезе от прозореца.
    """
    if len(attempts) < limit:
        return None
    return attempts[limit - 1] + window


def minutes_left(email, ip):
    """Колко минути още е спрян входът (0 – не е спрян)."""
    from .models import LoginAttempt

    limit, window = _limits()
    now = timezone.now()
    recent = LoginAttempt.objects.filter(created_at__gt=now - window)

    until = []
    email = normalize(email)
    if email:
        times = list(recent.filter(email=email).values_list("created_at", flat=True)[:limit])
        until.append(_locked_until(times, limit, window))
    if ip:
        ip_limit = limit * IP_FACTOR
        times = list(recent.filter(ip_address=ip).values_list("created_at", flat=True)[:ip_limit])
        until.append(_locked_until(times, ip_limit, window))

    until = [moment for moment in until if moment and moment > now]
    if not until:
        return 0
    return max(1, math.ceil((max(until) - now).total_seconds() / 60))


def record_failure(email, ip):
    """Записва неуспешен опит. Опитите по време на забраната не се броят, за да не я удължават."""
    from .models import LoginAttempt

    if minutes_left(email, ip):
        return
    LoginAttempt.objects.create(email=normalize(email)[:254], ip_address=ip)
    LoginAttempt.objects.filter(created_at__lt=timezone.now() - KEEP_FOR).delete()
    if minutes_left(email, ip):
        logger.warning("Входът е спрян временно: имейл %s, адрес %s", normalize(email), ip)


def clear(email):
    """След успешен вход грешките за този имейл се забравят."""
    from .models import LoginAttempt

    LoginAttempt.objects.filter(email=normalize(email)).delete()
