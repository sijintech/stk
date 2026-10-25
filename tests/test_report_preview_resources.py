"""Two-stage document previews admit only sanitized entry bytes and explicit raster descriptors."""
import base64
import copy
import hashlib
import json
from uuid import UUID, uuid4

import pytest

from suan.agent.levels import OPERATIONS, TOOL_USES
from suan.desktop_bridge.protocol import MAX_LINE_BYTES
from suan.desktop_bridge.schema import validate_params, validate_outgoing
from suan.project import ProjectError, ProjectStore, RevisionConflict
from suan.project import report_previews, report_render, reports as storage
from suan.scripting import API, Project
from test_bridge_reports import PNG, assert_no_runs
from test_desktop_bridge import bridge_env, inproc  # noqa: F401
from test_desktop_scripts import scripts, execute  # noqa: F401
from test_report_render import Document


METHOD = "project.reports.preview_resources"
IMAGE_PATH = "images/图 #100%.png"
SOURCE = ('<h1>冻结入口</h1><img src="../images/图%20%23100%25.png">'
          '<a href="secondary.html">HTML</a><a href="secondary.md">Markdown</a>'
          '<a href="style.css">CSS</a><a href="paper.pdf">PDF</a>'
          '<a href="note.txt">Text</a><a href="#local">Anchor</a>'
          '<a href="report.html#local">Self</a><script>unsafe-script</script>')


def create(tmp_path, *, entry="report.html", source=None, images=None, secondary=True):
    store = ProjectStore.create(tmp_path / "project", "Resource preview")
    if source is None:
        source = SOURCE.replace("report.html#local", entry + "#local").encode()
    if images is None:
        images = {IMAGE_PATH: PNG}
    inputs = {"reports/" + entry: source, **images}
    if secondary:
        inputs.update({"reports/secondary.html": b'<script>secondary-script</script><h1>Raw</h1>',
                       "reports/secondary.md": b'# Secondary\n', "reports/style.css": b'body{color:red}',
                       "reports/paper.pdf": b'%PDF-1.4\n%%EOF', "reports/note.txt": b'Notes'})
    for path, data in inputs.items():
        target = store.directory / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    ids = store.files.index(list(inputs), expected_revision=0)["record_ids"]
    snapshot = store.snapshots.capture(ids, expected_revision=1)["snapshot"]
    assets = [{"record_id": identity, "path": path} for identity, path in zip(ids, inputs)]
    identity = str(uuid4())
    store.reports.create("Frozen report", snapshot["id"], ids[0], assets,
                         report_id=identity, expected_revision=2)
    report = store.reports.get(identity)["report"]
    selection = {"expected_revision": 3, "expected_source_sha256": report["source_sha256"]}
    return store, identity, report, selection, inputs


@pytest.mark.parametrize("entry", ["report.html", "report.md"])
def test_resources_are_metadata_only_and_secondary_sources_never_enter_render_map(tmp_path, monkeypatch, entry):
    store, identity, report, selection, inputs = create(tmp_path, entry=entry)
    for path in inputs:
        (store.directory / path).unlink()
    original = storage._read_asset
    calls = []
    def entry_only(owner, asset):
        calls.append(asset["path"])
        assert asset["path"] == "reports/" + entry, "image metadata must not read image contents"
        return original(owner, asset)
    monkeypatch.setattr(storage, "_read_asset", entry_only)
    result = report_previews.preview_resources(store, identity, **selection)
    assert set(result) == {"preview", "resources", "total_size"}
    preview = result["preview"]
    resource = next(a for a in report["manifest"]["assets"] if a["path"] == IMAGE_PATH)
    assert result["resources"] == [resource] and calls == ["reports/" + entry]
    data = base64.b64decode(preview["data"], validate=True)
    assert preview["renderer"] == report_render.RENDERER_ID
    assert preview["size"] == len(data) and preview["content_sha256"] == hashlib.sha256(data).hexdigest()
    source = inputs["reports/" + entry]
    assert preview["source_size"] == len(source) and preview["source_content_sha256"] == hashlib.sha256(source).hexdigest()
    assert preview["source_sha256"] == report["source_sha256"]
    assert len({preview["source_sha256"], preview["source_content_sha256"], preview["content_sha256"]}) == 3
    assert preview["project_id"] == store.info()["id"] and preview["report_id"] == identity
    assert str(UUID(preview["session_id"])) == preview["session_id"]
    assert result["total_size"] == len(data) + len(PNG)
    document = Document(data)
    assert document.attrs("img") == [{"src": "../images/%E5%9B%BE%20%23100%25.png"}]
    links = [a.get("href") for a in document.attrs("a")]
    assert links == [None, None, None, None, None, "#local", entry + "#local"]
    assert b"unsafe-script" not in data and b"secondary-script" not in data
    prefix = "/".join((preview["session_id"], preview["project_id"], identity, preview["source_sha256"], "assets"))
    path = prefix + "/images/%E5%9B%BE%20%23100%25.png"
    assert "https://stk-preview.invalid/" + path in document.csp
    assert "stk-preview://local/" + path in document.csp
    assert "secondary.html" not in document.csp
    again = report_previews.preview_resources(store, identity, **selection)
    assert again["preview"]["session_id"] != preview["session_id"]
    assert store.info()["revision"] == 3 and len(store.history()) == 3
    assert_no_runs(store)


def test_old_preview_retains_its_existing_document_mapping_and_identity_mimes(tmp_path):
    store, identity, _, selection, _ = create(tmp_path)
    legacy = report_previews.preview(store, identity, **selection)
    assert 'secondary.html' in base64.b64decode(legacy["data"]).decode()
    with pytest.raises(ProjectError, match="Markdown or HTML"):
        pdf_store, pdf_id, _, pdf_selection, _ = create(tmp_path / "pdf", entry="entry.pdf", source=b'%PDF-1.4', secondary=False)
        report_previews.preview_resources(pdf_store, pdf_id, **pdf_selection)
    assert report_previews.preview(pdf_store, pdf_id, **pdf_selection)["renderer"] == "identity"


def test_all_four_raster_mimes_are_admitted_in_original_manifest_order(tmp_path):
    images = {"raster/a.png": PNG, "raster/b.jpg": b'JPEG bytes', "raster/c.gif": b'GIF89a', "raster/d.webp": b'RIFF WebP'}
    store, identity, report, selection, _ = create(tmp_path, images=images)
    result = report_previews.preview_resources(store, identity, **selection)
    assert [a["mime"] for a in result["resources"]] == ["image/png", "image/jpeg", "image/gif", "image/webp"]
    assert result["resources"] == report["manifest"]["assets"][1:5]


def test_zero_images_and_maximum_sixty_three_descriptors(tmp_path):
    for count in (0, 63):
        store, identity, _, selection, _ = create(tmp_path / str(count), secondary=False,
            images={f'images/{i}.png': PNG for i in range(count)})
        result = report_previews.preview_resources(store, identity, **selection)
        assert len(result["resources"]) == count
        assert result["total_size"] == result["preview"]["size"] + count * len(PNG)
        assert len(json.dumps(result).encode()) < MAX_LINE_BYTES
        assert not validate_outgoing({"id": "1", "result": result}, METHOD)
        if not count:
            assert "img-src 'none'" in Document(base64.b64decode(result["preview"]["data"])).csp


def test_new_response_schema_rejects_raw_documents_and_oversized_sources(tmp_path):
    store, identity, _, selection, _ = create(tmp_path)
    result = report_previews.preview_resources(store, identity, **selection)
    assert not validate_outgoing({"id": "1", "result": result}, METHOD)
    invalid = [
        ("preview", "renderer", "identity"),
        ("preview", "mime", "application/pdf"),
        ("preview", "source_mime", "application/pdf"),
        ("preview", "source_size", 1024 * 1024 + 1),
        ("resources", "mime", "text/html; charset=utf-8"),
        ("resources", "mime", "image/bmp"),
        ("root", "total_size", 32 * 1024 * 1024 + 1),
        ("root", "unexpected", 1),
        ("preview", "unexpected", 1),
        ("resources", "unexpected", 1),
    ]
    for target, key, value in invalid:
        malformed = copy.deepcopy(result)
        obj = (malformed if target == "root" else
               malformed["resources"][0] if target == "resources" else malformed["preview"])
        obj[key] = value
        assert validate_outgoing({"id": "1", "result": malformed}, METHOD), (target, key, value)
    malformed = copy.deepcopy(result)
    malformed["resources"] *= 64
    assert validate_outgoing({"id": "1", "result": malformed}, METHOD)
    malformed = copy.deepcopy(result)
    del malformed["preview"]["source_content_sha256"]
    assert validate_outgoing({"id": "1", "result": malformed}, METHOD)
    # Additive restrictions must not narrow the existing identity-preview contract.
    legacy = copy.deepcopy(result["preview"])
    legacy.update(renderer="identity", mime="application/pdf", source_mime="application/pdf",
                  source_size=1024 * 1024 + 1)
    assert not validate_outgoing({"id": "1", "result": legacy}, "project.reports.preview")


def test_declared_resources_do_not_attest_asset_availability_or_integrity(tmp_path):
    store, identity, report, selection, _ = create(tmp_path)
    image = next(a for a in report["manifest"]["assets"] if a["path"] == IMAGE_PATH)
    object_path = store.snapshots._object(image["sha256"])
    object_path.write_bytes(b'corrupted image')
    result = report_previews.preview_resources(store, identity, **selection)
    assert result["resources"] == [image]
    with pytest.raises(ProjectError):
        store.reports.asset(identity, IMAGE_PATH, **selection)
    object_path.unlink()
    assert report_previews.preview_resources(store, identity, **selection)["resources"] == [image]
    with pytest.raises(ProjectError):
        store.reports.asset(identity, IMAGE_PATH, **selection)


@pytest.mark.parametrize("extra", [0, 1])
def test_actual_rendered_size_controls_the_full_32_mib_display_budget(tmp_path, monkeypatch, extra):
    mib = 1024 * 1024
    images = {f'images/{i}.png': b'x' * (4 * mib) for i in range(7)}
    images['images/last.png'] = b'y' * (2 * mib)
    store, identity, _, selection, _ = create(tmp_path, images=images, secondary=False)
    monkeypatch.setattr(report_render, "render_document", lambda *a, **kw: b' ' * (2 * mib + extra))
    if extra:
        with pytest.raises(ProjectError, match="32 MiB display"):
            report_previews.preview_resources(store, identity, **selection)
    else:
        result = report_previews.preview_resources(store, identity, **selection)
        assert result["total_size"] == 32 * mib
        assert len(base64.b64decode(result["preview"]["data"])) == 2 * mib
        assert len(json.dumps(result).encode()) < MAX_LINE_BYTES


def test_text_input_budget_is_checked_before_opening_entry(tmp_path, monkeypatch):
    store, identity, _, selection, _ = create(tmp_path, source=b'x' * (1024 * 1024 + 1), images={}, secondary=False)
    monkeypatch.setattr(storage, "_read_asset", lambda *a: pytest.fail("oversized rendering input was opened"))
    with pytest.raises(ProjectError, match="1 MiB"):
        report_previews.preview_resources(store, identity, **selection)


def test_render_output_keeps_the_four_mib_per_asset_limit(tmp_path, monkeypatch):
    store, identity, _, selection, _ = create(tmp_path, images={})
    monkeypatch.setattr(report_render, "render_document", lambda *a, **kw: b'x' * (4 * 1024 * 1024 + 1))
    with pytest.raises(ProjectError, match="4 MiB"):
        report_previews.preview_resources(store, identity, **selection)


def test_revision_is_rechecked_after_rendering_before_descriptors_are_published(tmp_path, monkeypatch):
    store, identity, _, selection, _ = create(tmp_path)
    original = report_render.render_document
    def concurrent_write(*args, **kwargs):
        result = original(*args, **kwargs)
        store.apply([{"op": "create_table", "id": str(uuid4()), "name": "Concurrent"}], expected_revision=3)
        return result
    monkeypatch.setattr(report_render, "render_document", concurrent_write)
    with pytest.raises(RevisionConflict):
        report_previews.preview_resources(store, identity, **selection)
    assert store.info()["revision"] == 4


def test_strict_bridge_discovery_errors_closed_handle_and_no_write_events(inproc, tmp_path, monkeypatch):
    store, identity, report, selection, _ = create(tmp_path)
    harness = inproc()
    info = harness.call("project.open", {"directory": str(store.directory)})["project"]
    project = Project(harness.call, info["handle"])
    params = {"handle": project.handle, "report_id": identity, **selection}
    assert METHOD in harness.call("hello", {"protocol": 1})["methods"]
    assert METHOD in harness.call("script.catalog")["operations"]
    assert OPERATIONS[METHOD][0] == "read" and not any(METHOD in uses for uses in TOOL_USES.values())
    before = harness.events_of("project.changed")
    result = project.reports.preview_resources(identity, **selection)
    resource = result["resources"][0]
    read = project.reports.asset(identity, resource["path"], **selection)
    assert read["size"] == resource["size"] and read["content_sha256"] == resource["sha256"]
    assert hashlib.sha256(base64.b64decode(read["data"])).hexdigest() == resource["sha256"]
    assert harness.error(METHOD, {**params, "expected_revision": 2})["code"] == "conflict"
    assert harness.error(METHOD, {**params, "expected_source_sha256": "0" * 64})["code"] == "conflict"
    assert harness.error(METHOD, {**params, "extra": 1})["code"] == "invalid_params"
    def missing(name):
        raise ProjectError("Document rendering requires Markdown and nh3 from the documents extra")
    with monkeypatch.context() as patch:
        patch.setattr(report_render, "_dependency", missing)
        assert harness.error(METHOD, params)["code"] == "invalid_params"
    assert harness.events_of("project.changed") == before
    assert project.close()
    assert harness.error(METHOD, params)["code"] == "not_found"
    harness.assert_clean()


def test_facade_preserves_original_handle_and_mandatory_guards():
    calls = []
    api = API(lambda method, params: calls.append((method, params)) or {})
    api._project_handle = 'a' * 32
    bound = api.project.reports
    api._project_handle = 'b' * 32
    identity = str(uuid4())
    bound.preview_resources(identity, expected_revision=3, expected_source_sha256='c' * 64)
    assert calls == [(METHOD, {"handle": 'a' * 32, "report_id": identity,
                              "expected_revision": 3, "expected_source_sha256": 'c' * 64})]
    with pytest.raises(TypeError):
        bound.preview_resources(identity)
    assert validate_params(METHOD, {**calls[0][1], "session_id": str(uuid4())})


def test_real_python_worker_can_prepare_then_explicitly_verify_images(scripts, tmp_path):
    store, identity, _, selection, inputs = create(tmp_path)
    info = scripts.call("project.open", {"directory": str(store.directory)})["project"]
    for path in inputs:
        (store.directory / path).unlink()
    session = scripts.call("script.open")["session"]
    code = f'''
import base64, hashlib
reports = stk.project.reports
selection = {selection!r}
result = reports.preview_resources({identity!r}, **selection)
assert result['preview']['renderer'] == 'stk.report-renderer/1'
assert len(result['resources']) == 1
resource = result['resources'][0]
asset = reports.asset({identity!r}, resource['path'], **selection)
assert asset['size'] == resource['size']
assert hashlib.sha256(base64.b64decode(asset['data'])).hexdigest() == resource['sha256']
'''
    result = execute(scripts, session, code, project_handle=info["handle"])
    assert result["run"]["state"] == "succeeded", scripts.call("script.read", {"session": session})["text"]
    assert store.info()["revision"] == 3 and len(store.history()) == 3
    assert_no_runs(store)
    scripts.assert_clean()
