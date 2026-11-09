#!/usr/bin/env python3
"""Линейный CLI проверки интерфейса: подготовка → агент → готовый отчёт."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from validation_lab import LabError, prepare_workspace, validate_report, write_readable_reports

ROOT = Path(__file__).resolve().parent


def prepare(args: argparse.Namespace) -> int:
    context = Path(args.context) if getattr(args, "context", None) else None
    manifest = prepare_workspace(
        Path(args.screens), Path(args.transcript), Path(args.out), ROOT, context,
    )
    out = Path(args.out).resolve()
    count = len(manifest["screen_map"])
    suffix = "экран" if count % 10 == 1 and count % 100 != 11 else "экрана" if count % 10 in {2, 3, 4} and count % 100 not in {12, 13, 14} else "экранов"
    print(f"Готово: {count} {suffix}")
    print(f"Галерея (автономный HTML): {out / 'gallery.html'}")
    print(f"Карта экранов: {out / '01_КАРТА_ЭКРАНОВ.md'}")
    print(f"Инструкция для агента: {out / 'cline_prompt.md'}")
    print("Следующий шаг: передайте агенту просьбу выполнить эту инструкцию.")
    if out == (ROOT / "runs" / "demo-pulse").resolve():
        print("После работы агента запустите: python3 interface_validation.py finish")
    elif (
        out.name == "results"
        and (out.parent / "screens").is_dir()
        and (out.parent / "transcript.md").is_file()
    ):
        print("После работы агента запустите:")
        print(f'  python3 "{ROOT / "run_study.py"}" "{out.parent}" --finish')
    else:
        print("После работы агента запустите:")
        print(f'  python3 "{ROOT / "launcher.py"}" validate --workspace "{out}" --report "{out / "draft_report.json"}"')
    return 0


def validate(args: argparse.Namespace) -> int:
    workspace, report = Path(args.workspace), Path(args.report)
    result = validate_report(workspace, report)
    print("CONTRACT PASS" if result["passed"] else "BLOCK")
    for error in result["errors"]:
        print(f"  ошибка: {error}")
    for warning in result["warnings"]:
        print(f"  внимание: {warning}")
    print(f"Протокол: {Path(args.workspace).resolve() / 'validation.json'}")
    if not result["passed"]:
        print("Читаемый отчёт ещё не создан. Исправьте перечисленные ошибки и повторите проверку до CONTRACT PASS.")
        return 2
    readable = write_readable_reports(workspace, report, result)
    print("Читаемые отчёты:")
    for path in readable:
        print(f"  {path}")
    return 0


def corpus_agent(args: argparse.Namespace) -> int:
    agent = ROOT.parent / "corpus_lab" / "tools" / "corpus_agent.py"
    workspace = Path(args.workspace).resolve()
    corpus = workspace / "corpus"
    if not agent.is_file():
        raise LabError("опциональный corpus_lab не найден рядом с interface_validation_lab")
    if not (corpus / "AGENTS.md").is_file():
        raise LabError("сначала выполните prepare: в workspace нет подготовленного corpus/")
    completed = subprocess.run(
        [sys.executable, str(agent), "--corpus", str(corpus)],
        cwd=str(agent.parent.parent),
        shell=False,
        check=False,
    )
    return completed.returncode


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Проверка интерфейса по статическим SVG-экранам")
    sub = ap.add_subparsers(dest="command")
    p = sub.add_parser("prepare", help="проверить входы и собрать workspace для агента")
    p.add_argument("--screens", required=True, help="папка отдельных SVG-экранов")
    p.add_argument("--transcript", required=True, help="Markdown-транскрипт проверки")
    p.add_argument(
        "--context",
        help="папка с ia.md, screen_flow.svg, tasks.md и questionnaire.md",
    )
    p.add_argument("--out", required=True, help="новая или пустая папка результата")
    p.set_defaults(func=prepare)
    v = sub.add_parser("validate", help="детерминированно проверить draft_report.json")
    v.add_argument("--workspace", required=True)
    v.add_argument("--report", required=True)
    v.set_defaults(func=validate)
    c = sub.add_parser("corpus-agent", help="опционально запустить знакомый corpus_agent.py")
    c.add_argument("--workspace", required=True)
    c.set_defaults(func=corpus_agent)
    return ap


def interactive() -> int:
    print("Проверка интерфейса по статическим SVG-экранам")
    print("1 — подготовить исследование\n2 — проверить и собрать отчёт\n3 — открыть знакомый corpus agent")
    choice = input("Выберите шаг [1]: ").strip() or "1"
    if choice == "1":
        args = argparse.Namespace(
            screens=input("Папка SVG: ").strip(),
            transcript=input("Markdown-транскрипт: ").strip(),
            context=input("Папка контекста [рядом с транскриптом]: ").strip() or None,
            out=input("Папка результата: ").strip(),
        )
        return prepare(args)
    if choice == "2":
        return validate(argparse.Namespace(
            workspace=input("Папка результата: ").strip(),
            report=input("draft_report.json: ").strip(),
        ))
    if choice == "3":
        return corpus_agent(argparse.Namespace(workspace=input("Папка результата: ").strip()))
    raise LabError("неизвестный шаг")


def main(argv: list[str] | None = None) -> int:
    ap = parser()
    args = ap.parse_args(argv)
    try:
        return args.func(args) if args.command else interactive()
    except (LabError, OSError, UnicodeError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
