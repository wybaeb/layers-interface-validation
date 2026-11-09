import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research_flow import (  # noqa: E402
    build_tree_test,
    parse_ia,
    prepare,
    summarize_tree_test,
    validate_tree_report,
)


def svg(label: str) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100"><text x="10" y="30">{label}</text></svg>'


class ResearchFlowCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.study = Path(self.tmp.name) / "pulse-study"
        (self.study / "screens").mkdir(parents=True)
        (self.study / "screens" / "Главная.svg").write_text(svg("Главная"), encoding="utf-8")
        (self.study / "screens" / "Расписание.svg").write_text(svg("Расписание"), encoding="utf-8")
        (self.study / "ia.md").write_text(
            "# Информационная архитектура\n\n## Дерево\n\n- Пульс\n  - Главная\n  - Работа\n    - Расписание\n    - Команда\n  - Профиль\n",
            encoding="utf-8",
        )
        (self.study / "user_flow.md").write_text("Родитель открывает расписание.", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_parse_ia_preserves_hierarchy_without_student_ids(self):
        tree = parse_ia((self.study / "ia.md").read_text(encoding="utf-8"))
        self.assertEqual(tree.label, "Пульс")
        self.assertEqual([child.label for child in tree.children], ["Главная", "Работа", "Профиль"])
        self.assertEqual([child.label for child in tree.children[1].children], ["Расписание", "Команда"])

    def test_full_tree_flow_creates_autonomous_runner_and_report(self):
        with contextlib.redirect_stdout(io.StringIO()):
            prepare(self.study)
        research = self.study / "research"
        self.assertTrue((research / "gallery.html").is_file())
        gallery = (research / "gallery.html").read_text(encoding="utf-8")
        self.assertIn("data:image/svg+xml;base64,", gallery)
        self.assertIn("Content-Security-Policy", gallery)
        self.assertTrue((research / "prepare_tasks_prompt.md").is_file())
        (research / "tree_tasks.json").write_text(json.dumps({"tasks": [
            {"id": "T-01", "prompt": "Где посмотреть рабочее расписание?", "targetLabel": "Расписание"},
            {"id": "T-02", "prompt": "Где изменить данные аккаунта?", "targetLabel": "Профиль"},
        ]}, ensure_ascii=False), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            build_tree_test(self.study)
        runner = (research / "tree_test.html").read_text(encoding="utf-8")
        self.assertIn("Скачать результат", runner)
        self.assertNotIn("targetLabel", runner)
        config = json.loads((research / "tree_study.json").read_text(encoding="utf-8"))
        responses = research / "tree_responses"
        (responses / "R1.json").write_text(json.dumps({
            "schemaVersion": 1,
            "studyId": config["id"],
            "participantId": "R1",
            "results": [
                {"taskId": "T-01", "success": True, "backtracks": 1, "firstChoiceLabel": "Главная", "pathLabels": ["Пульс", "Работа", "Расписание"], "durationSeconds": 22},
                {"taskId": "T-02", "success": True, "backtracks": 0, "firstChoiceLabel": "Профиль", "pathLabels": ["Пульс", "Профиль"], "durationSeconds": 9},
            ],
        }, ensure_ascii=False), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            summarize_tree_test(self.study)
        report = (research / "tree_testing.md").read_text(encoding="utf-8")
        self.assertIn("1/1", report)
        self.assertIn("Пульс → Работа → Расписание", report)
        self.assertIn("Наблюдения и решения", report)
        self.assertEqual((research / "ia_after_tree_testing.md").read_text(encoding="utf-8"), (self.study / "ia.md").read_text(encoding="utf-8"))
        self.assertTrue((research / "interpret_tree_testing_prompt.md").is_file())
        report = research / "tree_testing.md"
        report.write_text(
            report.read_text(encoding="utf-8").replace(
                "Заполните этот раздел после проверки маршрутов. Отделяйте наблюдаемое действие от возможной причины. Изменяйте информационную архитектуру только там, где результат подтверждается проведёнными сессиями.",
                "T-01: один участник начал с другого раздела; T-02 пройден напрямую. Структура оставлена без изменений.",
            ),
            encoding="utf-8",
        )
        with contextlib.redirect_stdout(io.StringIO()) as output:
            validate_tree_report(self.study)
        self.assertIn("TREE REPORT PASS", output.getvalue())

    def test_source_ia_change_blocks_later_steps(self):
        with contextlib.redirect_stdout(io.StringIO()):
            prepare(self.study)
        research = self.study / "research"
        (research / "tree_tasks.json").write_text(
            '{"tasks":[{"prompt":"Найти расписание","targetLabel":"Расписание"}]}', encoding="utf-8"
        )
        (self.study / "ia.md").write_text("# Изменено\n\n- Другая структура\n", encoding="utf-8")
        with self.assertRaises(Exception):
            build_tree_test(self.study)

    def test_task_target_must_exist_in_tree(self):
        with contextlib.redirect_stdout(io.StringIO()):
            prepare(self.study)
        (self.study / "research" / "tree_tasks.json").write_text(
            '{"tasks":[{"prompt":"Найти оплату","targetLabel":"Оплата"}]}', encoding="utf-8"
        )
        with self.assertRaises(Exception):
            build_tree_test(self.study)

    def test_result_from_another_study_is_rejected(self):
        with contextlib.redirect_stdout(io.StringIO()):
            prepare(self.study)
        research = self.study / "research"
        (research / "tree_tasks.json").write_text(
            '{"tasks":[{"prompt":"Найти расписание","targetLabel":"Расписание"}]}', encoding="utf-8"
        )
        with contextlib.redirect_stdout(io.StringIO()):
            build_tree_test(self.study)
        (research / "tree_responses" / "foreign.json").write_text(
            '{"studyId":"other","participantId":"R1","results":[]}', encoding="utf-8"
        )
        with self.assertRaises(Exception):
            summarize_tree_test(self.study)


if __name__ == "__main__":
    unittest.main()
