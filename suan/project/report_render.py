"""Offline rendering of an explicitly supplied report and virtual asset manifest.

This module reads no files and fetches no URLs. The host still owns resource admission,
navigation and native browser policy; sanitization is not a browser network sandbox.
"""

import base64
import hashlib
import html
import importlib
import re
from urllib.parse import quote, unquote, urlsplit

from .store import ProjectError


RENDERER_ID = "stk.report-renderer/1"
MAX_INPUT_BYTES = 1024 * 1024
MAX_OUTPUT_BYTES = 4 * 1024 * 1024
_MAX_PATH_BYTES = 1024
_MAX_URL_BYTES = 8192
_BAD_PERCENT = re.compile(r"%(?![0-9a-fA-F]{2})")
_ENCODED_SEPARATOR = re.compile(r"%(?:2f|5c)", re.IGNORECASE)
_UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_LANGUAGE = re.compile(r"language-[A-Za-z0-9_+.-]{1,64}\Z")
_TAGS = set("""
    a abbr address article aside b bdi bdo blockquote br caption cite code col colgroup dd del
    details dfn div dl dt em figcaption figure h1 h2 h3 h4 h5 h6 hr i img kbd li main
    mark ol p pre q rp rt ruby s samp section small span strong sub summary sup
    table tbody td tfoot th thead time tr u ul var wbr
""".split())
_DROP_CONTENT = set("""
    script style iframe frame frameset form object embed svg math template noscript
    noembed noframes canvas textarea xmp plaintext title
""".split())
_ATTRIBUTES = {
    "*": {"id", "title", "lang", "dir"},
    "a": {"href"},
    "img": {"src", "alt", "width", "height"},
    "code": {"class"},
    "td": {"colspan", "rowspan", "align"},
    "th": {"colspan", "rowspan", "align", "scope"},
    "col": {"span"},
    "colgroup": {"span"},
    "ol": {"start", "reversed"},
    "li": {"value"},
    "details": {"open"},
    "time": {"datetime"},
}
_STYLE = """html { color-scheme: light dark; }
body { margin: 2rem auto; padding: 0 1.5rem; max-width: 64rem;
       font-family: system-ui, sans-serif; line-height: 1.6; overflow-wrap: anywhere; }
img { max-width: 100%; height: auto; }
table { border-collapse: collapse; max-width: 100%; }
th, td { border: 1px solid #888; padding: .4rem .65rem; }
pre { overflow-x: auto; padding: 1rem; border: 1px solid #888; }
code, kbd, samp { font-family: ui-monospace, monospace; }
blockquote { margin-left: 0; padding-left: 1rem; border-left: .2rem solid #888; }
figure { margin: 1rem 0; }
"""


def _utf8(value, *, limit=None):
    if type(value) is not str:
        return False
    try:
        length = len(value.encode("utf-8"))
        return limit is None or length <= limit
    except UnicodeError:
        return False


def _controls(value):
    return any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value)


def _canonical_path(value):
    """Decoded virtual path, with the same unambiguous components as native assets."""
    return (
        _utf8(value, limit=_MAX_PATH_BYTES)
        and bool(value)
        and not _controls(value)
        and not any(char in value for char in "\\?:")
        and all(part not in ("", ".", "..") for part in value.split("/"))
    )


def _decode(value):
    if (
        not _utf8(value, limit=_MAX_URL_BYTES)
        or _controls(value)
        or "\\" in value
        or _BAD_PERCENT.search(value)
        or _ENCODED_SEPARATOR.search(value)
    ):
        return None
    try:
        decoded = unquote(value, encoding="utf-8", errors="strict")
    except UnicodeError:
        return None
    if _controls(decoded) or "\\" in decoded:
        return None
    return decoded


def _relative_url(value, *, fragment=False):
    """Decode a relative reference without a URL parser trimming filename spaces."""
    if _decode(value) is None:
        return None
    path_value, separator, anchor_value = value.partition("#")
    if "?" in path_value or (not fragment and separator):
        return None
    path = _decode(path_value)
    anchor = _decode(anchor_value)
    if path is None or anchor is None or any(char in path for char in "?:"):
        return None
    if path.startswith("/"):
        return None
    return path, anchor, bool(separator)


def _mapped_url(value):
    parsed = _relative_url(value)
    if parsed is None:
        return None
    path = parsed[0]
    if not path or len(path.encode("utf-8")) > _MAX_URL_BYTES:
        return None
    parts = path.split("/")
    if any(not part for part in parts) or parts[-1] in (".", ".."):
        return None
    # The trusted exporter supplies destinations relative to its generated document.
    # Leading '..' is needed for ../source/...; it is never resolved against the host FS.
    # A relative reference can be longer than either canonical bundle path: each
    # ancestor of the entry contributes '../'. Keep its own URL budget, including
    # expansion when the caller supplied unescaped UTF-8 characters.
    encoded = quote(path, safe="/.-_~")
    return encoded if len(encoded.encode("ascii")) <= _MAX_URL_BYTES else None


def _asset_url(value, entry_path, assets, *, fragment):
    parsed = _relative_url(value, fragment=fragment)
    if parsed is None:
        return None
    path, anchor, has_anchor = parsed
    if not path:
        return "#" + quote(anchor, safe="-._~") if has_anchor and fragment else None
    parts = entry_path.split("/")[:-1]
    for part in path.split("/"):
        if not part:
            return None
        if part == ".":
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
        else:
            parts.append(part)
    target = "/".join(parts)
    if not _canonical_path(target) or target not in assets:
        return None
    return assets[target] + ("#" + quote(anchor, safe="-._~") if has_anchor else "")


def _image_sources(sources):
    if type(sources) is not tuple:
        raise ProjectError("Document CSP image sources must be a tuple of preview URLs")
    result = []
    for value in sources:
        if _decode(value) is None:
            raise ProjectError("Document CSP image source is not a valid preview URL")
        try:
            parsed = urlsplit(value)
        except ValueError:
            raise ProjectError("Document CSP image source is not a valid preview URL") from None
        if (
            (parsed.scheme, parsed.netloc) not in {
                ("stk-preview", "local"), ("https", "stk-preview.invalid")
            }
            or "?" in value or "#" in value
            or not parsed.path.startswith("/")
        ):
            raise ProjectError("Document CSP image source must use an admitted preview origin")
        path = _decode(parsed.path)
        parts = path[1:].split("/")
        if (
            len(parts) < 6
            or not all(_UUID.fullmatch(part) for part in parts[:3])
            or not _SHA256.fullmatch(parts[3])
            or parts[4] != "assets"
            or (parts[5:] != [""] and not _canonical_path("/".join(parts[5:])))
        ):
            raise ProjectError("Document CSP image source must bind a preview identity and assets")
        # Encode CSP delimiters as path data. Only the host's complete identity prefix,
        # or a concrete asset below it, can be granted; no wildcard or file: origin.
        canonical = parsed.scheme + "://" + parsed.netloc + quote(path, safe="/.-_~")
        if canonical not in result:
            result.append(canonical)
    return " ".join(result) if result else "'none'"


def _dependency(name):
    try:
        return importlib.import_module(name)
    except ImportError:
        raise ProjectError(
            "Document rendering requires Markdown and nh3 from the documents extra"
        ) from None


def render_document(
    source: bytes,
    mime: str,
    *,
    entry_path: str,
    asset_urls: dict[str, str],
    title: str = "",
    csp_img_sources: tuple[str, ...] = (),
) -> bytes:
    """Return a sanitized complete UTF-8 document without changing source bytes.

    ``entry_path`` and manifest keys are decoded canonical bundle paths. Mapping
    values are relative URL references (encode literal '#' and '%' as %23/%25);
    they may point to an exporter's ``../source/...`` tree. Source references are
    decoded once and must resolve to an exact manifest key without escaping the
    bundle. Neither the map nor the HTML is used to open files.

    Images are disabled by CSP by default, including in a static export. A native
    host can supply absolute preview URLs binding session/project/report/SHA256,
    ending in /assets/ or an exact asset path. This does not authorize any ordinary
    web origin or local filesystem directory. Native resource and navigation gates
    remain necessary even when these explicitly bound image sources are supplied.
    """
    if type(source) is not bytes or len(source) > MAX_INPUT_BYTES:
        raise ProjectError("Document source must be bytes within the 1 MiB input limit")
    if type(mime) is not str or not re.fullmatch(
        r"text/(?:markdown|html)(?:\s*;\s*charset\s*=\s*(?:utf-8|\"utf-8\"))?",
        mime.strip(), flags=re.IGNORECASE,
    ):
        raise ProjectError("Document MIME must be text/markdown or text/html with UTF-8 charset")
    if not _canonical_path(entry_path):
        raise ProjectError("Document entry must be a canonical relative bundle path")
    if type(asset_urls) is not dict:
        raise ProjectError("Document assets must map canonical bundle paths to relative URLs")
    assets = {}
    for path, value in asset_urls.items():
        mapped = _mapped_url(value)
        if not _canonical_path(path) or mapped is None:
            raise ProjectError("Document assets must map canonical bundle paths to relative URLs")
        assets[path] = mapped
    if not _utf8(title, limit=MAX_OUTPUT_BYTES):
        raise ProjectError("Document title must be valid bounded UTF-8 text")
    image_sources = _image_sources(csp_img_sources)
    try:
        text = source.decode("utf-8")
    except UnicodeError:
        raise ProjectError("Document source must be valid UTF-8") from None

    sanitizer = _dependency("nh3")
    if mime.strip().lower().startswith("text/markdown"):
        markdown = _dependency("markdown")
        tables = _dependency("markdown.extensions.tables")
        fences = _dependency("markdown.extensions.fenced_code")
        try:
            table_extension = tables.TableExtension()
            # Older Markdown 3 releases already emit align and lack this option.
            if "use_align_attribute" in table_extension.getConfigs():
                table_extension.setConfig("use_align_attribute", True)
            text = markdown.Markdown(extensions=[
                table_extension,
                fences.FencedCodeExtension(),
            ]).convert(text)
        except (ValueError, RecursionError):
            raise ProjectError("Document Markdown could not be rendered") from None

    def attribute(tag, name, value):
        if name in ("href", "src"):
            return _asset_url(value, entry_path, assets, fragment=tag == "a")
        if _controls(value):
            return None
        if name == "class":
            return value if _LANGUAGE.fullmatch(value) else None
        if name in ("width", "height", "colspan", "rowspan", "span"):
            return value if re.fullmatch(r"[1-9][0-9]{0,3}", value) else None
        if name in ("start", "value"):
            return value if re.fullmatch(r"-?[0-9]{1,9}", value) else None
        if name == "align":
            return value if value in {"left", "center", "right"} else None
        if name == "scope":
            return value if value in {"row", "col", "rowgroup", "colgroup"} else None
        if name == "dir":
            return value if value in {"ltr", "rtl", "auto"} else None
        return value

    try:
        body = sanitizer.clean(
            text, tags=_TAGS, clean_content_tags=_DROP_CONTENT,
            attributes=_ATTRIBUTES, attribute_filter=attribute,
            url_schemes=set(), strip_comments=True,
        )
    except (ValueError, RecursionError):
        raise ProjectError("Document HTML could not be sanitized") from None
    style_hash = base64.b64encode(hashlib.sha256(_STYLE.encode("utf-8")).digest()).decode("ascii")
    csp = (
        "default-src 'none'; script-src 'none'; connect-src 'none'; frame-src 'none'; "
        "child-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; "
        f"style-src 'sha256-{style_hash}'; img-src {image_sources}"
    )
    document = (
        '<!doctype html>\n<html><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="' + html.escape(csp, quote=True) + '">'
        '<meta name="referrer" content="no-referrer">'
        '<meta name="generator" content="' + RENDERER_ID + '">'
        '<title>' + html.escape(title, quote=True) + '</title>'
        '<style>' + _STYLE + '</style></head><body>' + body + '</body></html>\n'
    ).encode("utf-8")
    if len(document) > MAX_OUTPUT_BYTES:
        raise ProjectError("Rendered document exceeds the 4 MiB output limit")
    return document
