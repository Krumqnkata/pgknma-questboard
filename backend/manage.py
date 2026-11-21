#!/usr/bin/env python
"""Команден ред на Django: миграции, тестове, сървър и др."""
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "questboard.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
