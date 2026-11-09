#!/usr/bin/env python3
"""Reset and prepare the bundled interface-validation demo in one student-facing command."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from launcher import main


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "runs" / "demo-pulse"
LEGACY_PRECHECK_PATTERN = "demo-pulse.precheck-*"
LEGACY_ARCHIVE_PATTERN = "demo-pulse-before-video-*"


def reset_demo() -> list[Path]:
    """Remove only generated demo state and keep source inputs and personal studies."""
    runs = (ROOT / "runs").resolve()
    output = OUTPUT.resolve()
    if output.parent != runs or output.name != "demo-pulse":
        raise RuntimeError("защитная проверка пути демо не пройдена")
    runs.mkdir(parents=True, exist_ok=True)
    targets = [output]
    targets.extend(path.resolve() for path in runs.glob(LEGACY_PRECHECK_PATTERN))
    archive = runs / "archive"
    if archive.is_dir():
        targets.extend(path.resolve() for path in archive.glob(LEGACY_ARCHIVE_PATTERN))

    removed: list[Path] = []
    for target in targets:
        if target == runs or runs not in target.parents:
            raise RuntimeError("защитная проверка пути демо не пройдена")
        if target.is_symlink():
            target.unlink()
            removed.append(target)
        elif target.is_dir():
            shutil.rmtree(target)
            removed.append(target)
        elif target.exists():
            target.unlink()
            removed.append(target)
    if archive.is_dir() and not any(archive.iterdir()):
        archive.rmdir()
    return removed


if __name__ == "__main__":
    reset_demo()
    print("Исходное состояние демо восстановлено.", flush=True)
    result = main([
        "prepare",
        "--screens", str(ROOT / "demo" / "screens"),
        "--transcript", str(ROOT / "demo" / "transcript.md"),
        "--context", str(ROOT / "demo"),
        "--out", str(OUTPUT),
    ])
    if result == 0:
        print("\nЗапрос агенту:")
        print(
            "Выполни инструкции из interface_validation_lab/runs/demo-pulse/cline_prompt.md. "
            "Создай screen_timeline.json и draft_report.json. "
            "Для задания сопоставь цель, ожидаемый результат, выбранный элемент, фактический переход и итог. "
            "Если цитата, поведение и экран подтверждают разрыв, добавь конкретное предложение по изменению. "
            "Исходные файлы не изменяй."
        )
    raise SystemExit(result)
