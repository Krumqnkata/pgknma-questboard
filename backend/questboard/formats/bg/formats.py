"""Датите се пишат и по български (15.12.2026), не само по ISO. Останалите формати са надолу."""
DATE_INPUT_FORMATS = ["%d.%m.%Y", "%Y-%m-%d", "%d.%m.%y"]
TIME_INPUT_FORMATS = ["%H:%M", "%H:%M:%S", "%H:%M:%S.%f"]
DATETIME_INPUT_FORMATS = ["%d.%m.%Y %H:%M", "%d.%m.%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M"]

# Как се показват в администрацията: „15.12.2026, 23:59“ вместо „Дек. 15, 2026, 11:59 след обяд“.
DATE_FORMAT = "d.m.Y"
TIME_FORMAT = "H:i"
DATETIME_FORMAT = "d.m.Y, H:i"
SHORT_DATE_FORMAT = "d.m.Y"
SHORT_DATETIME_FORMAT = "d.m.Y H:i"
FIRST_DAY_OF_WEEK = 1
