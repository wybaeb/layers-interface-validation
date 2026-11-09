import json
import contextlib
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from validation_lab import (  # noqa: E402
    LabError, build_screen_map, prepare_workspace, sha256,
    validate_report, validate_svg,
)
from finish_demo import finish  # noqa: E402


def svg(body='<g id="nav-team"><rect x="0" y="0" width="10" height="10"/></g>'):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">{body}</svg>'


TRANSCRIPT = """# Проверка

Экран: Главная
[00:01] R1: Сначала открою «Команда».
[00:02] Событие: выбор «Команда».

Экран: Команда
[00:03] R1: Здесь ожидаю увидеть приглашения.
"""


class LabCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.screens = self.base / "экраны с пробелом"
        self.screens.mkdir()
        (self.screens / "Главная.svg").write_text(svg(), encoding="utf-8")
        (self.screens / "Команда.svg").write_text(svg('<g id="team-invitations"><text x="2" y="12">Приглашения</text></g>'), encoding="utf-8")
        self.transcript = self.base / "транскрипт с пробелом.md"
        self.transcript.write_text(TRANSCRIPT, encoding="utf-8")
        self.workspace = self.base / "результат с пробелом"

    def tearDown(self):
        self.tmp.cleanup()

    def prepare(self):
        return prepare_workspace(self.screens, self.transcript, self.workspace, ROOT)

    def valid_report(self, manifest, screen_id="Главная", screen_line=3, quote_line=4):
        return {
            "schema_version": 1,
            "run_id": manifest["run_id"],
            "untrusted_inputs_acknowledged": True,
            "observations": [],
            "visual_review": [{
                "screen_id": screen_id,
                "status": "inspected",
                "method": "gallery_visual",
                "note": "Экран открыт в локальной галерее.",
            }],
            "limitations": [],
            "unlinked_evidence": [],
            "change_proposals": [{
                "proposal_id": "CP-001",
                "operation": "change",
                "screen_id": screen_id,
                "target_id": "nav-team",
                "target_status": "verified_svg_id",
                "current_value": "Команда",
                "proposed_value": "Рабочая команда",
                "rationale_type": "interpretation",
                "rationale": "Возможная интерпретация наблюдения, а не установленная причина.",
                "source_evidence": [{
                    "kind": "quote",
                    "participant_id": "R1",
                    "source_file": "inputs/transcript.md",
                    "screen_line": screen_line,
                    "line_start": quote_line,
                    "line_end": quote_line,
                    "verbatim": "Сначала открою «Команда».",
                }],
                "confidence": "supported",
            }],
            "insights": [],
            "prototype_brief": [],
        }

    def test_complete_flow_generates_report_without_decision_prompt(self):
        before = {p: sha256(p) for p in self.screens.iterdir()}
        before[self.transcript] = sha256(self.transcript)
        manifest = self.prepare()
        self.assertEqual({x["screen_id"] for x in manifest["screen_map"]}, {"Главная", "Команда"})
        self.assertIn("Content-Security-Policy", (self.workspace / "gallery.html").read_text())
        gallery = (self.workspace / "gallery.html").read_text()
        self.assertIn("<img", gallery)
        self.assertIn("data:image/svg+xml;base64,", gallery)
        self.assertNotIn('src="assets/', gallery)
        report_path = self.workspace / "draft_report.json"
        report_path.write_text(json.dumps(self.valid_report(manifest), ensure_ascii=False), encoding="utf-8")
        result = validate_report(self.workspace, report_path)
        self.assertTrue(result["passed"], result["errors"])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(finish(self.workspace), 0)
        self.assertTrue((self.workspace / "РЕЗУЛЬТАТЫ.html").is_file())
        self.assertFalse((self.workspace / "final_report.json").exists())
        for path, digest in before.items():
            self.assertEqual(sha256(path), digest)

    def test_finish_accepts_valid_report_without_change_proposals(self):
        manifest = self.prepare()
        report = self.valid_report(manifest)
        report["change_proposals"] = []
        report_path = self.workspace / "draft_report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = finish(self.workspace)
        self.assertEqual(result, 0)
        self.assertIn("Дополнительный ввод в терминале не требуется", output.getvalue())
        self.assertTrue((self.workspace / "02_НАБЛЮДЕНИЯ.md").is_file())

    def test_cli_paths_with_spaces(self):
        out = self.base / "cli output with spaces"
        cp = subprocess.run([
            sys.executable, str(ROOT / "launcher.py"), "prepare",
            "--screens", str(self.screens), "--transcript", str(self.transcript), "--out", str(out),
        ], text=True, capture_output=True, check=False)
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertTrue((out / "cline_prompt.md").is_file())
        self.assertTrue((out / "01_КАРТА_ЭКРАНОВ.md").is_file())
        self.assertIn("Искать или редактировать служебные данные не нужно", (out / "01_КАРТА_ЭКРАНОВ.md").read_text())
        self.assertIn("Готово: 2 экрана", cp.stdout)
        self.assertIn("Галерея (автономный HTML)", cp.stdout)
        self.assertIn(f'--workspace "{out}"', (out / "cline_prompt.md").read_text())

    def test_combined_sessions_transcript_is_accepted(self):
        combined = """# Коридорное тестирование

## Сессия R1
[00:00] Модератор: Покажите, с чего вы начнёте.
[00:08] R1: Открываю главный экран и ищу настройки.

## Сессия R2
[00:00] Модератор: Покажите, с чего вы начнёте.
[00:06] R2: Сначала открою команду.
"""
        self.transcript.write_text(combined, encoding="utf-8")
        manifest = self.prepare()
        copied = (self.workspace / "inputs" / "transcript.md").read_text(encoding="utf-8")
        self.assertEqual(copied, combined)
        self.assertEqual(manifest["transcript"]["line_count"], len(combined.splitlines()))
        prompt = (self.workspace / "cline_prompt.md").read_text(encoding="utf-8")
        self.assertIn("только с локальными файлами", prompt)
        self.assertNotIn("GitHub", prompt)

    def test_demo_runner_resets_previous_output_and_prints_summary(self):
        demo_output = ROOT / "runs" / "demo-pulse"
        demo_output.mkdir(parents=True, exist_ok=True)
        (demo_output / "stale.txt").write_text("old", encoding="utf-8")
        cp = subprocess.run(
            [sys.executable, str(ROOT / "run_demo.py")],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertFalse((demo_output / "stale.txt").exists())
        self.assertTrue((demo_output / "gallery.html").is_file())
        self.assertIn("Исходное состояние демо восстановлено", cp.stdout)
        self.assertIn("Готово: 6 экранов", cp.stdout)

    def test_run_study_accepts_one_input_folder(self):
        source = self.base / "исследование"
        source.mkdir()
        shutil.copytree(self.screens, source / "screens")
        shutil.copyfile(self.transcript, source / "transcript.md")
        (source / "ia.md").write_text("# Структура\n\n- Главная\n  - Команда\n", encoding="utf-8")
        (source / "screen_flow.svg").write_text(svg(), encoding="utf-8")
        (source / "tasks.md").write_text("# Задание\n\nНайти команду.\n", encoding="utf-8")
        (source / "questionnaire.md").write_text("# Вопросы\n\nКуда нажмёте?\n", encoding="utf-8")
        cp = subprocess.run(
            [sys.executable, str(ROOT / "run_study.py"), str(source)],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertTrue((source / "results" / "gallery.html").is_file())
        for name in ("ia.md", "screen_flow.svg", "tasks.md", "questionnaire.md"):
            self.assertTrue((source / "results" / "inputs" / "context" / name).is_file())
        self.assertIn("Следующий шаг", cp.stdout)
        self.assertIn("run_study.py", cp.stdout)
        self.assertIn("--finish", cp.stdout)

        workspace = source / "results"
        manifest = json.loads((workspace / "workspace.json").read_text(encoding="utf-8"))
        (workspace / "draft_report.json").write_text(
            json.dumps(self.valid_report(manifest), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        finished = subprocess.run(
            [sys.executable, str(ROOT / "run_study.py"), str(source), "--finish"],
            input="",
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(finished.returncode, 0, finished.stderr)
        self.assertTrue((workspace / "РЕЗУЛЬТАТЫ.html").is_file())
        self.assertFalse((workspace / "final_report.json").exists())

    def test_run_study_resolves_relative_paths_from_any_terminal_folder(self):
        from run_study import PROJECT_ROOT, resolve_user_path

        project_study = PROJECT_ROOT / "studies" / "path-resolution-fixture"
        tool_study = PROJECT_ROOT / "interface_validation_lab" / "studies" / "path-resolution-fixture"
        self.assertEqual(
            resolve_user_path("studies/path-resolution-fixture", cwd=self.base),
            project_study.resolve(),
        )
        self.assertEqual(
            resolve_user_path("interface_validation_lab/studies/path-resolution-fixture", cwd=self.base),
            tool_study.resolve(),
        )
        self.assertEqual(resolve_user_path(str(self.base)), self.base.resolve())

    def test_preflight_reports_paths_and_does_not_create_results(self):
        source = self.base / "исследование preflight"
        source.mkdir()
        shutil.copytree(self.screens, source / "screens")
        shutil.copyfile(self.transcript, source / "transcript.md")
        cp = subprocess.run(
            [sys.executable, str(ROOT / "run_study.py"), str(source), "--preflight"],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertIn("PREFLIGHT PASS", cp.stdout)
        self.assertIn((source / "screens").as_posix(), cp.stdout)
        self.assertIn((source / "transcript.md").as_posix(), cp.stdout)
        self.assertIn("draft_report.json появятся позже", cp.stdout)
        self.assertFalse((source / "results").exists())

    def test_preflight_stops_on_missing_input_with_exact_action(self):
        source = self.base / "неполное исследование"
        source.mkdir()
        cp = subprocess.run(
            [sys.executable, str(ROOT / "run_study.py"), str(source), "--preflight"],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(cp.returncode, 2)
        self.assertIn("PREFLIGHT STOP", cp.stdout)
        self.assertIn("положите в screens/ хотя бы один", cp.stdout)
        self.assertIn("создайте непустой transcript.md", cp.stdout)
        self.assertFalse((source / "results").exists())

    def test_preflight_blocks_existing_results_before_overwrite(self):
        source = self.base / "повторный запуск"
        source.mkdir()
        shutil.copytree(self.screens, source / "screens")
        shutil.copyfile(self.transcript, source / "transcript.md")
        (source / "results").mkdir()
        cp = subprocess.run(
            [sys.executable, str(ROOT / "run_study.py"), str(source), "--preflight"],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(cp.returncode, 2)
        self.assertIn("уже существует", cp.stdout)
        self.assertIn("--reset", cp.stdout)

    def test_run_study_reset_removes_only_generated_results(self):
        source = self.base / "исследование для сброса"
        source.mkdir()
        shutil.copytree(self.screens, source / "screens")
        shutil.copyfile(self.transcript, source / "transcript.md")
        before = {
            path.relative_to(source): sha256(path)
            for path in source.rglob("*") if path.is_file()
        }
        prepared = subprocess.run(
            [sys.executable, str(ROOT / "run_study.py"), str(source)],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        (source / "results" / "agent-output.tmp").write_text("generated", encoding="utf-8")
        reset = subprocess.run(
            [sys.executable, str(ROOT / "run_study.py"), str(source), "--reset"],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(reset.returncode, 0, reset.stderr)
        self.assertFalse((source / "results").exists())
        after = {
            path.relative_to(source): sha256(path)
            for path in source.rglob("*") if path.is_file()
        }
        self.assertEqual(before, after)
        self.assertIn("Удалены только созданные результаты", reset.stdout)
        again = subprocess.run(
            [sys.executable, str(ROOT / "run_study.py"), str(source), "--reset"],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn("уже восстановлено", again.stdout)

    def test_clear_inputs_requires_confirmation_and_keeps_unlisted_files(self):
        source = self.base / "исследование для очистки"
        source.mkdir()
        shutil.copytree(self.screens, source / "screens")
        shutil.copyfile(self.transcript, source / "transcript.md")
        for name in ("ia.md", "screen_flow.svg", "tasks.md", "questionnaire.md"):
            (source / name).write_text(name, encoding="utf-8")
        (source / "заметки.md").write_text("сохранить", encoding="utf-8")

        unconfirmed = subprocess.run(
            [sys.executable, str(ROOT / "run_study.py"), str(source), "--clear-inputs"],
            text=True, capture_output=True, check=False,
        )
        self.assertNotEqual(unconfirmed.returncode, 0)
        self.assertTrue((source / "screens").is_dir())
        self.assertTrue((source / "transcript.md").is_file())

        (source / "results").mkdir()
        blocked = subprocess.run(
            [
                sys.executable, str(ROOT / "run_study.py"), str(source),
                "--clear-inputs", "--confirm-delete-inputs",
            ],
            text=True, capture_output=True, check=False,
        )
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("сначала удалите результаты", blocked.stderr)
        (source / "results").rmdir()

        cleared = subprocess.run(
            [
                sys.executable, str(ROOT / "run_study.py"), str(source),
                "--clear-inputs", "--confirm-delete-inputs",
            ],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(cleared.returncode, 0, cleared.stderr)
        for name in ("screens", "transcript.md", "ia.md", "screen_flow.svg", "tasks.md", "questionnaire.md"):
            self.assertFalse((source / name).exists(), name)
        self.assertTrue((source / "заметки.md").is_file())
        self.assertTrue(source.is_dir())
        self.assertIn("без возможности восстановления", cleared.stdout)

    def test_generated_prompt_requires_gap_chain_without_forcing_a_proposal(self):
        self.prepare()
        prompt = (self.workspace / "cline_prompt.md").read_text(encoding="utf-8")
        self.assertIn("цель участника", prompt)
        self.assertIn("фактически выбранный элемент", prompt)
        self.assertIn("Если ни один разрыв не подтверждён", prompt)
        self.assertIn("ничего не выдумывайте", prompt)

    def test_launcher_does_not_publish_readable_report_before_contract_pass(self):
        manifest = self.prepare()
        report = self.valid_report(manifest)
        report["limitations"] = "не список"
        report_path = self.workspace / "draft_report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        completed = subprocess.run(
            [
                sys.executable, str(ROOT / "launcher.py"), "validate",
                "--workspace", str(self.workspace), "--report", str(report_path),
            ],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("BLOCK", completed.stdout)
        self.assertIn("до CONTRACT PASS", completed.stdout)
        self.assertFalse((self.workspace / "РЕЗУЛЬТАТЫ.html").exists())

    def test_root_vscode_tasks_include_demo_reset_and_validation(self):
        if ROOT.parent.name == "materials":
            tasks = json.loads((ROOT / ".vscode" / "tasks.json").read_text(encoding="utf-8"))
            labels = {task.get("label") for task in tasks["tasks"]}
            self.assertIn("Проверка интерфейса: проверить входы", labels)
            self.assertIn("Проверка интерфейса: подготовить исследование", labels)
            self.assertIn("Проверка интерфейса: проверить и собрать отчёт", labels)
            self.assertIn("Проверка интерфейса: сбросить результаты", labels)
            self.assertNotIn("Проверка интерфейса: записать решение", labels)
            return
        tasks = json.loads((ROOT.parent / ".vscode" / "tasks.json").read_text(encoding="utf-8"))
        labels = {task.get("label") for task in tasks["tasks"]}
        self.assertIn("Проверка интерфейса: проверить входы", labels)
        self.assertIn("Проверка интерфейса: подготовить исследование", labels)
        self.assertIn("Проверка интерфейса: проверить и собрать отчёт", labels)
        self.assertIn("Проверка интерфейса: сбросить результаты", labels)

    def test_demo_reset_removes_only_demo_state(self):
        runs = ROOT / "runs"
        active = runs / "demo-pulse"
        precheck = runs / "demo-pulse.precheck-test"
        archived = runs / "archive" / "demo-pulse-before-video-test"
        personal = runs / "my-own-study"
        for path in (active, precheck, archived, personal):
            path.mkdir(parents=True, exist_ok=True)
            (path / "result.txt").write_text("generated", encoding="utf-8")
        cp = subprocess.run(
            [sys.executable, str(ROOT / "reset_demo.py")],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertFalse(active.exists())
        self.assertFalse(precheck.exists())
        self.assertFalse(archived.exists())
        self.assertTrue((personal / "result.txt").is_file())
        self.assertIn("Демо возвращено в исходное состояние", cp.stdout)
        shutil.rmtree(personal)

    def test_unicode_nfc_casefold_duplicates(self):
        dup = self.base / "dup"
        dup.mkdir()
        (dup / "Écran.svg").write_text(svg(), encoding="utf-8")
        (dup / "E\u0301CRAN.svg").write_text(svg(), encoding="utf-8")
        with self.assertRaisesRegex(LabError, "дублирующиеся ID"):
            build_screen_map(dup)

    def test_figma_gradient_clip_shadow_accepted(self):
        path = ROOT / "demo" / "screens" / "S-TODAY__Сегодня.svg"
        info = validate_svg(path)
        self.assertEqual(info["text_mode"], "text")
        self.assertIn("btn.resolve_conflict", info["element_ids"])

    def test_empty_report_warns_without_claiming_quality(self):
        manifest = self.prepare()
        report = json.loads((self.workspace / "report_template.json").read_text())
        path = self.workspace / "empty.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        result = validate_report(self.workspace, path)
        self.assertTrue(result["passed"])
        self.assertTrue(any("не подтверждает качество" in x for x in result["warnings"]))

    def test_previous_report_without_new_sections_still_validates(self):
        manifest = self.prepare()
        report = self.valid_report(manifest)
        report.pop("insights")
        report.pop("prototype_brief")
        path = self.workspace / "previous-report.json"
        path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        result = validate_report(self.workspace, path)
        self.assertTrue(result["passed"], result["errors"])

    def test_validation_writes_human_readable_reports(self):
        manifest = self.prepare()
        path = self.workspace / "draft_report.json"
        path.write_text(json.dumps(self.valid_report(manifest), ensure_ascii=False), encoding="utf-8")
        cp = subprocess.run([
            sys.executable, str(ROOT / "launcher.py"), "validate",
            "--workspace", str(self.workspace), "--report", str(path),
        ], text=True, capture_output=True, check=False)
        self.assertEqual(cp.returncode, 0, cp.stdout + cp.stderr)
        observations = self.workspace / "02_НАБЛЮДЕНИЯ.md"
        proposals = self.workspace / "03_ПРЕДЛОЖЕНИЯ.md"
        protocol = self.workspace / "04_ПРОТОКОЛ_ПРОВЕРКИ.md"
        insights = self.workspace / "05_ВЫВОДЫ.md"
        prototype = self.workspace / "06_ОПИСАНИЕ_СЛЕДУЮЩЕЙ_ВЕРСИИ.md"
        visual = self.workspace / "РЕЗУЛЬТАТЫ.html"
        self.assertTrue(observations.is_file())
        self.assertIn("Рабочая команда", proposals.read_text())
        self.assertIn("PASS", protocol.read_text())
        self.assertTrue(insights.is_file())
        self.assertTrue(prototype.is_file())
        self.assertIn("Результаты исследования", visual.read_text())
        self.assertIn("Читаемые отчёты", cp.stdout)

    def test_insight_and_prototype_brief_are_grounded_and_rendered(self):
        manifest = self.prepare()
        report = self.valid_report(manifest)
        evidence = dict(report["change_proposals"][0]["source_evidence"][0])
        report["insights"] = [{
            "insight_id": "I-001",
            "screen_id": "Главная",
            "statement": "Название действия недостаточно точно описывает результат.",
            "implication": "Уточнить подпись перед повторной проверкой.",
            "confidence": "supported",
            "source_evidence": [evidence],
        }]
        report["prototype_brief"] = [{
            "screen_id": "Главная",
            "purpose": "Помочь выбрать рабочую команду.",
            "user_goal": "Открыть нужную команду.",
            "key_elements": ["Список команд", "Действие «Рабочая команда»"],
            "states": ["Список загружен", "Команда выбрана"],
            "transitions": ["Выбор команды → экран команды"],
            "related_proposal_ids": ["CP-001"],
            "evidence_basis": "supported",
        }]
        path = self.workspace / "grounded.json"
        path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        cp = subprocess.run([
            sys.executable, str(ROOT / "launcher.py"), "validate",
            "--workspace", str(self.workspace), "--report", str(path),
        ], text=True, capture_output=True, check=False)
        self.assertEqual(cp.returncode, 0, cp.stdout + cp.stderr)
        self.assertIn("Уточнить подпись", (self.workspace / "05_ВЫВОДЫ.md").read_text())
        self.assertIn("Выбор команды", (self.workspace / "06_ОПИСАНИЕ_СЛЕДУЮЩЕЙ_ВЕРСИИ.md").read_text())
        self.assertIn("Рабочая команда", (self.workspace / "РЕЗУЛЬТАТЫ.html").read_text())

    def test_prototype_brief_rejects_unknown_proposal(self):
        manifest = self.prepare()
        report = self.valid_report(manifest)
        report["prototype_brief"] = [{
            "screen_id": "Главная",
            "purpose": "Назначение", "user_goal": "Цель",
            "key_elements": [], "states": [], "transitions": [],
            "related_proposal_ids": ["CP-999"], "evidence_basis": "mixed",
        }]
        path = self.workspace / "unknown-proposal.json"
        path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        result = validate_report(self.workspace, path)
        self.assertFalse(result["passed"])
        self.assertTrue(any("unknown related_proposal_id" in value or "неизвестный related_proposal_id" in value for value in result["errors"]))

    def test_quote_cannot_be_attributed_to_other_screen(self):
        manifest = self.prepare()
        report = self.valid_report(manifest, screen_id="Команда", screen_line=3, quote_line=4)
        proposal = report["change_proposals"][0]
        proposal["target_id"] = "team-invitations"
        proposal["current_value"] = "Приглашения"
        path = self.workspace / "wrong-screen.json"
        path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        result = validate_report(self.workspace, path)
        self.assertFalse(result["passed"])
        self.assertTrue(any("другого экрана" in x for x in result["errors"]))

    def test_no_marker_cannot_support_proposal(self):
        manifest = self.prepare()
        report = self.valid_report(manifest)
        del report["change_proposals"][0]["source_evidence"][0]["screen_line"]
        path = self.workspace / "no-marker.json"
        path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        result = validate_report(self.workspace, path)
        self.assertFalse(result["passed"])
        self.assertTrue(any("alignment_id" in x and "screen_line" in x for x in result["errors"]))

    def test_unmarked_transcript_uses_validated_screen_timeline(self):
        raw = """# Проверка

[00:01] Модератор: Перед вами главный экран.
[00:02] R1: Сначала открою «Команда».
[00:03] Модератор: Теперь открыт экран команды.
[00:04] R1: Здесь ожидаю увидеть приглашения.
"""
        self.transcript.write_text(raw, encoding="utf-8")
        manifest = self.prepare()
        (self.workspace / "screen_timeline.json").write_text(json.dumps({
            "schema_version": 1,
            "run_id": manifest["run_id"],
            "segments": [
                {"alignment_id": "A-001", "screen_id": "Главная", "line_start": 3,
                 "line_end": 4, "confidence": "high", "rationale": "Назван главный экран."},
                {"alignment_id": "A-002", "screen_id": "Команда", "line_start": 5,
                 "line_end": 6, "confidence": "high", "rationale": "Назван экран команды."},
            ],
            "unassigned_ranges": [{"line_start": 1, "line_end": 2, "reason": "Заголовок."}],
        }, ensure_ascii=False), encoding="utf-8")
        report = self.valid_report(manifest, screen_id="Главная", quote_line=4)
        evidence = report["change_proposals"][0]["source_evidence"][0]
        evidence.pop("screen_line")
        evidence["alignment_id"] = "A-001"
        path = self.workspace / "timeline-report.json"
        path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        result = validate_report(self.workspace, path)
        self.assertTrue(result["passed"], result["errors"])
        self.assertTrue(any("читаемом отчёте" in x for x in result["warnings"]))

    def test_timeline_cannot_attribute_quote_to_other_screen(self):
        raw = "# Проверка\n\n[00:01] R1: Сначала открою «Команда».\n"
        self.transcript.write_text(raw, encoding="utf-8")
        manifest = self.prepare()
        (self.workspace / "screen_timeline.json").write_text(json.dumps({
            "schema_version": 1,
            "run_id": manifest["run_id"],
            "segments": [{"alignment_id": "A-001", "screen_id": "Команда", "line_start": 3,
                          "line_end": 3, "confidence": "medium", "rationale": "Упомянута команда."}],
            "unassigned_ranges": [],
        }, ensure_ascii=False), encoding="utf-8")
        report = self.valid_report(manifest, screen_id="Главная", quote_line=3)
        evidence = report["change_proposals"][0]["source_evidence"][0]
        evidence.pop("screen_line")
        evidence["alignment_id"] = "A-001"
        path = self.workspace / "wrong-timeline-screen.json"
        path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        result = validate_report(self.workspace, path)
        self.assertFalse(result["passed"])
        self.assertTrue(any("другой экран" in x for x in result["errors"]))

    def test_overlapping_timeline_is_blocked(self):
        manifest = self.prepare()
        (self.workspace / "screen_timeline.json").write_text(json.dumps({
            "schema_version": 1,
            "run_id": manifest["run_id"],
            "segments": [
                {"alignment_id": "A-001", "screen_id": "Главная", "line_start": 3,
                 "line_end": 5, "confidence": "high", "rationale": "Первый блок."},
                {"alignment_id": "A-002", "screen_id": "Команда", "line_start": 5,
                 "line_end": 8, "confidence": "high", "rationale": "Второй блок."},
            ],
            "unassigned_ranges": [],
        }, ensure_ascii=False), encoding="utf-8")
        report = self.valid_report(manifest)
        path = self.workspace / "overlap.json"
        path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        result = validate_report(self.workspace, path)
        self.assertFalse(result["passed"])
        self.assertTrue(any("пересекаются" in x for x in result["errors"]))

    def test_fake_id_in_workspace_is_reparsed_and_rejected(self):
        manifest = self.prepare()
        saved = json.loads((self.workspace / "workspace.json").read_text())
        row = next(x for x in saved["screen_map"] if x["screen_id"] == "Главная")
        row["element_ids"]["invented-id"] = "g"
        (self.workspace / "workspace.json").write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
        report = self.valid_report(manifest)
        report["change_proposals"][0]["target_id"] = "invented-id"
        path = self.workspace / "fake-id.json"
        path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        result = validate_report(self.workspace, path)
        self.assertFalse(result["passed"])
        self.assertTrue(any("target_id отсутствует" in x for x in result["errors"]))

    def test_agent_contract_contains_no_hashes_or_decision_fields(self):
        manifest = self.prepare()
        public_text = "\n".join(
            (self.workspace / name).read_text(encoding="utf-8")
            for name in ("workspace.json", "report_template.json", "cline_prompt.md")
        ) + (self.workspace / ".cline/skills/interface-validation/SKILL.md").read_text(encoding="utf-8")
        for forbidden in ("sha256", "SHA-256", "input_hashes", "screen_sha256", "human_decision", "decision_note"):
            self.assertNotIn(forbidden, public_text)
        self.assertTrue((self.workspace / ".integrity.json").is_file())

    def test_observation_is_validated(self):
        manifest = self.prepare()
        report = self.valid_report(manifest)
        report["observations"] = [{"screen_id": "Несуществующий", "event": "click"}]
        path = self.workspace / "bad-observation.json"
        path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        result = validate_report(self.workspace, path)
        self.assertFalse(result["passed"])
        self.assertTrue(any("unlinked_evidence" in x for x in result["errors"]))

    def test_report_array_is_graceful_block(self):
        self.prepare()
        path = self.workspace / "array.json"
        path.write_text("[]", encoding="utf-8")
        result = validate_report(self.workspace, path)
        self.assertFalse(result["passed"])
        self.assertIn("JSON-объект", result["errors"][0])

    def test_changed_asset_and_original_are_detected(self):
        manifest = self.prepare()
        report = self.valid_report(manifest)
        path = self.workspace / "draft.json"
        path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        asset = self.workspace / "assets" / "Главная.svg"
        asset.write_text(asset.read_text().replace('width="10"', 'width="11"'), encoding="utf-8")
        self.assertFalse(validate_report(self.workspace, path)["passed"])

    def test_unavailable_visual_review_blocks_proposal(self):
        manifest = self.prepare()
        report = self.valid_report(manifest)
        review = report["visual_review"][0]
        review.update(status="unavailable", method=None, note="insufficient_visual_evidence")
        path = self.workspace / "no-visual.json"
        path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        result = validate_report(self.workspace, path)
        self.assertFalse(result["passed"])
        self.assertTrue(any("визуального просмотра" in x for x in result["errors"]))

    def test_malformed_llm_fields_block_without_crash(self):
        manifest = self.prepare()
        report = self.valid_report(manifest)
        proposal = report["change_proposals"][0]
        proposal.update(operation=[], screen_id=[], proposal_id=[])
        path = self.workspace / "malformed.json"
        path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        self.assertFalse(validate_report(self.workspace, path)["passed"])

    def test_workspace_asset_path_escape_blocked(self):
        manifest = self.prepare()
        saved = json.loads((self.workspace / "workspace.json").read_text())
        saved["screen_map"][0]["file"] = "../../outside.svg"
        (self.workspace / "workspace.json").write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
        path = self.workspace / "report.json"
        path.write_text(json.dumps(self.valid_report(manifest), ensure_ascii=False), encoding="utf-8")
        result = validate_report(self.workspace, path)
        self.assertFalse(result["passed"])
        self.assertTrue(any("прямо в assets" in x for x in result["errors"]))

    def test_unlinked_invented_quote_blocked(self):
        manifest = self.prepare()
        report = json.loads((self.workspace / "report_template.json").read_text())
        report["unlinked_evidence"] = [{
            "link_status": "unsupported", "kind": "quote", "source_file": "inputs/transcript.md",
            "line_start": 4, "line_end": 4, "verbatim": "выдуманная цитата",
        }]
        path = self.workspace / "unlinked.json"
        path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        self.assertFalse(validate_report(self.workspace, path)["passed"])

    def test_location_object_blocked(self):
        manifest = self.prepare()
        report = self.valid_report(manifest)
        proposal = report["change_proposals"][0]
        proposal.update(target_id=None, target_status="requires_confirmation", confidence="mixed", location={"x": 1})
        path = self.workspace / "bad-location.json"
        path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        self.assertFalse(validate_report(self.workspace, path)["passed"])

    def test_empty_operation_values_blocked(self):
        manifest = self.prepare()
        cases = [
            ("add", None, ""),
            ("change", "", ""),
            ("delete", "", None),
        ]
        for index, (operation, current, proposed) in enumerate(cases):
            report = self.valid_report(manifest)
            report["change_proposals"][0].update(
                operation=operation, current_value=current, proposed_value=proposed)
            path = self.workspace / f"empty-operation-{index}.json"
            path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
            with self.subTest(operation=operation):
                self.assertFalse(validate_report(self.workspace, path)["passed"])

    def test_gallery_embeds_file_with_fragment_character(self):
        (self.screens / "S__name#variant.svg").write_text(svg(), encoding="utf-8")
        self.prepare()
        gallery = (self.workspace / "gallery.html").read_text()
        self.assertIn("S__name#variant.svg", gallery)
        self.assertIn("data:image/svg+xml;base64,", gallery)
        self.assertNotIn('src="assets/', gallery)

    def test_symlink_transcript_rejected(self):
        link = self.base / "link.md"
        try:
            link.symlink_to(self.transcript)
        except OSError:
            self.skipTest("symlink недоступен")
        with self.assertRaisesRegex(LabError, "символическая"):
            prepare_workspace(self.screens, link, self.workspace, ROOT)


class AdversarialSvgCase(unittest.TestCase):
    def check_rejected(self, content, message=None, encoding="utf-8"):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bad.svg"
            if isinstance(content, str):
                path.write_bytes(content.encode(encoding))
            else:
                path.write_bytes(content)
            with self.assertRaises(LabError) as caught:
                validate_svg(path)
            if message:
                self.assertIn(message, str(caught.exception))

    def test_active_and_external_constructs_rejected(self):
        cases = [
            (svg("<script>alert(1)</script>"), "<script>"),
            (svg('<image href="data:image/png;base64,AA=="/>'), "<image>"),
            (svg('<foreignObject/>'), "foreignObject"),
            (svg('<rect onclick="x()"/>'), "обработчики"),
            (svg('<rect style="fill:red"/>'), "style"),
            (svg('<rect xml:base="https://evil.invalid"/>'), "xml:base"),
            (svg('<use href="#a"/>'), "<use>"),
            (svg('<rect fill="url(https://evil.invalid/x)"/>'), "внешняя"),
            (svg('<rect fill="u\\72l(\\68ttps://evil.invalid/x)"/>'), "CSS escapes"),
            ('<!DOCTYPE svg [<!ENTITY x "boom">]>' + svg("<text>&x;</text>"), "DTD"),
            ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 NaN 10"/>', "viewBox"),
            ('<?xml-stylesheet href="https://evil.invalid/x.css"?>' + svg(), "processing instructions"),
        ]
        for content, message in cases:
            with self.subTest(message=message):
                self.check_rejected(content, message)

    def test_utf16_declaration_bypass_rejected(self):
        content = ('<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE svg>' + svg()).encode("utf-16")
        self.check_rejected(content, "UTF-8")

    def test_depth_cap(self):
        content = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">' + '<g>' * 70 + '</g>' * 70 + '</svg>'
        self.check_rejected(content, "сложности")


if __name__ == "__main__":
    unittest.main()
