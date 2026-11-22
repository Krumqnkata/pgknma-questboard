from django.apps import AppConfig


class MissionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "missions"
    verbose_name = "Мисии и заявки"

    def ready(self):
        from . import signals  # noqa: F401 – трие файловете от диска заедно със записите
