"""Общо четене на CSV файлове (разписание, потребители)."""
import csv
import io


def read_csv_rows(text):
    """
    Връща редовете като речници {колона: стойност}.
    Разпознава разделителя: Excel с български настройки записва с „;“ вместо „,“.
    """
    text = text.lstrip("﻿")  # BOM, който Excel добавя в началото
    try:
        dialect = csv.Sniffer().sniff(text.splitlines()[0], delimiters=",;	")
    except (csv.Error, IndexError):
        dialect = csv.excel
    return list(csv.DictReader(io.StringIO(text), dialect=dialect))
