#!/usr/bin/env python3
"""Validate the agent report and render readable results without terminal questions."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from validation_lab import LabError, validate_report, write_readable_reports


ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT / "runs" / "demo-pulse"


def finish(workspace: Path) -> int:
    report_path = workspace / "draft_report.json"
    if not report_path.is_file():
        raise LabError(f"агент ещё не создал {report_path}")
    result = validate_report(workspace, report_path)
    print("CONTRACT PASS" if result["passed"] else "BLOCK")
    for error in result["errors"]:
        print(f"  ошибка: {error}")
    for warning in result["warnings"]:
        print(f"  внимание: {warning}")
    if not result["passed"]:
        print("Попросите агента исправить только перечисленные несоответствия и повторите finish.")
        return 2

    readable = write_readable_reports(workspace, report_path, result)
    print("Готовый отчёт создан. Дополнительный ввод в терминале не требуется.")
    print("Откройте:")
    for path in readable:
        print(f"  {path}")
    print("Обсудите предложения и дальнейшие изменения с агентом в обычном чате.")
    return 0


def main() -> int:
    return finish(WORKSPACE)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (LabError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        raise SystemExit(2)
