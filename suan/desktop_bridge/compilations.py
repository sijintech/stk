"""Read evidence of an explicit workflow compilation, never execute or recover it.

The workflow journal supplies the attempt directory. Compiler diagnostics can
select a frozen input record; their text never supplies an arbitrary host path.
"""
import hashlib
from pathlib import Path

from suan.documents import latex
from suan.project import ProjectError


def _bound_receipt(store, evidence):
    receipt = latex.read_receipt(store, **evidence["location"])
    prepared, source = evidence["prepared"], evidence["source"]
    if receipt["compiler"] != prepared["compiler"]:
        raise ProjectError("Compilation compiler differs from its frozen workflow task")
    inputs = receipt["inputs"]
    if prepared["inputs"] is not None and inputs != prepared["inputs"]:
        raise ProjectError("Compilation inputs differ from the frozen workflow task")
    # read_receipt independently validates the immutable snapshot's actual
    # metadata hash and every selected file's hash/size. Here bind that validated
    # snapshot to the upstream result that existed before this precise attempt.
    selection = prepared["assets"]
    files = source["files"]
    if any(item["source"] not in files for item in selection):
        raise ProjectError("Compilation selection is missing from its historical upstream files")
    expected = [{"record_id": files[item["source"]], "path": item["path"]} for item in selection]
    actual = [{"record_id": item["record_id"], "path": item["path"]} for item in inputs["assets"]]
    if (inputs["snapshot_id"] != source["snapshot_id"] or inputs["entry_path"] != prepared["entry_path"]
            or actual != expected):
        raise ProjectError("Compilation inputs differ from this attempt's historical upstream files")
    return receipt


def read(store, action, params):
    identity = {key: params[key] for key in ("run_id", "step", "row", "attempt")}
    evidence = store.workflow_runs.compilation_evidence(**identity)
    location = evidence["location"]
    try:
        receipt = _bound_receipt(store, evidence)
        if action == "compilation_log":
            return {**identity, **latex.read_log(store, **location, stream=params.get("stream", "stdout.txt"),
                offset=params.get("offset", 0), limit=params.get("limit", 65536),
                expected_binding={key: receipt[key] for key in ("compiler", "inputs")})}
        if action == "compilation_source":
            index = params["diagnostic"]
            if type(index) is not int or not 0 <= index < len(receipt["diagnostics"]):
                raise ProjectError("Select a diagnostic of this exact compilation attempt")
            diagnostic = receipt["diagnostics"][index]
            # Resolve a registered source at the requested editable revision,
            # then compare its actual bytes with the frozen input, not Files'
            # possibly old metadata. Editing a source requires a fresh compile.
            resolved = store.files.resolve(diagnostic["record_id"], expected_revision=params["expected_revision"])
            raw = latex._regular(Path(resolved["path"]), latex.MAX_FILE_BYTES)
            if hashlib.sha256(raw).hexdigest() != diagnostic["source_sha256"]:
                raise ProjectError("Source has changed since compilation; compile its current version before opening this diagnostic")
            return {**identity, "attempt_id": receipt["attempt_id"], "diagnostic": index,
                    "revision": resolved["revision"], "record_id": diagnostic["record_id"], "path": resolved["path"],
                    "source_sha256": diagnostic["source_sha256"], "line": diagnostic["line"], "column": diagnostic["column"]}
        inputs, compiler = receipt["inputs"], receipt["compiler"]
        public = {key: receipt[key] for key in ("format", "attempt_id", "state", "exit_code", "reason", "inputs_sha256", "files", "diagnostics")}
        public.update(error=receipt.get("error"), snapshot_id=inputs["snapshot_id"], snapshot_sha256=inputs["snapshot_sha256"],
                      entry_path=inputs["entry_path"], compiler={**{key: compiler[key] for key in ("engine", "path", "sha256")},
                                                                "version": receipt["version"]})
        return {**identity, "receipt": public}
    except latex.LatexError as exc:
        raise ProjectError(str(exc)) from None
