import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from scripts.dependency_inventory import build_lock_entries, is_license_file, make_sbom


class DependencyInventoryTests(unittest.TestCase):
    def test_license_documents_not_python_implementation(self):
        for name in ("x.dist-info/licenses/LICENSE", "x.dist-info/LICENSES.txt", "LICENSE_zstd.txt", "NOTICE", "AUTHORS"):
            self.assertTrue(is_license_file(name), name)
        for name in ("packaging/licenses/_spdx.py", "packaging/licenses/__init__.py", "license.py", "licensed_module.so", "metadata.json"):
            self.assertFalse(is_license_file(name), name)

    def test_build_lock_requires_exact_versions(self):
        source = "# lock\nzope.interface==8.6 \\\n  --hash=sha256:" + "a" * 64 + "\n"
        self.assertEqual(build_lock_entries(source), {("zope-interface", "8.6")})
        for value in ("", "foo>=1", "-r elsewhere.txt", "--index-url https://example.com", "foo==1; sys_platform=='linux'"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                build_lock_entries(value)

    def test_sbom_does_not_infer_licenses_or_completeness(self):
        project = {"name": "everyinfra-docs-crawler", "version": "0.1.0.dev0", "license": "MIT"}
        rows = [{"name": "zope.interface", "version": "8.6", "license_expression": None, "license_files": []},
                {"name": "packaging", "version": "26.3", "license_expression": "Apache-2.0 OR BSD-2-Clause", "license_files": [{"path": "LICENSE"}]}]
        inventory = {"packages": rows, "generated_at": "2026-09-05T00:00:00Z", "scope": "test fixture", "lock_sha256": "a" * 64}
        bom = make_sbom(inventory, project)
        self.assertEqual(bom["specVersion"], "1.6")
        self.assertEqual(bom["components"][0]["purl"], "pkg:pypi/zope-interface@8.6")
        self.assertNotIn("licenses", bom["components"][0])
        self.assertEqual(bom["components"][1]["licenses"], [{"expression": "Apache-2.0 OR BSD-2-Clause"}])
        self.assertEqual(bom["metadata"]["component"]["licenses"], [{"expression": "MIT"}])
        self.assertEqual(bom["compositions"][0]["aggregate"], "incomplete")
        self.assertNotIn("vulnerabilities", bom)

    def test_existing_bundle_refused_before_inventory_write(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "bundle"
            bundle.mkdir()
            keep = bundle / "keep.txt"
            keep.write_text("keep")
            result = subprocess.run([sys.executable, "scripts/dependency_inventory.py", "--output", str(root / "inventory.json"),
                                     "--bundle-dir", str(bundle)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertFalse((root / "inventory.json").exists())
            self.assertEqual(keep.read_text(), "keep")

    def test_runtime_bundle_matches_file_hashes(self):
        from hashlib import sha256
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = subprocess.run([sys.executable, "scripts/dependency_inventory.py", "--output", str(root / "inventory.json"),
                                     "--bundle-dir", str(root / "bundle")], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            inventory = json.loads((root / "inventory.json").read_text())
            self.assertTrue(inventory["all_installed_match_lock"])
            self.assertFalse(inventory["full_license_audit"])
            for package in inventory["packages"]:
                for entry in package["license_files"]:
                    self.assertEqual(sha256((root / "bundle" / entry["bundle_path"]).read_bytes()).hexdigest(), entry["sha256"])
            bom = json.loads((root / "bundle" / "bom.cdx.json").read_text())
            self.assertEqual(len(bom["components"]), inventory["installed_count"] - 1)
