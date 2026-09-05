"""Inventory installed metadata without importing dependency modules."""

import argparse
from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import distributions
import json
from pathlib import Path, PurePosixPath
import platform
import re
import tomllib
from urllib.parse import quote
from uuid import uuid4


def canonical_name(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def is_license_file(path):
    """Do not mistake packaging/licenses/*.py for license documents."""
    name = PurePosixPath(str(path)).name.lower()
    return bool(re.match(r"^(licen[sc]e[sd]?|copying|notice|authors)([._-].*)?$", name)) and not name.endswith((".py", ".pyc", ".so"))


def build_lock_entries(source):
    entries = set()
    for line in source.splitlines():
        line = line.strip().removesuffix("\\").strip()
        if not line or line.startswith("#"):
            continue
        if re.fullmatch(r"--hash=sha256:[0-9a-f]{64}", line):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+!-]+)", line)
        if not match:
            raise ValueError("Expected exact versions and SHA256 hashes in build constraints")
        entries.add((canonical_name(match[1]), match[2]))
    if not entries:
        raise ValueError("Build constraints are empty")
    return entries


def purl(name, version):
    return f"pkg:pypi/{canonical_name(name)}@{quote(version, safe='')}"


def make_sbom(inventory, project):
    components = []
    for package in inventory["packages"]:
        if canonical_name(package["name"]) == canonical_name(project["name"]):
            continue
        component = {"type": "library", "bom-ref": purl(package["name"], package["version"]),
                     "name": canonical_name(package["name"]), "version": package["version"],
                     "purl": purl(package["name"], package["version"]),
                     "properties": [{"name": "everyinfra:license-evidence-files", "value": str(len(package["license_files"]))}]}
        if package["license_expression"]:
            component["licenses"] = [{"expression": package["license_expression"]}]
        components.append(component)
    root = {"type": "application", "bom-ref": purl(project["name"], project["version"]),
            "name": project["name"], "version": project["version"], "purl": purl(project["name"], project["version"])}
    if project.get("license"):
        root["licenses"] = [{"expression": project["license"]}]
    return {"bomFormat": "CycloneDX", "specVersion": "1.6", "serialNumber": f"urn:uuid:{uuid4()}", "version": 1,
            "metadata": {"timestamp": inventory["generated_at"], "component": root,
                         "properties": [{"name": "everyinfra:scope", "value": inventory["scope"]},
                                        {"name": "everyinfra:dependency-edges", "value": "not represented"},
                                        {"name": "everyinfra:lock-sha256", "value": inventory["lock_sha256"]}]},
            "components": components,
            "compositions": [{"aggregate": "incomplete", "assemblies": [root["bom-ref"]]}]}


def write_json(path, data):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bundle-dir", type=Path, help="New directory for CycloneDX inventory and unchanged license files")
    parser.add_argument("--build-constraints", type=Path, help="Inventory a restored isolated build environment instead of runtime")
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((project_root / "pyproject.toml").read_text())["project"]
    lock_path = args.build_constraints or project_root / "uv.lock"
    lock_bytes = lock_path.read_bytes()
    if args.build_constraints:
        locked = build_lock_entries(lock_bytes.decode())
        scope = "Installed isolated build packages only; excludes runtime, operating system and bundled native subcomponents"
    else:
        lock = tomllib.loads(lock_bytes.decode())
        locked = {(canonical_name(package["name"]), package["version"]) for package in lock["package"]}
        scope = "Installed runtime packages only; excludes build environment, inactive platform variants, OS and bundled native subcomponents"
    if args.output.exists() or args.output.is_symlink():
        parser.error("Inventory output already exists")
    if args.bundle_dir and (args.bundle_dir.exists() or args.bundle_dir.is_symlink()):
        parser.error("Bundle directory already exists")
    packages = []
    notices = []
    for dist in sorted(distributions(), key=lambda item: item.metadata["Name"].lower()):
        metadata = dist.metadata
        license_files = []
        for path in dist.files or []:
            if is_license_file(path):
                absolute = Path(dist.locate_file(path))
                if not absolute.resolve().is_relative_to(Path(dist.locate_file("")).resolve()):
                    raise ValueError("License path escapes installed distribution root")
                if absolute.is_file():
                    content = absolute.read_bytes()
                    entry = {"path": str(path), "sha256": sha256(content).hexdigest()}
                    if args.bundle_dir:
                        entry["bundle_path"] = f"licenses/{len(notices):03d}-{canonical_name(metadata['Name'])}-{PurePosixPath(str(path)).name}"
                        notices.append((entry["bundle_path"], content))
                    license_files.append(entry)
        name = metadata["Name"]
        packages.append({"name": name, "version": dist.version,
                         "matches_lock": (canonical_name(name), dist.version) in locked,
                         "license_expression": metadata.get("License-Expression"),
                         "license_classifiers": [v for v in metadata.get_all("Classifier", []) if v.startswith("License ::")],
                         "license_metadata_present": bool(metadata.get("License")), "license_files": license_files})
    installed = {(canonical_name(p["name"]), p["version"]) for p in packages}
    missing = sorted(locked - installed) if args.build_constraints else []
    inventory = {"generated_at": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
                 "platform": platform.platform(), "lock_file": lock_path.name, "lock_sha256": sha256(lock_bytes).hexdigest(),
                 "installed_count": len(packages), "all_installed_match_lock": all(p["matches_lock"] for p in packages),
                 "missing_build_packages": missing,
                 "third_party_without_license_file": [p["name"] for p in packages if not p["license_files"] and canonical_name(p["name"]) != canonical_name(project["name"])],
                 "packages": packages, "full_license_audit": False, "vulnerability_scan": False,
                 "scope": scope}
    if not args.build_constraints:
        inventory["uv_lock_sha256"] = inventory["lock_sha256"]
    if args.bundle_dir:
        args.bundle_dir.mkdir(parents=True)
        (args.bundle_dir / "licenses").mkdir()
        for name, content in notices:
            with (args.bundle_dir / name).open("xb") as handle:
                handle.write(content)
        write_json(args.bundle_dir / "bom.cdx.json", make_sbom(inventory, project))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, inventory)
    print(json.dumps({key: value for key, value in inventory.items() if key != "packages"}))
    return 0 if inventory["all_installed_match_lock"] and not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
