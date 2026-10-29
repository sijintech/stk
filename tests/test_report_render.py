"""Real Markdown/HTML sanitization and virtual-path admission, without a browser or I/O."""

import base64
import hashlib
import html
from html.parser import HTMLParser
from urllib.parse import quote

import pytest

from suan.project import ProjectError
from suan.project import report_render
from suan.project.report_render import render_document


class Document(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.elements = []
        self.feed(source.decode("utf-8"))

    def handle_starttag(self, tag, attributes):
        self.elements.append((tag, dict(attributes)))

    def attrs(self, tag):
        return [attrs for name, attrs in self.elements if name == tag]

    @property
    def csp(self):
        return next(attrs["content"] for attrs in self.attrs("meta")
                    if attrs.get("http-equiv") == "Content-Security-Policy")


def render(source, mime="text/html", **kwargs):
    kwargs.setdefault("entry_path", "reports/report.html")
    kwargs.setdefault("asset_urls", {})
    return render_document(source.encode("utf-8") if isinstance(source, str) else source,
                           mime, **kwargs)


def body(source):
    return source.decode("utf-8").split("<body>", 1)[1].split("</body>", 1)[0]


def preview_prefix(scheme="https"):
    origin = "https://stk-preview.invalid" if scheme == "https" else "stk-preview://local"
    identity = "/".join([
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
        "33333333-3333-3333-3333-333333333333",
        "a" * 64,
    ])
    return f"{origin}/{identity}/assets/"


def test_markdown_unicode_table_fenced_code_and_source_are_preserved():
    source = """# 实验报告

| 温度 | 结果 |
| :--- | ---: |
| 300 | **通过** |

```python
print("<script>not executable</script>")
```
""".encode("utf-8")
    original = bytes(source)
    rendered = render(source, "text/markdown; charset=utf-8", title='报告 <A> & "B"')
    document = Document(rendered)
    assert rendered.startswith(b"<!doctype html>")
    assert "<h1>实验报告</h1>" in body(rendered)
    assert len(document.attrs("table")) == 1
    assert document.attrs("th") == [{"align": "left"}, {"align": "right"}]
    assert document.attrs("code") == [{"class": "language-python"}]
    assert "&lt;script&gt;not executable&lt;/script&gt;" in body(rendered)
    assert '<title>报告 &lt;A&gt; &amp; &quot;B&quot;</title>' in rendered.decode()
    assert not document.attrs("script")
    assert {"name": "generator", "content": "stk.report-renderer/1"} in document.attrs("meta")
    assert source == original


@pytest.mark.parametrize("mime", ["text/html", "text/html; charset=utf-8",
                                  'TEXT/MARKDOWN; charset="UTF-8"'])
def test_supported_mime_and_safe_semantic_html(mime):
    rendered = render('<article><h2 id="标题">Title</h2><figure>'
                      '<figcaption>Caption</figcaption></figure>'
                      '<details open><summary>More</summary><p>Text</p></details>'
                      '<a href="#%E6%A0%87%E9%A2%98">Jump</a></article>', mime)
    document = Document(rendered)
    assert document.attrs("h2") == [{"id": "标题"}]
    assert document.attrs("figure") == [{}]
    assert document.attrs("details") == [{"open": ""}]
    assert document.attrs("a")[0]["href"] == "#%E6%A0%87%E9%A2%98"


def test_exact_asset_mapping_decodes_once_and_rewrites_special_paths():
    filename = "图 像/a#b%.png"
    source_url = "../" + quote(filename, safe="/")
    destination = "../source/" + quote(filename, safe="/")
    rendered = render(
        f'<img src="{source_url}" alt="结果"><a href="{source_url}#part">Open</a>'
        '<img src="../images/%252f.png"><img src="../images/%2f.png">',
        asset_urls={filename: destination, "images/%2f.png": "../source/images/%252f.png"},
    )
    document = Document(rendered)
    assert document.attrs("img") == [
        {"src": destination, "alt": "结果"}, {"src": "../source/images/%252f.png"}, {},
    ]
    assert document.attrs("a")[0]["href"] == destination + "#part"
    assert "img-src 'none'" in document.csp  # Rewriting alone grants no CSP read permission.


def test_relative_parent_resolution_stays_inside_bundle_and_never_guesses():
    rendered = render(
        '<img src="../images/./result.png"><img src="../../images/result.png">'
        '<img src="../other/result.png"><img src="result.png">',
        asset_urls={"images/result.png": "../source/images/result.png"},
    )
    assert Document(rendered).attrs("img") == [
        {"src": "../source/images/result.png"}, {}, {}, {},
    ]


def test_markdown_local_images_and_links_use_same_manifest_policy():
    rendered = render(
        '![图](<../图 像/a%23b%25.png>)\n\n'
        '[open](../图%20像/a%23b%25.png) [outside](https://example.invalid/)',
        "text/markdown", asset_urls={"图 像/a#b%.png": "../source/图 像/a%23b%25.png"},
    )
    document = Document(rendered)
    target = "../source/" + quote("图 像/a#b%.png", safe="/")
    assert document.attrs("img") == [{"alt": "图", "src": target}]
    assert document.attrs("a")[0]["href"] == target
    assert "href" not in document.attrs("a")[1]


def test_filename_spaces_are_encoded_without_trimming_and_inputs_are_not_mutated():
    assets = {"reports/ leading image .png": "../source/ leading image .png"}
    before = dict(assets)
    document = Document(render('<img src=" leading image .png">', asset_urls=assets))
    assert document.attrs("img") == [{"src": "../source/%20leading%20image%20.png"}]
    assert assets == before


def test_deep_entry_can_reference_a_valid_asset_with_a_longer_relative_url():
    import posixpath

    entry = "d/" * 63 + "report.md"
    asset = ("b" * 15 + "/") * 60 + "image.png"
    relative = posixpath.relpath(asset, posixpath.dirname(entry))
    assert len(entry.encode()) <= 1024 and len(asset.encode()) <= 1024
    assert 1024 < len(relative.encode()) < 8192
    rendered = render(f"![Result]({relative})", "text/markdown", entry_path=entry,
                      asset_urls={entry: "report.md", asset: relative})
    assert Document(rendered).attrs("img") == [{"src": relative, "alt": "Result"}]


def test_mapped_url_budget_applies_before_and_after_encoding():
    destination = "图/" * 818 + "file0000.png"
    encoded = quote(destination, safe="/")
    assert len(destination.encode()) < 8192 and len(encoded.encode()) == 8192
    for mapped in (destination, encoded):
        rendered = render('<img src="../image.png">', asset_urls={"image.png": mapped})
        assert Document(rendered).attrs("img") == [{"src": encoded}]
    for over_budget in (destination + "x", encoded.replace("file", "%66ile")):
        with pytest.raises(ProjectError, match="assets must map"):
            render("safe", asset_urls={"image.png": over_budget})


@pytest.mark.parametrize("url", [
    "", "/images/result.png", "//example.invalid/result.png", "https://example.invalid/x",
    "http://example.invalid/x", "file:///etc/passwd", "data:image/png;base64,AAAA",
    "blob:https://example.invalid/a", "javascript:alert(1)", "mailto:user@example.invalid",
    "../images/result.png?download=1", "../images/result.png?", "../../images/result.png",
    "..\\images\\result.png", "../images/%2fresult.png", "../images/%5Cresult.png",
    "%2fimages/result.png", "../images/result%00.png", "../images/result%7f.png",
    "../images/result%C2%80.png", "../images/result\n.png", "../images/result\t.png",
    "../images/result\u0085.png", "../images/%", "../images/%gg", "../images/%ff",
    "../images/%C0%AF.png", "https%3aexample.invalid/result.png", "../images//result.png",
])
def test_unsafe_or_unlisted_urls_lose_resource_attributes(url):
    rendered = render(
        '<img src="' + html.escape(url, quote=True) + '"><a href="'
        + html.escape(url, quote=True) + '">Link</a>',
        asset_urls={"images/result.png": "../source/images/result.png"},
    )
    document = Document(rendered)
    assert all("src" not in attrs for attrs in document.attrs("img"))
    assert all("href" not in attrs for attrs in document.attrs("a"))


def test_active_elements_attributes_styles_and_source_metadata_are_removed():
    source = """<!doctype html><html><head>
    <base href="https://example.invalid/">
    <meta http-equiv="refresh" content="0;url=https://example.invalid/">
    <link rel="stylesheet" href="https://example.invalid/style.css">
    <style>drop-style @import 'https://example.invalid';</style>
    <title>drop-title</title></head><body>
    <script>drop-script</script><iframe srcdoc="<script>alert(1)</script>">drop-iframe</iframe>
    <form action="https://example.invalid"><input><p>drop-form</p></form>
    <object data="https://example.invalid">drop-object</object><embed src="https://example.invalid">
    <svg><text>drop-svg</text></svg><math><mtext>drop-math</mtext></math>
    <template><p>drop-template</p></template>
    <p style="background:url(https://example.invalid)" onclick="alert(1)">Safe</p>
    <img src="../images/result.png" onerror="alert(1)" srcset="https://example.invalid/a 1x">
    <a href="#safe" target="_blank" download ping="https://example.invalid/">Safe link</a>
    </body></html>"""
    rendered = render(source, asset_urls={"images/result.png": "result.png"})
    document = Document(rendered)
    assert "drop-" not in body(rendered)
    assert "example.invalid" not in rendered.decode()
    assert "Safe" in body(rendered)
    assert document.attrs("p") == [{}]
    assert document.attrs("img") == [{"src": "result.png"}]
    assert document.attrs("a") == [{"href": "#safe", "rel": "noopener noreferrer"}]
    assert len(document.attrs("style")) == 1  # Only the renderer's hashed default CSS.
    for forbidden in ("script", "iframe", "form", "input", "object", "embed", "svg", "math",
                      "template", "base", "link"):
        assert not document.attrs(forbidden)


@pytest.mark.parametrize("source", [
    '<svg><style><a id="</style><img src=x onerror=alert(1)>">',
    '<math><mtext><table><mglyph><style><!--</style><img title="--><img src=x onerror=alert(1)>">',
    '<p><b>safe<i>text</p></i><img/src="https://example.invalid"onerror="alert(1)">',
    '<noscript><p title="</noscript><img src=x onerror=alert(1)>">',
    '<a href="java&#x09;script:alert(1)" target="_blank">click</a>',
])
def test_malformed_html_does_not_reintroduce_active_content(source):
    document = Document(render(source))
    for tag, attrs in document.elements:
        assert tag not in {"script", "svg", "math", "iframe", "object", "form", "noscript"}
        assert not any(name.startswith("on") or name in {"target", "style"} for name in attrs)
        assert "src" not in attrs and "href" not in attrs


def test_csp_default_blocks_fetches_and_only_hash_authorizes_trusted_style():
    document = Document(render("<p>hello</p>"))
    for directive in ("default-src", "script-src", "connect-src", "frame-src", "child-src",
                      "object-src", "base-uri", "form-action", "img-src", "media-src"):
        assert f"{directive} 'none'" in document.csp
    expected = base64.b64encode(hashlib.sha256(report_render._STYLE.encode()).digest()).decode()
    assert f"style-src 'sha256-{expected}'" in document.csp
    assert "'self'" not in document.csp and "'unsafe-inline'" not in document.csp


def test_csp_host_can_admit_only_bound_preview_prefix_or_exact_asset():
    https = preview_prefix()
    custom = preview_prefix("stk-preview") + "图%20像/a%23b%25.png"
    document = Document(render("<p>hello</p>", csp_img_sources=(https, custom, https)))
    normalized = preview_prefix("stk-preview") + quote("图 像/a#b%.png", safe="/")
    assert f"img-src {https} {normalized}" in [part.strip() for part in document.csp.split(";")]
    assert "file:" not in document.csp and "'self'" not in document.csp


@pytest.mark.parametrize("source", [
    "'self'", "file:", "file:///tmp/export/source/", "https://example.invalid/assets/",
    "https://stk-preview.invalid/", "stk-preview://local/", "//stk-preview.invalid/assets/",
    preview_prefix().replace("stk-preview.invalid/", "user@stk-preview.invalid/"),
    preview_prefix().replace("stk-preview.invalid/", "stk-preview.invalid:443/"),
    preview_prefix().replace("a" * 64, "not-a-digest"),
    preview_prefix().replace("11111111-1111-1111-1111-111111111111", "bad-session"),
    preview_prefix() + "../secret.png", preview_prefix() + "a/../../secret.png",
    preview_prefix() + "image.png?q=1", preview_prefix() + "image.png#fragment",
    preview_prefix() + "%2fsecret.png", preview_prefix() + "%00.png",
    preview_prefix() + "\nhttps://example.invalid/",
])
def test_csp_rejects_unbound_or_ambiguous_image_permissions(source):
    with pytest.raises(ProjectError, match="CSP image source"):
        render("safe", csp_img_sources=(source,))


def test_csp_filename_delimiters_cannot_add_another_directive():
    source = preview_prefix() + 'image.png; img-src * & "quoted"'
    rendered = render("safe", csp_img_sources=(source,))
    csp = Document(rendered).csp
    assert 'image.png%3B%20img-src%20%2A%20%26%20%22quoted%22' in csp
    assert [item.strip().split(" ")[0] for item in csp.split(";")].count("img-src") == 1
    assert "&#x27;none&#x27;" in rendered.decode()  # CSP is HTML attribute escaped.


@pytest.mark.parametrize("entry", ["/report.html", "../report.html", "a/../report.html",
                                  "a//report.html", "a\\report.html", "http:report.html",
                                  "report.html?x", "\ud800.html", "a" * 1025])
def test_entry_path_must_be_canonical(entry):
    with pytest.raises(ProjectError, match="canonical relative"):
        render("safe", entry_path=entry)


@pytest.mark.parametrize("assets", [
    [], {"../image.png": "image.png"}, {"image.png": "/image.png"},
    {"image.png": "https://example.invalid/image.png"}, {"image.png": "//outside/image.png"},
    {"image.png": "file:///image.png"}, {"image.png": "image.png?x"},
    {"image.png": "image.png#x"}, {"image.png": "bad%image.png"},
    {"image.png": "a%2fimage.png"}, {"image.png": "image\x00.png"},
    {"image.png": "a\\image.png"}, {"image.png": "../"}, {"image.png": ".."},
    {"image.png": 42}, {"image.png": "\ud800"},
    {"a/" * 510 + "image.png": "image.png"},
])
def test_asset_map_itself_cannot_inject_absolute_or_active_urls(assets):
    with pytest.raises(ProjectError, match="assets must map"):
        render("safe", asset_urls=assets)


@pytest.mark.parametrize("mime", ["application/xhtml+xml", "text/plain", "text/markdown; charset=latin1",
                                  "text/html; charset=utf-8; x=y", None])
def test_unsupported_mime_is_an_explicit_project_error(mime):
    with pytest.raises(ProjectError, match="MIME"):
        render("safe", mime)


def test_invalid_utf8_and_non_bytes_source_are_rejected():
    with pytest.raises(ProjectError, match="valid UTF-8"):
        render(b"\xff")
    with pytest.raises(ProjectError, match="source must be bytes"):
        render_document(bytearray(b"safe"), "text/html", entry_path="report.html", asset_urls={})
    with pytest.raises(ProjectError, match="title"):
        render("safe", title="\ud800")


def test_input_limit_accepts_boundary_and_rejects_overflow_before_dependencies(monkeypatch):
    assert b"x" * report_render.MAX_INPUT_BYTES in render(b"x" * report_render.MAX_INPUT_BYTES)

    def forbidden(name):
        pytest.fail("oversized source must be rejected before dependency loading")

    monkeypatch.setattr(report_render, "_dependency", forbidden)
    with pytest.raises(ProjectError, match="1 MiB input limit"):
        render(b"x" * (report_render.MAX_INPUT_BYTES + 1))


def test_real_sanitizer_expansion_cannot_exceed_output_budget():
    # Each literal ampersand becomes '&amp;', so an admissible source can exceed 4 MiB.
    with pytest.raises(ProjectError, match="4 MiB output limit"):
        render(b"&" * report_render.MAX_INPUT_BYTES)


def test_wrapper_title_and_csp_are_included_in_output_budget(monkeypatch):
    rendered = render("safe")
    monkeypatch.setattr(report_render, "MAX_OUTPUT_BYTES", len(rendered))
    assert render("safe") == rendered
    with pytest.raises(ProjectError, match="output limit"):
        render("safe", title="x")


@pytest.mark.parametrize("missing,mime", [("nh3", "text/html"), ("nh3", "text/markdown"),
                                         ("markdown", "text/markdown")])
def test_missing_dependency_is_explicit_and_never_falls_back(monkeypatch, missing, mime):
    real_import = report_render.importlib.import_module

    def unavailable(name, *args, **kwargs):
        if name == missing:
            raise ModuleNotFoundError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(report_render.importlib, "import_module", unavailable)
    with pytest.raises(ProjectError, match=r"Markdown and nh3.*documents extra"):
        render('<script>alert(1)</script>', mime)


def test_markdown_extensions_are_objects_and_never_use_plugin_discovery(monkeypatch):
    import markdown.core

    def forbidden(*args, **kwargs):
        pytest.fail("Rendering must not discover extension entry points")

    monkeypatch.setattr(markdown.core.util, "get_installed_extensions", forbidden, raising=False)
    assert b"<table>" in render("a | b\n--|--\n1 | 2", "text/markdown")


@pytest.mark.parametrize("mime", ["text/html; charset=utf-8", "text/markdown; charset=utf-8"])
def test_listed_mp4_has_manual_native_controls_without_active_page_content(mime):
    selected = "clips/视频 #a%.mp4"
    reference = "../" + quote(selected, safe="/")
    mapped = "../source/" + quote(selected, safe="/")
    media = {selected: mapped, "clips/second.mp4": "../source/clips/second.mp4"}
    images = {"images/poster.png": "../source/images/poster.png"}
    original_media, original_images = dict(media), dict(images)
    source = (
        '<video src="' + reference + '" autoplay loop muted preload="auto" '
        'onplay="startUnsafe()" style="background:url(https://outside.invalid)">'
        '<source src="../clips/second.mp4" type="video/mp4" onerror="unsafe()">'
        '<source src="../clips/unselected.mp4" type="video/webm">'
        '<p>Manual playback fallback</p></video><script>unsafe-project-script</script>'
    ).encode()
    unchanged = bytes(source)
    document = Document(render(source, mime, asset_urls=images, media_urls=media))
    assert document.attrs("video") == [
        {"src": mapped, "controls": "", "preload": "none", "playsinline": ""},
    ]
    sources = document.attrs("source")
    assert sources[0] == {"src": "../source/clips/second.mp4", "type": "video/mp4"}
    assert "src" not in sources[1] and sources[1].get("type") in {None, "video/mp4"}
    assert "Manual playback fallback" in body(render(source, mime, media_urls=media))
    assert not document.attrs("script")
    assert all(not name.startswith("on") and name not in {"autoplay", "loop", "muted", "style"}
               for tag, attrs in document.elements if tag != "meta" for name in attrs)
    assert {"name": "generator", "content": "stk.report-renderer/2"} in document.attrs("meta")
    assert "media-src 'none'" in document.csp  # Rewriting never grants a fetch permission by itself.
    assert "script-src 'none'" in document.csp and "connect-src 'none'" in document.csp
    assert source == unchanged and media == original_media and images == original_images


def test_generic_asset_mapping_does_not_authorize_video_source():
    document = Document(render('<video src="clip.mp4"><source src="clip.mp4"></video>',
                               asset_urls={"reports/clip.mp4": "clip.mp4"}))
    assert all("src" not in attrs for tag in ("video", "source") for attrs in document.attrs(tag))
    assert "media-src 'none'" in document.csp


@pytest.mark.parametrize("url", [
    "https://outside.invalid/clip.mp4", "//outside.invalid/clip.mp4", "file:///tmp/clip.mp4",
    "data:video/mp4;base64,AAAA", "blob:https://stk-preview.invalid/movie", "javascript:play()",
    "/clips/movie.mp4", "../../clips/movie.mp4", "../clips/unselected.mp4",
    "../clips/movie.mp4?x=1", "../clips/movie.mp4#fragment", "../clips/%2fmovie.mp4",
    "../clips/%5cmovie.mp4", "../clips/movie%00.mp4", "../clips/movie%C2%80.mp4",
    "..\\clips\\movie.mp4", "../clips/%ff.mp4",
])
def test_video_and_source_reject_external_or_unselected_urls(url):
    escaped = html.escape(url, quote=True)
    document = Document(render(f'<video src="{escaped}"><source src="{escaped}"></video>',
                               media_urls={"clips/movie.mp4": "../clips/movie.mp4"}))
    assert all("src" not in attrs for tag in ("video", "source") for attrs in document.attrs(tag))
    assert document.attrs("video") == [{"controls": "", "preload": "none", "playsinline": ""}]


def test_mp4_csp_is_exact_session_asset_urls_and_keeps_other_fetches_closed():
    filename = "clips/视频 #a%.mp4"
    encoded = quote(filename, safe="/")
    https = preview_prefix() + encoded
    custom = preview_prefix("stk-preview") + encoded
    document = Document(render('<video src="../' + encoded + '"></video>',
        media_urls={filename: "../" + encoded}, csp_media_sources=(https, custom, https)))
    policies = {part.strip().split(" ", 1)[0]: part.strip().split(" ", 1)[1]
                for part in document.csp.split(";") if part.strip()}
    assert policies["media-src"] == https + " " + custom
    assert policies["img-src"] == "'none'" and policies["script-src"] == "'none'"
    assert policies["connect-src"] == "'none'" and policies["object-src"] == "'none'"
    assert "'self'" not in document.csp and "*" not in document.csp


@pytest.mark.parametrize("source", [
    "'self'", "https://outside.invalid/clip.mp4", "file:///tmp/clip.mp4", "stk-preview:",
    preview_prefix(), preview_prefix("stk-preview"),
    preview_prefix() + "clip.png", preview_prefix() + "clip.webm", preview_prefix() + "clip.mp4/",
    preview_prefix() + "../clip.mp4", preview_prefix() + "%2fclip.mp4",
    preview_prefix() + "clip.mp4?x=1", preview_prefix() + "clip.mp4#fragment",
    preview_prefix().replace("11111111-1111-1111-1111-111111111111", "wrong-session") + "clip.mp4",
    preview_prefix().replace("a" * 64, "wrong-digest") + "clip.mp4",
    preview_prefix().replace("stk-preview.invalid/", "user@stk-preview.invalid/") + "clip.mp4",
])
def test_media_csp_refuses_broad_non_mp4_or_unbound_permissions(source):
    with pytest.raises(ProjectError):
        render("safe", media_urls={"clip.mp4": "clip.mp4"}, csp_media_sources=(source,))


@pytest.mark.parametrize("media", [
    [], {"clip.png": "clip.png"}, {"clip.webm": "clip.webm"}, {"../clip.mp4": "clip.mp4"},
    {"clip.mp4": "https://outside.invalid/clip.mp4"}, {"clip.mp4": "file:///clip.mp4"},
    {"clip.mp4": "//outside.invalid/clip.mp4"}, {"clip.mp4": "clip.mp4?x=1"},
    {"clip.mp4": "clip.mp4#fragment"}, {"clip.mp4": "a%2fclip.mp4"},
    {"clip.mp4": "bad%clip.mp4"}, {"clip.mp4": 42},
])
def test_explicit_media_map_rejects_non_mp4_and_unsafe_destinations(media):
    with pytest.raises(ProjectError):
        render("safe", media_urls=media)


def test_media_filename_delimiters_stay_encoded_in_one_csp_directive():
    filename = 'clip; media-src * & "quoted".mp4'
    source = preview_prefix() + filename
    document = Document(render("safe", media_urls={filename: quote(filename, safe="/")},
                               csp_media_sources=(source,)))
    assert quote(filename, safe="/.-_~") in document.csp
    assert [part.strip().split(" ")[0] for part in document.csp.split(";")].count("media-src") == 1
