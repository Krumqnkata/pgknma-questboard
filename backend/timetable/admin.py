from django.contrib import admin

from .models import Lesson, Room, Subject


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ["day", "period", "start_time", "end_time", "school_class", "subject", "teacher", "room"]
    list_filter = ["day", "school_class", "room"]
    search_fields = ["subject__name", "teacher__first_name", "teacher__last_name", "room__name"]


admin.site.register(Room)
admin.site.register(Subject)
