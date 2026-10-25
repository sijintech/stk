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


_RASTER_MIMES = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp"})


def preview(store, report_id, *, expected_revision, expected_source_sha256):
    return _preview(store, report_id, expected_revision, expected_source_sha256, resources_only=False)


def preview_resources(store, report_id, *, expected_revision, expected_source_sha256):
    """Render an entry plus descriptors for later explicit, verified raster-image reads.

    Resource descriptors are metadata, not proof of present or valid image bytes. The host must
    read every listed image with the same revision/digest before publishing one native session.
    Secondary documents, CSS and PDF are never admitted by this rendering operation.
    """
    return _preview(store, report_id, expected_revision, expected_source_sha256, resources_only=True)


def _preview(store, report_id, expected_revision, expected_source_sha256, *, resources_only):
    reports = store.reports
    observed = reports.get(report_id)
    report = observed["report"]
    if observed["revision"] != expected_revision:
        raise RevisionConflict("Report preview revision is stale")
    if report["state"] != "readable" or report["source_sha256"] != expected_source_sha256:
        raise RevisionConflict("Report preview source differs from the selected manifest")
    manifest = report["manifest"]
    entry_path = manifest["entry_path"]
    admitted = manifest["assets"]
    resources = []
    if resources_only:
        from .report_render import MAX_INPUT_BYTES
        original = next(asset for asset in admitted if asset["path"] == entry_path)
        if original["mime"] not in {"text/markdown; charset=utf-8", "text/html; charset=utf-8"}:
            raise ProjectError("Resource preview requires a Markdown or HTML report entry")
        if original["size"] > MAX_INPUT_BYTES:
            raise ProjectError("Document source must be bytes within the 1 MiB input limit")
        resources = [asset for asset in admitted if asset["path"] != entry_path and asset["mime"] in _RASTER_MIMES]
        admitted = [original, *resources]
    entry = reports.asset(report_id, entry_path, expected_revision=expected_revision,
                          expected_source_sha256=expected_source_sha256)
    source = base64.b64decode(entry["data"], validate=True)
    session_id = str(uuid4())
    relative_urls = {asset["path"]: quote(posixpath.relpath(asset["path"], posixpath.dirname(entry_path) or "."),
                                           safe="/") for asset in admitted}
    prefix = "/".join((session_id, store._project_id, report_id, expected_source_sha256, "assets")) + "/"
    origins = ("stk-preview://local/", "https://stk-preview.invalid/")
    image_sources = tuple(origin + prefix for origin in origins)
    if resources_only:
        image_sources = tuple(origin + prefix + quote(asset["path"], safe="/")
                              for asset in resources for origin in origins)
    renderer = "identity"
    data, mime = source, entry["mime"]
    if mime.split(";", 1)[0] in {"text/markdown", "text/html"}:
        from .report_render import RENDERER_ID, render_document
        data = render_document(source, mime, entry_path=entry_path, asset_urls=relative_urls,
                               title=report["name"], csp_img_sources=image_sources)
        renderer = RENDERER_ID
        mime = "text/html; charset=utf-8"
    if len(data) > 4 * 1024 * 1024:
        raise ProjectError("Rendered report preview exceeds 4 MiB")
    total_size = len(data) + sum(asset["size"] for asset in resources)
    if resources_only:
        from .reports import MAX_TOTAL_BYTES
        if total_size > MAX_TOTAL_BYTES:
            raise ProjectError("Rendered entry and preview images exceed the 32 MiB display budget")
    # Rendering is not a transaction or a run. Recheck the current project and exact saved
    # manifest before publishing derived bytes; external writers can advance SQLite meanwhile.
    reports._selected(report_id, expected_revision, expected_source_sha256)
    result = {"revision": expected_revision, "project_id": store._project_id, "report_id": report_id,
            "source_sha256": expected_source_sha256, "session_id": session_id, "path": entry_path,
            "mime": mime, "content_sha256": hashlib.sha256(data).hexdigest(), "size": len(data),
            "data": base64.b64encode(data).decode("ascii"), "renderer": renderer,
            "source_mime": entry["mime"], "source_content_sha256": entry["content_sha256"],
            "source_size": entry["size"]}
    return {"preview": result, "resources": resources, "total_size": total_size} if resources_only else result
