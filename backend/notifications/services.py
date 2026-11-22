"""Създаване и четене на известия."""
from django.utils import timezone

from .models import Notification

# Толкова последни известия се показват; по-старите остават в базата.
SHOWN = 30


def notify(user, kind, text, link=""):
    return Notification.objects.create(user=user, kind=kind, text=text[:300], link=link)


def unread_count(user):
    return user.notifications.filter(read_at__isnull=True).count()


def recent_for(user):
    return list(user.notifications.all()[:SHOWN])


def mark_all_read(user):
    return user.notifications.filter(read_at__isnull=True).update(read_at=timezone.now())
