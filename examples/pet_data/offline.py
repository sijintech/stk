"""Import only the shipped synthetic PET identity fixtures into a NEW generic project.

No model, solver, network request or business database migration is involved. This example
demonstrates existing CSV, scalar references and immutable file snapshots, not a PET contract.
"""
import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import stat

from suan.project import ProjectStore
from suan.project.files import FIELD_IDS

FIXTURES = Path(__file__).resolve().parent / "fixtures"
FORMAT = "stk.pet-data-example/0.1"
DICTIONARY = "pet-data-dictionary-draft/0.1"
MAX_BYTES = 1024 * 1024


def _json_new(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _regular_bytes(path):
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("The example requires regular files without symbolic links")
    with path.open("rb") as stream:
        value = stream.read(MAX_BYTES + 1)
    if len(value) > MAX_BYTES:
        raise ValueError("Example file exceeds the 1 MiB budget")
    return value


def _bundle():
    """Sanity-check this fixed software fixture; not a production relationship validator."""
    metadata_bytes = _regular_bytes(FIXTURES / "fixture.json")
    metadata = json.loads(metadata_bytes)
    if (metadata["format"] != FORMAT or metadata["dictionary_version"] != DICTIONARY
            or metadata["synthetic"] is not True or metadata["not_for_material_validation"] is not True):
        raise ValueError("Expected the explicitly synthetic example bundle")
    paths = ["fixture.json", *[table["path"] for table in metadata["tables"]], *metadata["assets"]]
    if len(set(paths)) != len(paths) or len(paths) > 100:
        raise ValueError("Example file paths must be unique and fit the existing snapshot API")
    payloads = {}
    for name in paths:
        path = Path(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name:
            raise ValueError("Example assets must stay within the fixture directory")
        payloads[name] = _regular_bytes(FIXTURES / path)
    if sum(map(len, payloads.values())) > MAX_BYTES:
        raise ValueError("Example bundle exceeds the 1 MiB budget")
    rows = {}
    for table in metadata["tables"]:
        reader = csv.DictReader(io.StringIO(payloads[table["path"]].decode("utf-8"), newline=""))
        if reader.fieldnames != list(table["types"]):
            raise ValueError("Example CSV headers differ from their explicit types")
        values = list(reader)
        if any(row["source_kind"] != "synthetic" or row["synthetic"] != "true" for row in values):
            raise ValueError("Every fixture row must remain explicitly synthetic")
        if len({row["id"] for row in values}) != len(values):
            raise ValueError("Example identity labels must be unique within a table")
        rows[table["name"]] = values
    for table in metadata["tables"]:
        for column, target in table["relations"].items():
            identities = {row["id"] for row in rows[target]}
            if any(row[column] and row[column] not in identities for row in rows[table["name"]]):
                raise ValueError("The shipped example contains a dangling identity label")
    return metadata, payloads, rows


def _literal(value, kind):
    return value if kind == "text" else json.loads(value) if value.strip() else None


def create_demo(directory):
    """Create only a user-specified new directory; existing paths, including links, fail.

    The edits are ordinary undoable CSV imports followed by one reference edit and a file
    capture. If interrupted, the incomplete new project is retained; reruns never replace it.
    """
    metadata, payloads, rows = _bundle()
    directory = Path(os.path.abspath(Path(directory).expanduser()))
    directory.mkdir(parents=True, exist_ok=False)
    directory = directory.resolve()
    store = ProjectStore.create(directory, "Synthetic PET data / 合成材料数据")
    for name, data in payloads.items():
        target = directory / "fixture" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(data)
    tables, revision = {}, 0
    for definition in metadata["tables"]:
        name = definition["name"]
        imported = store.csv.import_file(directory / "fixture" / definition["path"],
                                         name="PET demo " + name, types=definition["types"],
                                         expected_revision=revision)
        revision = imported["revision"]
        tables[name] = {
            "table_id": imported["table_id"],
            "fields": dict(zip(definition["types"], imported["field_ids"])),
            "records": {row["id"]: identity for row, identity in zip(rows[name], imported["record_ids"])},
        }
    indexed = store.files.index([str(directory / "fixture" / name) for name in payloads], expected_revision=revision)
    revision = indexed["revision"]
    files = dict(zip(payloads, indexed["record_ids"]))
    commands = []
    for definition in metadata["tables"]:
        name, source = definition["name"], tables[definition["name"]]
        for row in rows[name]:
            for column, target_name in definition["relations"].items():
                if not row[column]:
                    continue
                target = tables[target_name]
                commands.append({"op": "set_reference", "table_id": source["table_id"],
                                 "record_id": source["records"][row["id"]], "field_id": source["fields"][column],
                                 "source": {"record_id": target["records"][row[column]],
                                            "field_id": target["fields"]["id"]}})
            if name == "observations":
                commands.append({"op": "set_reference", "table_id": source["table_id"],
                                 "record_id": source["records"][row["id"]],
                                 "field_id": source["fields"]["raw_path"],
                                 "source": {"record_id": files[row["raw_path"]], "field_id": FIELD_IDS["path"]}})
    linked = store.apply(commands, expected_revision=revision)
    captured = store.snapshots.capture(list(files.values()), expected_revision=linked["revision"], max_bytes=MAX_BYTES)
    receipt = {
        "format": FORMAT, "dictionary_version": DICTIONARY, "synthetic": True,
        "project_id": store.info()["id"], "revision": captured["revision"],
        "tables": tables, "files": files, "snapshot_id": captured["snapshot"]["id"],
        "source_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in payloads.items()},
        "reference_count": len(commands),
    }
    _json_new(directory / "demo.json", receipt)
    return verify_demo(directory)


def verify_demo(directory):
    """Check ordinary tables and frozen fixture bytes after reopening, without mutation."""
    store = ProjectStore(directory)
    receipt = json.loads(_regular_bytes(store.directory / "demo.json"))
    metadata, payloads, rows = _bundle()
    if (receipt["format"] != FORMAT or receipt["dictionary_version"] != DICTIONARY
            or receipt["synthetic"] is not True or receipt["project_id"] != store.info()["id"]):
        raise ValueError("Receipt does not identify this synthetic project")
    if set(receipt["files"]) != set(payloads):
        raise ValueError("Receipt files differ from the fixed example bundle")
    snapshot = store.snapshot()
    actual_tables = {table["id"]: table for table in snapshot["tables"]}
    reference_count = 0
    for definition in metadata["tables"]:
        name = definition["name"]
        identity = receipt["tables"][name]
        table = actual_tables[identity["table_id"]]
        actual_rows = {row["id"]: row for row in table["records"]}
        if set(actual_rows) != set(identity["records"].values()):
            raise ValueError("Example record identities changed")
        for expected in rows[name]:
            row = actual_rows[identity["records"][expected["id"]]]
            for column, kind in definition["types"].items():
                value = _literal(expected[column], kind)
                if name == "observations" and column == "raw_path":
                    value = "fixture/" + value
                if row["values"][identity["fields"][column]] != value:
                    raise ValueError("Reopened fixture value differs from its original declaration")
            for column, target_name in definition["relations"].items():
                if not expected[column]:
                    continue
                target = receipt["tables"][target_name]
                source = {"record_id": target["records"][expected[column]], "field_id": target["fields"]["id"]}
                if row["definitions"][identity["fields"][column]] != {"kind": "reference", "source": source}:
                    raise ValueError("Reopened scalar reference lost its stable IDs")
                reference_count += 1
            if name == "observations":
                source = {"record_id": receipt["files"][expected["raw_path"]], "field_id": FIELD_IDS["path"]}
                if row["definitions"][identity["fields"]["raw_path"]] != {"kind": "reference", "source": source}:
                    raise ValueError("Raw resource reference differs from its stable file identity")
                reference_count += 1
    if reference_count != receipt["reference_count"]:
        raise ValueError("Example reference count changed")
    frozen = store.snapshots.get(receipt["snapshot_id"])
    if not store.snapshots.verify(receipt["snapshot_id"])["ok"]:
        raise ValueError("Frozen fixture bytes are missing or invalid")
    manifest = {entry["record_id"]: entry for entry in frozen["manifest"]["files"]}
    if set(manifest) != set(receipt["files"].values()):
        raise ValueError("Snapshot files differ from the example file identities")
    working_changes = 0
    for name, data in payloads.items():
        digest = hashlib.sha256(data).hexdigest()
        entry = manifest[receipt["files"][name]]
        if entry["sha256"] != digest or receipt["source_sha256"][name] != digest:
            raise ValueError("Frozen bytes differ from the shipped synthetic fixture")
        try:
            working = _regular_bytes(store.directory / "fixture" / name)
        except (OSError, ValueError):
            working_changes += 1
        else:
            working_changes += working != data
    return {"synthetic": True, "format_version": snapshot["format_version"], "project_id": receipt["project_id"],
            "tables": len(metadata["tables"]), "records": sum(map(len, rows.values())),
            "references": reference_count, "frozen_files": len(manifest), "working_copy_changes": working_changes,
            "verified_reopen": True, "material_validated": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument("--out", type=Path, help="Create a NEW directory containing only synthetic data")
    destination.add_argument("--verify", type=Path, help="Read and verify an existing example without changes")
    arguments = parser.parse_args()
    result = create_demo(arguments.out) if arguments.out is not None else verify_demo(arguments.verify)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))


if __name__ == "__main__":
    main()
