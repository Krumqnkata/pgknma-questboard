"""
Пуска 20-те контролни случая срещу истинския езиков модел (раздел 3.2 на плана):

    python manage.py evaluate_assistant

Нужно е: асистентът да работи (python start.py) и в .env да има API ключ
за доставчика, избран в администрацията. Всеки случай е една заявка към модела
и се плаща по цената на доставчика.

Проверява се автоматично:
  - подсказка: има отговор и не съдържа думи от готовото решение;
  - чернова: валиден JSON, съществуваща гилдия, XP в лимита;
  - справка: моделът избира очакваната справка.
Резултатът се записва в docs/assistant-evaluation.md – за документацията.
Подсказките трябва и да се прочетат от човек: таблицата ги съдържа.
"""
import json
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from assistant_bridge import client
from assistant_bridge.tools import TOOLS
from economy.models import GameSettings

CASES = Path(__file__).resolve().parents[2] / "evaluation" / "cases.json"
REPORT = Path(settings.PROJECT_ROOT) / "docs" / "assistant-evaluation.md"


def _tools(for_student):
    return [{"name": name, "description": tool["description"], "parameters": tool["parameters"]}
            for name, tool in TOOLS.items()
            if (tool["for_students"] if for_student else not tool.get("only_students"))]


class Command(BaseCommand):
    help = "Пуска контролните случаи на асистента срещу истинския езиков модел."

    def handle(self, *args, **options):
        cases = json.loads(CASES.read_text(encoding="utf-8"))
        rows = []

        for case in cases["hints"]:
            rows.append(self.run_case(case["id"], "подсказка", lambda c=case: self.check_hint(c)))
        for case in cases["drafts"]:
            rows.append(self.run_case(case["id"], "чернова", lambda c=case: self.check_draft(c, cases)))
        for case in cases["queries"]:
            rows.append(self.run_case(case["id"], "справка", lambda c=case: self.check_query(c)))

        passed = sum(1 for row in rows if row["ok"])
        self.write_report(rows, passed)
        style = self.style.SUCCESS if passed == len(rows) else self.style.WARNING
        self.stdout.write(style(f"\nМинали: {passed} от {len(rows)}. Отчет: {REPORT}"))

    def run_case(self, case_id, kind, check):
        started = time.monotonic()
        try:
            ok, note = check()
        except client.AssistantUnavailable as error:
            ok, note = False, f"грешка: {error}"
        seconds = time.monotonic() - started
        self.stdout.write(f"{case_id:4} {kind:10} {'✓' if ok else '✗'} {seconds:5.1f} s  {note[:90]}")
        return {"id": case_id, "kind": kind, "ok": ok, "note": note, "seconds": seconds}

    def check_hint(self, case):
        hint = client.call("/hint", {"mission": case["mission"]})["hint"]
        leaked = [word for word in case["forbidden"] if word.lower() in hint.lower()]
        if leaked:
            return False, f"съдържа решението ({', '.join(leaked)}): {hint}"
        return bool(hint.strip()), hint

    def check_draft(self, case, cases):
        draft = client.call("/mission-draft", {"idea": case["idea"], "guilds": cases["guilds"],
                                               "max_xp": cases["max_xp"]})
        names = {guild["name"] for guild in cases["guilds"]}
        problems = []
        if draft.get("guild") not in names:
            problems.append("непозната гилдия")
        if not 1 <= int(draft.get("xp", 0)) <= cases["max_xp"]:
            problems.append("XP извън лимита")
        for field in ("title", "description", "criteria"):
            if not str(draft.get(field, "")).strip():
                problems.append(f"празно поле {field}")
        note = f"{draft.get('title')} · {draft.get('guild')} · {draft.get('xp')} XP"
        return not problems, ("; ".join(problems) + " – " if problems else "") + note

    def check_query(self, case):
        plan = client.call("/query/plan", {
            "question": case["question"],
            "tools": _tools(for_student=case["role"] == "ученик"),
            "context": {"today": "вторник", "now_period": "2", "role": case["role"]},
        })
        chosen = plan.get("tool")
        return chosen == case["expected_tool"], f"избрана: {chosen}, очаквана: {case['expected_tool']}"

    def write_report(self, rows, passed):
        rules = GameSettings.load()
        lines = [
            "# Контролни случаи на асистента",
            "",
            f"Дата: {timezone.localtime():%d.%m.%Y %H:%M} · Доставчик: {rules.get_llm_provider_display()} · "
            f"Модел: {rules.llm_model or 'по подразбиране'}",
            "",
            f"**Резултат: {passed} от {len(rows)} минали.**",
            "",
            "| № | Вид | Резултат | Време | Бележка |",
            "|---|---|---|---|---|",
        ]
        for row in rows:
            note = row["note"].replace("|", "/").replace("\n", " ")
            lines.append(f"| {row['id']} | {row['kind']} | {'✓' if row['ok'] else '✗'} | "
                         f"{row['seconds']:.1f} s | {note} |")
        REPORT.parent.mkdir(exist_ok=True)
        REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
