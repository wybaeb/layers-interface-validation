import hashlib
import json
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class UpdateBundleCase(unittest.TestCase):
    def test_bundle_is_complete_and_verified(self):
        manifest = json.loads((ROOT / "dist" / "update.json").read_text(encoding="utf-8"))
        package = ROOT / "dist" / "interface_validation_update.zip"
        installer = ROOT / "dist" / "install_interface_validation.py"
        self.assertEqual(manifest["version"], "2026.11.09.5")
        self.assertEqual(hashlib.sha256(package.read_bytes()).hexdigest(), manifest["sha256"])
        self.assertEqual(hashlib.sha256(installer.read_bytes()).hexdigest(), manifest["installer_sha256"])
        with zipfile.ZipFile(package) as archive:
            names = {name.rstrip("/") for name in archive.namelist() if not name.endswith("/")}
        self.assertEqual(names, set(manifest["files"]))
        self.assertIn("interface_validation_lab/.cline/skills/interface-validation/SKILL.md", names)
        self.assertIn("interface_validation_lab/research_flow.py", names)
        self.assertIn("interface_validation_lab/run_study.py", names)
        self.assertNotIn(".vscode/tasks.json", names)
        self.assertFalse(any("studies/" in name or "/runs/" in name for name in names))


if __name__ == "__main__":
    unittest.main()
