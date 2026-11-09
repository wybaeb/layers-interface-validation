#!/usr/bin/env python3
"""Prepare a student's study from one folder with screens, transcript and context."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from finish_demo import finish
from launcher import main

PROJECT_ROOT = Path(__file__).resolve().parent.parent

INPUT_NAMES = (
    "screens",
    "transcript.md",
    "ia.md",
    "screen_flow.svg",
    "tasks.md",
    "questionnaire.md",
)


def resolve_user_path(value: str, *, cwd: Path | None = None) -> Path:
    """Resolve an absolute path or a path relative to the student repository root."""
    candidate = Path(value).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (PROJECT_ROOT / candidate).resolve()


def _display_path(path: Path) -> str:
    """Use one readable separator on Windows, macOS and Linux."""
    return path.as_posix()


def _file_status(path: Path, *, non_empty: bool = False) -> bool:
    return path.is_file() and (not non_empty or path.stat().st_size > 0)


def preflight(source: Path, output: Path, *, show: bool = True) -> bool:
    """Check the documented study contract before creating any results."""
    screens = source / "screens"
    transcript = source / "transcript.md"
    svg_count = len(list(screens.glob("*.svg"))) if screens.is_dir() else 0
    required = [
        (
            "Папка исследования",
            source,
            source.is_dir(),
            "создайте папку внутри открытого студенческого репозитория",
        ),
        (
            "SVG-экраны",
            screens,
            screens.is_dir() and svg_count > 0,
            "положите в screens/ хотя бы один экспортированный SVG",
        ),
        (
            "Транскрипт",
            transcript,
            _file_status(transcript, non_empty=True),
            "создайте непустой transcript.md текущего коридорного тестирования",
        ),
    ]
    optional = [
        ("Информационная архитектура", source / "ia.md"),
        ("Screen Flow", source / "screen_flow.svg"),
        ("Задания", source / "tasks.md"),
        ("Вопросы модератора", source / "questionnaire.md"),
    ]
    output_clear = not output.exists() and not output.is_symlink()
    passed = all(row[2] for row in required) and output_clear

    if show:
        print("PREFLIGHT · проверка входов")
        print("| Вход | Путь | Статус | Что сделать |")
        print("|---|---|---|---|")
        for label, path, found, action in required:
            status = "найден" if found else "отсутствует"
            next_action = "ничего" if found else action
            print(f"| {label} | `{_display_path(path)}` | {status} | {next_action} |")
        for label, path in optional:
            found = _file_status(path, non_empty=True)
            status = "найден" if found else "необязателен"
            action = "будет подключён" if found else "можно продолжить без файла"
            print(f"| {label} | `{_display_path(path)}` | {status} | {action} |")
        output_status = "свободен" if output_clear else "уже существует"
        output_action = (
            "будет создан автоматически"
            if output_clear
            else "выполните эту же команду с --reset, затем повторите preflight"
        )
        print(f"| Папка результатов | `{_display_path(output)}` | {output_status} | {output_action} |")
        print()
        if passed:
            print("PREFLIGHT PASS")
            print("Следующий запуск создаст results/gallery.html, results/cline_prompt.md и results/report_template.json.")
            print("screen_timeline.json и draft_report.json появятся позже как результаты работы агента.")
        else:
            print("PREFLIGHT STOP: исправьте строки со статусом «отсутствует» или освободите папку results.")
    return passed


def reset_results(source: Path, output: Path) -> int:
    """Remove only the generated results directory inside this study folder."""
    expected = (source / "results").resolve()
    if output != expected or output.name != "results" or output.parent != source:
        raise ValueError(
            "сброс разрешён только для папки <исследование>/results; исходные материалы не удаляются"
        )
    if output.is_symlink():
        raise ValueError("папка results не должна быть символической ссылкой")
    if not output.exists():
        print(f"Исходное состояние уже восстановлено: {output} отсутствует")
        return 0
    if not output.is_dir():
        raise ValueError("results существует, но не является папкой")
    shutil.rmtree(output)
    print("Исходное состояние исследования восстановлено.")
    print(f"Удалены только созданные результаты: {output}")
    print(f"Экраны, транскрипт и контекст сохранены: {source}")
    return 0


def clear_inputs(source: Path, output: Path) -> int:
    """Remove only the documented study inputs after results were reset."""
    if not source.exists() or not source.is_dir():
        raise ValueError(f"папка исследования не найдена: {source}")
    if source.is_symlink():
        raise ValueError("папка исследования не должна быть символической ссылкой")
    if output.exists() or output.is_symlink():
        raise ValueError("сначала удалите результаты командой --reset")

    removed: list[str] = []
    for name in INPUT_NAMES:
        target = source / name
        if target.is_symlink() or target.is_file():
            target.unlink()
            removed.append(name)
        elif target.is_dir():
            if name != "screens":
                raise ValueError(f"{name} должен быть файлом, а не папкой")
            shutil.rmtree(target)
            removed.append(name)

    print("Исходные данные исследования удалены без возможности восстановления.")
    if removed:
        print("Удалено: " + ", ".join(removed))
    else:
        print("Перечисленные исходные файлы уже отсутствуют.")
    print(f"Папка исследования сохранена: {source}")
    return 0


def cli() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Подготовить анализ: обязательны screens/ и transcript.md; "
            "ia.md, screen_flow.svg, tasks.md и questionnaire.md подключаются автоматически"
        ),
    )
    parser.add_argument("input", help="папка исследования")
    parser.add_argument("--out", help="новая папка результата; по умолчанию <input>/results")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument(
        "--preflight",
        action="store_true",
        help="проверить входы и показать точные пути, ничего не создавая",
    )
    actions.add_argument(
        "--finish",
        action="store_true",
        help="проверить отчёт агента и собрать читаемые результаты без дополнительных вопросов",
    )
    actions.add_argument(
        "--reset",
        action="store_true",
        help="удалить только <input>/results и вернуть исследование к исходному состоянию",
    )
    actions.add_argument(
        "--clear-inputs",
        action="store_true",
        help="навсегда удалить перечисленные исходные файлы исследования",
    )
    parser.add_argument(
        "--confirm-delete-inputs",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()
    source = resolve_user_path(args.input)
    output = resolve_user_path(args.out) if args.out else source / "results"
    if args.confirm_delete_inputs and not args.clear_inputs:
        parser.error("--confirm-delete-inputs используется только вместе с --clear-inputs")
    if args.preflight:
        return 0 if preflight(source, output) else 2
    if args.reset:
        if args.out:
            parser.error("для безопасного сброса не указывайте --out")
        try:
            return reset_results(source, output)
        except (ValueError, OSError) as exc:
            parser.error(str(exc))
    if args.clear_inputs:
        if args.out:
            parser.error("для удаления исходных данных не указывайте --out")
        if not args.confirm_delete_inputs:
            parser.error(
                "исходные данные удаляются без возможности восстановления; "
                "после проверки пути добавьте --confirm-delete-inputs"
            )
        try:
            return clear_inputs(source, output)
        except (ValueError, OSError) as exc:
            parser.error(str(exc))
    if args.finish:
        return finish(output)
    if not preflight(source, output):
        return 2
    return main([
        "prepare",
        "--screens", str(source / "screens"),
        "--transcript", str(source / "transcript.md"),
        "--context", str(source),
        "--out", str(output),
    ])


if __name__ == "__main__":
    raise SystemExit(cli())
