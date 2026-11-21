"""Тестове за внасянето на разписанието и справките Ф17, Ф18, Ф22."""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from accounts.models import SchoolClass
from accounts.testing import make_student, make_teacher

from . import queries
from .importer import import_timetable
from .models import Lesson

SAMPLE = Path(settings.BASE_DIR) / "timetable" / "sample" / "razpisanie_primer.csv"
SOFIA = ZoneInfo("Europe/Sofia")
MONDAY_2ND_PERIOD = datetime(2026, 11, 23, 9, 0, tzinfo=SOFIA)   # понеделник, 2 час
SATURDAY = datetime(2026, 11, 21, 10, 0, tzinfo=SOFIA)

HEADER = "ден,час,начало,край,клас,предмет,учител,кабинет\n"


class ImportTests(TestCase):
    def test_sample_file_imports(self):
        result = import_timetable(SAMPLE.read_text(encoding="utf-8"))
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(Lesson.objects.count(), result.created)

    def test_semicolon_separator_from_excel(self):
        text = HEADER.replace(",", ";") + "понеделник;1;08:00;08:40;11Б;Математика;Петър Николов;203\n"
        self.assertTrue(import_timetable(text).ok)

    def test_errors_list_row_numbers_and_nothing_is_imported(self):
        text = HEADER + "понеделник,1,08:00,08:40,11Б,Математика,Петър Николов,203\n" \
                        "събота,1,08:00,08:40,11Б,Математика,Петър Николов,203\n" \
                        "вторник,2,09:00,08:00,11Б,Математика,Петър Николов,203\n"
        result = import_timetable(text)
        self.assertFalse(result.ok)
        self.assertTrue(any("Ред 3" in e for e in result.errors))
        self.assertTrue(any("Ред 4" in e for e in result.errors))
        self.assertEqual(Lesson.objects.count(), 0)

    def test_missing_column(self):
        result = import_timetable("ден,час\nпонеделник,1\n")
        self.assertIn("Липсват колони", result.errors[0])

    def test_teacher_account_is_linked_by_name(self):
        teacher = make_teacher()
        teacher.first_name, teacher.last_name = "Петър", "Николов"
        teacher.save()
        import_timetable(HEADER + "понеделник,1,08:00,08:40,11Б,Математика,Петър Николов,203\n")
        self.assertEqual(Lesson.objects.get().teacher, teacher)


class QueryTests(TestCase):
    def setUp(self):
        import_timetable(SAMPLE.read_text(encoding="utf-8"))

    def test_now_slot(self):
        self.assertEqual(queries.now_slot(MONDAY_2ND_PERIOD), {"day": 0, "period": 2})
        self.assertEqual(queries.now_slot(SATURDAY)["day"], None)

    def test_resolve_teacher_by_surname(self):
        self.assertEqual(queries.resolve_teacher("маринова"), "Елена Маринова")

    def test_unknown_teacher(self):
        with self.assertRaises(queries.QueryError):
            queries.resolve_teacher("Несъществуващ")

    def test_teacher_schedule_for_day(self):
        result = queries.teacher_schedule("Маринова", "понеделник")
        self.assertTrue(result["lessons"])
        self.assertTrue(all(lesson["teacher"] == "Елена Маринова" for lesson in result["lessons"]))

    def test_free_periods_do_not_overlap_lessons(self):
        busy = {x["period"] for x in queries.teacher_schedule("Маринова", "вторник")["lessons"]}
        free = {x["period"] for x in queries.teacher_free_periods("Маринова", "вторник")["free_periods"]}
        self.assertFalse(busy & free)

    def test_substitutes_are_free_at_that_time(self):
        result = queries.substitutes("Маринова", "понеделник", 2)
        busy = set(Lesson.objects.filter(day=0, period=2).values_list("teacher_name", flat=True))
        for name in result["same_subject"] + result["other_free"]:
            self.assertNotIn(name, busy)

    def test_class_now(self):
        result = queries.class_schedule("11б", now=MONDAY_2ND_PERIOD, day="днес", period="2")
        self.assertEqual(result["class"], "11Б")
        self.assertEqual(len(result["lessons"]), 1)

    def test_free_rooms_exclude_used_rooms(self):
        result = queries.free_rooms("понеделник", 2)
        used = set(Lesson.objects.filter(day=0, period=2).values_list("room__name", flat=True))
        self.assertFalse(used & set(result["rooms"]))
        self.assertTrue(result["rooms"])

    def test_weekend_is_rejected(self):
        with self.assertRaises(queries.QueryError):
            queries.parse_day("събота")


class AccessTests(TestCase):
    def setUp(self):
        import_timetable(SAMPLE.read_text(encoding="utf-8"))
        self.student = make_student()  # клас 11А по подразбиране в тестовете
        self.teacher = make_teacher()

    def test_student_cannot_query_teachers(self):
        with self.assertRaises(queries.QueryError):
            queries.run_report(self.student, "teacher_schedule", {"teacher": "Маринова"})

    def test_student_cannot_query_another_class(self):
        with self.assertRaises(queries.QueryError):
            queries.run_report(self.student, "class_schedule", {"class_name": "10А", "day": "понеделник"})

    def test_student_gets_own_class_by_default(self):
        self.student.school_class = SchoolClass.objects.get(name="11Б")
        self.student.save()
        result = queries.run_report(self.student, "class_schedule", {"day": "понеделник"})
        self.assertEqual(result["class"], "11Б")

    def test_teacher_can_query_free_rooms(self):
        result = queries.run_report(self.teacher, "free_rooms", {"day": "сряда", "period": "3"})
        self.assertIn("rooms", result)


class ReportPagesTests(TestCase):
    def setUp(self):
        import_timetable(SAMPLE.read_text(encoding="utf-8"))
        self.teacher = make_teacher()

    def test_reports_page(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("reports"), {"report": "free_rooms", "day": "сряда", "period": "3"})
        self.assertContains(response, "Свободни кабинети")

    def test_reports_api(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("api-report", args=["teacher_schedule"]),
                                   {"teacher": "Маринова", "day": "понеделник"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["teacher"], "Елена Маринова")

    def test_reports_api_refuses_student_teacher_report(self):
        self.client.force_login(make_student())
        response = self.client.get(reverse("api-report", args=["free_rooms"]), {"day": "сряда", "period": "3"})
        self.assertEqual(response.status_code, 400)


class AdminImportTests(TestCase):
    def setUp(self):
        from accounts.models import User
        self.client.force_login(User.objects.create_superuser("admin@example.com", "TaynaParola123"))

    def test_import_page_opens(self):
        response = self.client.get(reverse("admin:timetable_lesson_import_csv"))
        self.assertContains(response, "Внасяне на разписание")

    def test_upload_csv(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        upload = SimpleUploadedFile("razpisanie.csv", SAMPLE.read_bytes(), content_type="text/csv")
        response = self.client.post(reverse("admin:timetable_lesson_import_csv"), {"file": upload}, follow=True)
        self.assertContains(response, "Разписанието е внесено")
        self.assertTrue(Lesson.objects.exists())
