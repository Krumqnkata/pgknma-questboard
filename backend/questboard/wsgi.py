"""Входна точка за уеб сървър при публикуване (напр. gunicorn или waitress)."""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "questboard.settings")

application = get_wsgi_application()
