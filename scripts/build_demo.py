#!/usr/bin/env python3
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "interface_validation_lab"
sys.path.insert(0, str(LAB))
from research_flow import build_tree_test, prepare, summarize_tree_test  # noqa: E402


def svg(title, color):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 390 720"><rect width="390" height="720" fill="#f7f2e9"/><rect x="24" y="30" width="342" height="64" rx="16" fill="{color}"/><text x="45" y="70" font-family="Arial" font-size="24" fill="#1e2027">{title}</text><rect x="24" y="120" width="342" height="190" rx="18" fill="#fff"/><rect x="24" y="330" width="164" height="140" rx="18" fill="#fff"/><rect x="202" y="330" width="164" height="140" rx="18" fill="#fff"/></svg>'''


def main():
    out = ROOT / "demo"
    with tempfile.TemporaryDirectory() as temp:
        study = Path(temp) / "pulse-interface-study"
        (study / "screens").mkdir(parents=True)
        (study / "screens" / "Главная.svg").write_text(svg("Пульс · Главная", "#ff7055"), encoding="utf-8")
        (study / "screens" / "Расписание.svg").write_text(svg("Рабочее расписание", "#90c6aa"), encoding="utf-8")
        (study / "ia.md").write_text("""# Информационная архитектура

## Дерево

- Пульс
  - Главная
  - Рабочий день
    - Расписание
    - Смены
  - Команда
    - Сотрудники
    - Приглашения
  - Профиль
""", encoding="utf-8")
        (study / "user_flow.md").write_text("Руководитель открывает расписание и проверяет смену сотрудника.\n", encoding="utf-8")
        prepare(study)
        research = study / "research"
        (research / "tree_tasks.json").write_text(json.dumps({"tasks": [
            {"id": "T-01", "prompt": "Вы хотите узнать, кто работает завтра утром. Где будете искать?", "targetLabel": "Расписание"},
            {"id": "T-02", "prompt": "Нужно пригласить нового сотрудника. Где начнёте?", "targetLabel": "Приглашения"},
        ]}, ensure_ascii=False, indent=2), encoding="utf-8")
        (research / "questionnaire.md").write_text("# Проверка экранов\n\n1. Найдите смену на завтра.\n2. Покажите, где пригласить сотрудника.\n", encoding="utf-8")
        build_tree_test(study)
        config = json.loads((research / "tree_study.json").read_text(encoding="utf-8"))
        sessions = [
            ("R1", [("T-01", True, 1, "Главная", ["Пульс", "Рабочий день", "Расписание"], 25), ("T-02", True, 0, "Команда", ["Пульс", "Команда", "Приглашения"], 12)]),
            ("R2", [("T-01", True, 0, "Рабочий день", ["Пульс", "Рабочий день", "Расписание"], 14), ("T-02", False, 2, "Профиль", ["Пульс", "Профиль"], 31)]),
        ]
        for participant, rows in sessions:
            payload = {"schemaVersion": 1, "studyId": config["id"], "participantId": participant, "results": []}
            for task, success, backtracks, first, path, seconds in rows:
                payload["results"].append({"taskId": task, "success": success, "backtracks": backtracks, "firstChoiceLabel": first, "pathLabels": path, "durationSeconds": seconds})
            (research / "tree_responses" / f"{participant}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        summarize_tree_test(study)
        out.mkdir(exist_ok=True)
        for name in ("tree_test.html", "gallery.html", "tree_testing.md"):
            shutil.copy2(research / name, out / name)
    print(f"Demo built in {out}")

if __name__ == "__main__":
    main()
