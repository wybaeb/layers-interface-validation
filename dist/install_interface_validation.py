#!/usr/bin/env python3
"""Install a verified interface-validation runtime without touching study data."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

VERSION = "2026.11.09.4"
BASE_URL = os.environ.get(
    "LAYERS_INTERFACE_UPDATE_BASE_URL",
    "https://wybaeb.github.io/layers-interface-validation/dist",
).rstrip("/")
PACKAGE_URL = f"{BASE_URL}/interface_validation_update.zip"
MANIFEST_URL = f"{BASE_URL}/update.json"
ALLOWED = {
    "interface_validation_lab/AGENTS.md",
    "interface_validation_lab/.cline/skills/interface-validation/SKILL.md",
    "interface_validation_lab/README.md",
    "interface_validation_lab/finish_demo.py",
    "interface_validation_lab/launcher.py",
    "interface_validation_lab/research_flow.py",
    "interface_validation_lab/run_study.py",
    "interface_validation_lab/validation_lab.py",
    ".vscode/tasks.json",
}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def project_root() -> Path:
    root = Path.cwd().resolve()
    if not (root / "interface_validation_lab").is_dir():
        raise RuntimeError(
            "откройте корень студенческого репозитория: в нём должна быть папка interface_validation_lab"
        )
    return root


def main() -> int:
    root = project_root()
    with tempfile.TemporaryDirectory(prefix="layers-interface-update-") as temp_name:
        temp = Path(temp_name)
        manifest_path = temp / "update.json"
        package_path = temp / "update.zip"
        urllib.request.urlretrieve(MANIFEST_URL, manifest_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("version") != VERSION:
            raise RuntimeError("версия пакета не совпала с версией установщика")
        urllib.request.urlretrieve(PACKAGE_URL, package_path)
        if digest(package_path) != manifest.get("sha256"):
            raise RuntimeError("контрольная сумма пакета не совпала; обновление остановлено")
        with zipfile.ZipFile(package_path) as archive:
            names = {name.rstrip("/") for name in archive.namelist() if not name.endswith("/")}
            if names != ALLOWED:
                raise RuntimeError("состав пакета отличается от разрешённого списка")
            archive.extractall(temp / "content")
        backup = Path.home() / ".layers-backups" / "interface-validation" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        for relative in sorted(ALLOWED):
            source = temp / "content" / relative
            target = root / relative
            if target.exists():
                saved = backup / relative
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, saved)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        installed = root / "interface_validation_lab" / "research_flow.py"
        print(f"Установлено: {installed}")
        print("Папки studies/, research/ и results/ не изменялись.")
        if backup.exists():
            print(f"Точка возврата: {backup}")
        print(f"UPDATE PASS · interface validation {VERSION}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"UPDATE STOP: {error}")
        raise SystemExit(2)
