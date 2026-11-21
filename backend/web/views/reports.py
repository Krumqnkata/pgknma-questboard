"""
Страница „Справки“ по разписанието (Ф17, Ф18, Ф22) – без асистента.

Същите справки ги прави и асистентът. Тази страница е резервният вариант
от плана: работи и когато асистентът е изключен.
"""
from django.shortcuts import render

from accounts.models import SchoolClass, User
from accounts.permissions import role_required
from timetable import queries

STUDENT = User.Role.STUDENT
TEACHER = User.Role.TEACHER

REPORTS = {
    "teacher_schedule": "Часове на учител",
    "teacher_free_periods": "Свободни часове на учител",
    "substitutes": "Кой може да замести",
    "class_schedule": "Часове на клас",
    "free_rooms": "Свободни кабинети",
}


@role_required(STUDENT, TEACHER)
def reports(request):
    user = request.user
    report = request.GET.get("report", "")
    params = {
        "teacher": request.GET.get("teacher", ""),
        "class_name": request.GET.get("class_name", "") or (str(user.school_class) if user.is_student else ""),
        "day": request.GET.get("day", ""),
        "period": request.GET.get("period", ""),
    }
    allowed = {key: title for key, title in REPORTS.items()
               if not user.is_student or key in queries.CLASS_REPORTS}

    result, error = None, None
    if report in allowed:
        try:
            result = queries.run_report(user, report, params)
        except queries.QueryError as exc:
            error = str(exc)

    return render(request, "web/reports.html", {
        "reports": allowed, "report": report, "params": params, "result": result, "error": error,
        "teachers": queries.teacher_names() if not user.is_student else [],
        "classes": SchoolClass.objects.all() if not user.is_student else [],
        "days": queries.DAY_NAMES.values(),
    })

