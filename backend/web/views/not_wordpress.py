"""
Шега за ботовете: Questboard не е WordPress.

Ботове по цял ден пробват /wp-admin/, /wp-login.php, /xmlrpc.php и подобни
на всеки сайт с надежда да намерят стар WordPress. Тук те получават страница
„Това не е WordPress“ с код 418 („Аз съм чайник“ – шегата от RFC 2324),
а броят на опитите за деня се пази за таблото на администрацията.

Нарочно няма форма и поле за парола: нищо не се приема и не се чете от
заявката – дори някой по навик да опита да „влезе“, нищо не стига до нас.
"""
from django.db import IntegrityError
from django.db.models import F
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from ..models import BotKnock


def count_knock():
    """+1 за днешния ден. Без IP адреси и без други данни за посетителя."""
    today = timezone.localdate()
    if not BotKnock.objects.filter(day=today).update(hits=F("hits") + 1):
        try:
            BotKnock.objects.create(day=today, hits=1)
        except IntegrityError:  # две заявки едновременно създават деня
            BotKnock.objects.filter(day=today).update(hits=F("hits") + 1)


@csrf_exempt  # ботовете пращат и POST; без това биха получили грешка 403 вместо шегата
def not_wordpress(request, rest=""):
    count_knock()
    return render(request, "web/not_wordpress.html", status=418)
