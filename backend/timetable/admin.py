from django.contrib import admin, messages
from django.shortcuts import redirect, render
from django.urls import reverse
from unfold.admin import ModelAdmin
from unfold.decorators import action

from .importer import COLUMNS, import_timetable
from .models import Lesson, Room, Subject


@admin.register(Lesson)
class LessonAdmin(ModelAdmin):
    list_display = ["day", "period", "start_time", "end_time", "school_class", "subject", "teacher_name", "room"]
    list_filter = ["day", "school_class", "room"]
    search_fields = ["subject__name", "teacher_name", "room__name", "school_class__name"]
    actions_list = ["import_csv"]  # бутон над списъка

    @action(description="Внеси от CSV", url_path="import-csv", icon="upload_file")
    def import_csv(self, request):
        """Страница за качване на CSV с разписанието. Заменя цялото разписание."""
        if request.method == "POST" and request.FILES.get("file"):
            try:
                text = request.FILES["file"].read().decode("utf-8-sig")
            except UnicodeDecodeError:
                messages.error(request, "Файлът трябва да е записан в UTF-8 (в Excel: „CSV UTF-8“).")
            else:
                result = import_timetable(text)
                if result.ok:
                    messages.success(request, f"Разписанието е внесено: {result.created} учебни часа.")
                    return redirect(reverse("admin:timetable_lesson_changelist"))
                for error in result.errors[:20]:
                    messages.error(request, error)
                if len(result.errors) > 20:
                    messages.error(request, f"… и още {len(result.errors) - 20} грешки.")

        return render(request, "admin/timetable/import.html", {
            **self.admin_site.each_context(request),
            "title": "Внасяне на разписание",
            "columns": ",".join(COLUMNS),
            "opts": self.model._meta,
        })


@admin.register(Room)
class RoomAdmin(ModelAdmin):
    search_fields = ["name"]


@admin.register(Subject)
class SubjectAdmin(ModelAdmin):
    search_fields = ["name"]
