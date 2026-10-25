"""Render one explicitly opened frozen report for a newly bound native view session.

This produces bytes and identity metadata; it starts no browser, network service,
model or workflow. The host must validate every asset and close its own child view
when the project handle or preview session ends.
"""
import base64
import hashlib
import posixpath
from urllib.parse import quote
from uuid import uuid4

from .store import ProjectError, RevisionConflict


def preview(store, report_id, *, expected_revision, expected_source_sha256):
    reports = store.reports
    observed = reports.get(report_id)
    report = observed["report"]
    if observed["revision"] != expected_revision:
        raise RevisionConflict("Report preview revision is stale")
    if report["state"] != "readable" or report["source_sha256"] != expected_source_sha256:
        raise RevisionConflict("Report preview source differs from the selected manifest")
    manifest = report["manifest"]
    entry_path = manifest["entry_path"]
    entry = reports.asset(report_id, entry_path, expected_revision=expected_revision,
                          expected_source_sha256=expected_source_sha256)
    source = base64.b64decode(entry["data"], validate=True)
    session_id = str(uuid4())
    relative_urls = {asset["path"]: quote(posixpath.relpath(asset["path"], posixpath.dirname(entry_path) or "."),
                                           safe="/") for asset in manifest["assets"]}
    prefix = "/".join((session_id, store._project_id, report_id, expected_source_sha256, "assets")) + "/"
    renderer = "identity"
    data, mime = source, entry["mime"]
    if mime.split(";", 1)[0] in {"text/markdown", "text/html"}:
        from .report_render import RENDERER_ID, render_document
        data = render_document(source, mime, entry_path=entry_path, asset_urls=relative_urls,
                               title=report["name"], csp_img_sources=("stk-preview://local/" + prefix,
                                                                    "https://stk-preview.invalid/" + prefix))
        renderer = RENDERER_ID
        mime = "text/html; charset=utf-8"
    if len(data) > 4 * 1024 * 1024:
        raise ProjectError("Rendered report preview exceeds 4 MiB")
    # Rendering is not a transaction or a run. Recheck the current project and exact saved
    # manifest before publishing derived bytes; external writers can advance SQLite meanwhile.
    reports._selected(report_id, expected_revision, expected_source_sha256)
    return {"revision": expected_revision, "project_id": store._project_id, "report_id": report_id,
            "source_sha256": expected_source_sha256, "session_id": session_id, "path": entry_path,
            "mime": mime, "content_sha256": hashlib.sha256(data).hexdigest(), "size": len(data),
            "data": base64.b64encode(data).decode("ascii"), "renderer": renderer,
            "source_mime": entry["mime"], "source_content_sha256": entry["content_sha256"],
            "source_size": entry["size"]}
