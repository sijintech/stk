"""Trusted workflow adapter for explicit local compilation of frozen TeX files.

The saved document selects output names, not filesystem paths to read. Preparation
hashes an explicitly selected compiler without executing it. Only execute_frozen
can invoke the independent document compiler; refresh and receipt reads cannot.
"""
from pathlib import Path
from uuid import UUID, uuid5

from suan.project.store import ProjectError, RevisionConflict


def attempt_identity(run_id, step, row_id, attempt):
    return str(uuid5(UUID(run_id), f"stk.workflow-local-attempt/1:{step}:{row_id}:{attempt}"))


class LatexCompileTemplate:
    id = "latex-compile/1"
    name = "Local LaTeX compilation / 本机 LaTeX 编译"
    table_id = None
    local = True
    file_input = "files"
    parameters = [
        {"name": "compiler_path", "type": "string", "label": "Compiler executable / 编译器路径"},
        {"name": "engine", "type": "string", "default": "pdflatex"},
        {"name": "entry_path", "type": "string", "default": "main.tex"},
        {"name": "assets", "type": "json", "default": []},
        {"name": "timeout_seconds", "type": "integer", "unit": "s", "default": 60},
    ]
    outputs = ["report.pdf", "stdout.txt", "stderr.txt", "compiler.txt"]

    def run(self, parameters, directory):
        raise ProjectError("LaTeX compilation requires a prepared project workflow and its bound files")

    @staticmethod
    def _assets(parameters):
        from suan.documents.latex import MAX_INPUTS, INPUT_SUFFIXES
        from suan.project.reports import _paths
        assets = parameters["assets"]
        if type(assets) is not list or not 1 <= len(assets) <= MAX_INPUTS:
            raise ProjectError("LaTeX needs 1 to 60 explicit upstream file selections")
        names, paths = [], []
        for asset in assets:
            if type(asset) is not dict or set(asset) != {"source", "path"}:
                raise ProjectError("LaTeX assets are exactly {source: upstream filename, path: virtual path}")
            source, path = asset["source"], asset["path"]
            if (type(source) is not str or not source or len(source.encode("utf-8")) > 4096
                    or type(path) is not str or path.split("/")[0].casefold().startswith("_stk")
                    or Path(path).suffix.lower() not in INPUT_SUFFIXES
                    or Path(source).suffix.lower() != Path(path).suffix.lower()):
                raise ProjectError("LaTeX assets need bounded source names and matching supported suffixes")
            names.append(source)
            paths.append(path)
        if len(set(names)) != len(names):
            raise ProjectError("Select each upstream file only once")
        _paths(paths)
        entry = parameters["entry_path"]
        if type(entry) is not str or entry not in paths or Path(entry).suffix.lower() != ".tex":
            raise ProjectError("LaTeX entry_path must select one of the .tex virtual paths")
        timeout = parameters["timeout_seconds"]
        if type(timeout) is not int or not 1 <= timeout <= 300:
            raise ProjectError("LaTeX timeout_seconds must be an integer from 1 to 300")
        return assets

    @staticmethod
    def _selection(assets, source):
        if not source or type(source.get("files")) is not dict or not source.get("snapshot_id"):
            raise ProjectError("The bound upstream step has no frozen file collection")
        available = source["files"]
        if any(asset["source"] not in available for asset in assets):
            raise ProjectError("A selected LaTeX file is missing or ambiguous in the bound upstream files")
        return [{"record_id": available[asset["source"]], "path": asset["path"]} for asset in assets]

    def freeze_workflow(self, store, parameters, source, *, expected_revision):
        from suan.documents.latex import freeze_compiler, freeze_inputs
        assets = self._assets(parameters)
        try:
            compiler = freeze_compiler(parameters["compiler_path"], engine=parameters["engine"])
        except (OSError, ValueError) as error:
            # A missing tool is not a missing project database. Keep preparation
            # failures in the project-domain error path used by bridge sessions.
            raise ProjectError("Select the absolute compiler path from an installed TeX Live or MiKTeX "
                               "(pdflatex or xelatex): " + str(error)[:512]) from None
        inputs = None
        if source["kind"] == "files":
            selection = self._selection(assets, source)
            inputs = freeze_inputs(store, source["snapshot_id"], selection,
                                   entry_path=parameters["entry_path"], expected_revision=expected_revision)
        elif source["kind"] == "simulation":
            if not source.get("remote") and any(a["source"] not in source["outputs"] for a in assets):
                raise ProjectError("A selected LaTeX file is not an output of the bound template")
        else:
            raise ProjectError("LaTeX files must come from a Files/Snapshot or simulation output")
        return {"format": "stk.latex-workflow/1", "compiler": compiler, "inputs": inputs,
                "assets": assets, "entry_path": parameters["entry_path"],
                "timeout_seconds": parameters["timeout_seconds"]}

    def execute_frozen(self, store, prepared, source, *, directory, attempt_id, cancel):
        from suan.documents.latex import compile_frozen, freeze_inputs
        if prepared.get("format") != "stk.latex-workflow/1":
            raise ProjectError("Unsupported frozen LaTeX workflow version")
        selection = self._selection(prepared["assets"], source)
        inputs = prepared["inputs"]
        if inputs is not None:
            if (source["snapshot_id"] != inputs["snapshot_id"] or
                    selection != [{"record_id": item["record_id"], "path": item["path"]} for item in inputs["assets"]]):
                raise ProjectError("Bound LaTeX files differ from the prepared snapshot selection")
        else:
            # Only metadata reads are retried. The actual compile below is one-shot.
            for retry in range(3):
                try:
                    inputs = freeze_inputs(store, source["snapshot_id"], selection,
                        entry_path=prepared["entry_path"], expected_revision=store.info()["revision"])
                    break
                except RevisionConflict:
                    if retry == 2:
                        raise
        receipt = compile_frozen(store, inputs, prepared["compiler"], attempt_id=attempt_id,
                                 directory=directory, cancel=cancel, timeout_seconds=prepared["timeout_seconds"])
        if receipt["state"] != "succeeded":
            raise ProjectError("LaTeX compilation " + receipt["state"] + ": " +
                               (receipt.get("reason") or "compiler_failed") + "; inspect this attempt's saved log")

    @staticmethod
    def check_previous_attempts(store, attempts):
        from suan.documents.latex import recover
        for previous in attempts:
            path = store.directory / previous["directory"]
            # No directory means this earlier attempt failed before the compiler
            # module established its durable execution gate. Existing incomplete,
            # unreadable or live receipts must never silently unlock another run.
            if path.exists() or path.is_symlink():
                recover(store, **previous)
