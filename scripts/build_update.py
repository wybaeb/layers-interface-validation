#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
VERSION = "2026.11.09.2"
FILES = (
    "interface_validation_lab/AGENTS.md",
    "interface_validation_lab/.cline/skills/interface-validation/SKILL.md",
    "interface_validation_lab/README.md",
    "interface_validation_lab/finish_demo.py",
    "interface_validation_lab/launcher.py",
    "interface_validation_lab/research_flow.py",
    "interface_validation_lab/run_study.py",
    "interface_validation_lab/validation_lab.py",
    ".vscode/tasks.json",
)


def main() -> None:
    DIST.mkdir(exist_ok=True)
    package = DIST / "interface_validation_update.zip"
    with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative in FILES:
            archive.write(ROOT / relative, relative)
    checksum = hashlib.sha256(package.read_bytes()).hexdigest()
    manifest = {
        "version": VERSION,
        "sha256": checksum,
        "installer_sha256": hashlib.sha256((DIST / "install_interface_validation.py").read_bytes()).hexdigest(),
        "files": list(FILES),
        "preserves": ["interface_validation_lab/studies", "research", "results"],
    }
    (DIST / "update.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(checksum)


if __name__ == "__main__":
    main()
