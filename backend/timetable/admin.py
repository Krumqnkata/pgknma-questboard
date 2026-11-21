from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Lesson, Room, Subject


@admin.register(Lesson)
class LessonAdmin(ModelAdmin):
    list_display = ["day", "period", "start_time", "end_time", "school_class", "subject", "teacher", "room"]
    list_filter = ["day", "school_class", "room"]
    search_fields = ["subject__name", "teacher__first_name", "teacher__last_name", "room__name"]


@admin.register(Room)
class RoomAdmin(ModelAdmin):
    search_fields = ["name"]


@admin.register(Subject)
class SubjectAdmin(ModelAdmin):
    search_fields = ["name"]
