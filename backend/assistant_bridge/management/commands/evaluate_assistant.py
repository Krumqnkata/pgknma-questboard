"""
Пуска 20-те контролни случая срещу истинските езикови модели (раздел 3.2 на плана):

    python manage.py evaluate_assistant                    # с реда на доставчиците от admin
    python manage.py evaluate_assistant --provider claude  # само един доставчик
    python manage.py evaluate_assistant --provider all     # всеки от трите поотделно – за сравнение

Нужно е: асистентът да работи (python start.py) и в .env да има API ключ
за доставчика. Всеки случай е една заявка към модела и се плаща по цената
на доставчика.

Проверява се автоматично:
  - подсказка: има отговор и не съдържа думи от готовото решение;
  - чернова: валиден JSON, съществуваща гилдия, XP в лимита;
  - справка: моделът избира очакваната справка.
Резултатът се записва в docs/assistant-evaluation[-доставчик].md – за документацията.
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
PROVIDERS = ["claude", "openai", "gemini"]


def _tools(for_student):
    return [{"name": name, "description": tool["description"], "parameters": tool["parameters"]}
            for name, tool in TOOLS.items()
            if (tool["for_students"] if for_student else not tool.get("only_students"))]


class Command(BaseCommand):
    help = "Пуска контролните случаи на асистента срещу истинските езикови модели."

    def add_arguments(self, parser):
        parser.add_argument("--provider", choices=PROVIDERS + ["all"],
                            help="Само този доставчик (или „all“ – всеки поотделно). По подразбиране – редът от admin.")

    def handle(self, *args, **options):
        rules = GameSettings.load()
        models = {"claude": rules.claude_model, "openai": rules.openai_model, "gemini": rules.gemini_model}

        if not options["provider"]:
            self.evaluate(None, REPORT, "по реда от настройките (с резервни доставчици)")
            return

        for name in PROVIDERS if options["provider"] == "all" else [options["provider"]]:
            if not models[name]:
                self.stdout.write(self.style.WARNING(f"{name}: няма име на модел в настройките – пропуснат."))
                continue
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n=== {name} ({models[name]}) ==="))
            self.evaluate([{"provider": name, "model": models[name]}],
                          REPORT.with_name(f"assistant-evaluation-{name}.md"), f"{name} · {models[name]}")

    def evaluate(self, providers, report_path, label):
        """providers=None означава реда от настройките; иначе – само дадените доставчици."""
        self.providers = providers
        cases = json.loads(CASES.read_text(encoding="utf-8"))
        rows = []

        for case in cases["hints"]:
            rows.append(self.run_case(case["id"], "подсказка", lambda c=case: self.check_hint(c)))
        for case in cases["drafts"]:
            rows.append(self.run_case(case["id"], "чернова", lambda c=case: self.check_draft(c, cases)))
        for case in cases["queries"]:
            rows.append(self.run_case(case["id"], "справка", lambda c=case: self.check_query(c)))

        passed = sum(1 for row in rows if row["ok"])
        self.write_report(rows, passed, report_path, label)
        style = self.style.SUCCESS if passed == len(rows) else self.style.WARNING
        self.stdout.write(style(f"Минали: {passed} от {len(rows)}. Отчет: {report_path}"))

    def run_case(self, case_id, kind, check):
        started = time.monotonic()
        try:
            ok, note, provider = check()
        except client.AssistantUnavailable as error:
            ok, note, provider = False, f"грешка: {error}", ""
        seconds = time.monotonic() - started
        self.stdout.write(f"{case_id:4} {kind:10} {'✓' if ok else '✗'} {seconds:5.1f} s  {note[:90]}")
        return {"id": case_id, "kind": kind, "ok": ok, "note": note, "seconds": seconds, "provider": provider}

    def check_hint(self, case):
        answer = client.call("/hint", {"mission": case["mission"]}, self.providers)
        hint = answer["hint"]
        leaked = [word for word in case["forbidden"] if word.lower() in hint.lower()]
        if leaked:
            return False, f"съдържа решението ({', '.join(leaked)}): {hint}", answer.get("provider", "")
        return bool(hint.strip()), hint, answer.get("provider", "")

    def check_draft(self, case, cases):
        draft = client.call("/mission-draft", {"idea": case["idea"], "guilds": cases["guilds"],
                                               "max_xp": cases["max_xp"]}, self.providers)
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
        return not problems, ("; ".join(problems) + " – " if problems else "") + note, draft.get("provider", "")

    def check_query(self, case):
        plan = client.call("/query/plan", {
            "question": case["question"],
            "tools": _tools(for_student=case["role"] == "ученик"),
            "context": {"today": "вторник", "now_period": "2", "role": case["role"]},
        }, self.providers)
        chosen = plan.get("tool")
        return (chosen == case["expected_tool"], f"избрана: {chosen}, очаквана: {case['expected_tool']}",
                plan.get("provider", ""))

    def write_report(self, rows, passed, report_path, label):
        lines = [
            "# Контролни случаи на асистента",
            "",
            f"Дата: {timezone.localtime():%d.%m.%Y %H:%M} · Модел: {label}",
            "",
            f"**Резултат: {passed} от {len(rows)} минали.**",
            "",
            "| № | Вид | Резултат | Отговорил | Време | Бележка |",
            "|---|---|---|---|---|---|",
        ]
        for row in rows:
            note = row["note"].replace("|", "/").replace("\n", " ")
            lines.append(f"| {row['id']} | {row['kind']} | {'✓' if row['ok'] else '✗'} | {row['provider']} | "
                         f"{row['seconds']:.1f} s | {note} |")
        report_path.parent.mkdir(exist_ok=True)
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
