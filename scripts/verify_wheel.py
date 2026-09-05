"""Verify exact wheel contents, RECORD hashes, license metadata, and reproducibility."""

import argparse
import base64
import csv
from email.parser import BytesParser
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import re
import tomllib
from zipfile import ZipFile


def digest(value):
    return sha256(value).hexdigest()


def normalized_dist(name):
    return re.sub(r"[-_.]+", "_", name).lower()


def inspect(wheel, root):
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    dist_info = f"{normalized_dist(project['name'])}-{project['version']}.dist-info"
    source_root = root / "src"
    sources = {path.relative_to(source_root).as_posix(): path for path in (source_root / "everyinfra_docs").glob("*.py")}
    license_member = f"{dist_info}/licenses/LICENSE"
    expected = set(sources) | {f"{dist_info}/{name}" for name in ("METADATA", "WHEEL", "entry_points.txt", "RECORD")} | {license_member}
    errors = []
    files = []
    with ZipFile(wheel) as archive:
        names = archive.namelist()
        if set(names) != expected or len(names) != len(expected):
            errors.append("unexpected_or_duplicate_members")
        corrupt = archive.testzip()
        if corrupt:
            errors.append(f"crc_mismatch:{corrupt}")
        record_name = f"{dist_info}/RECORD"
        records = list(csv.reader(StringIO(archive.read(record_name).decode())))
        if len(records) != len(names) or {row[0] for row in records} != set(names):
            errors.append("record_membership_mismatch")
        for name, encoded, length in records:
            data = archive.read(name)
            if name == record_name:
                if encoded or length:
                    errors.append("record_self_hash_present")
            else:
                record_digest = base64.urlsafe_b64encode(sha256(data).digest()).decode().rstrip("=")
                if encoded != f"sha256={record_digest}" or length != str(len(data)):
                    errors.append(f"record_value_mismatch:{name}")
            if name in sources and data != sources[name].read_bytes():
                errors.append(f"source_mismatch:{name}")
            files.append({"path": name, "bytes": len(data), "sha256": digest(data),
                          "type": "original_source" if name in sources else "metadata_or_license"})
        if archive.read(license_member) != (root / "LICENSE").read_bytes():
            errors.append("license_payload_mismatch")
        metadata = BytesParser().parsebytes(archive.read(f"{dist_info}/METADATA"))
        if metadata["Name"] != project["name"] or metadata["Version"] != project["version"]:
            errors.append("identity_mismatch")
        expected_dependencies = sorted(value.lower() for value in project["dependencies"])
        if sorted(value.lower() for value in metadata.get_all("Requires-Dist", [])) != expected_dependencies:
            errors.append("dependency_metadata_mismatch")
        if metadata.get_all("License-Expression", []) != [project["license"]]:
            errors.append("license_expression_mismatch")
        if metadata.get_all("License-File", []) != ["LICENSE"]:
            errors.append("license_file_metadata_mismatch")
    return {"path": str(wheel), "sha256": digest(wheel.read_bytes()), "files": files, "errors": errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first", type=Path)
    parser.add_argument("second", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    first = inspect(args.first.resolve(), args.root.resolve())
    second = inspect(args.second.resolve(), args.root.resolve())
    errors = first["errors"] + second["errors"]
    if first["sha256"] != second["sha256"]:
        errors.append("builds_not_byte_identical")
    result = {"schema_version": 1, "candidate_checks_passed": not errors, "errors": errors,
              "first": first, "second": second,
              "limits": "Validates this project's wheel allowlist and metadata; does not approve public release or dependencies."}
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"candidate_checks_passed": not errors, "sha256": first["sha256"],
                      "members": len(first["files"]), "errors": errors}, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
