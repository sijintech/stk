"""Private one-shot PDFium worker; no parent STK/science imports.

This is process/resource isolation, not an operating-system security sandbox.
Text is PDFium character-stream order, not a claim of scholarly reading order,
table reconstruction, OCR, or scientifically reviewed paragraph boundaries.
"""
import hashlib
from importlib.metadata import distribution, version, PackageNotFoundError
import json
import math
import os
from pathlib import Path
import stat
import sys

MAX_PDF = 32 * 1024 * 1024
MAX_OUTPUT = 64 * 1024 * 1024
MAX_PAGES = 256
MAX_CHARS = 250000
FORMAT = "stk.literature-extraction/1"


class ParserUnavailable(Exception):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _deny_network(event, args):
    if event.startswith("socket."):
        raise RuntimeError("Literature worker has no network capability")


def _stamp(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def _source(request):
    path = Path(request["source"])
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError
    for parent in (*reversed(path.parents), path.parent):
        info = parent.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400 or not stat.S_ISDIR(info.st_mode):
            raise ValueError
    before = path.lstat()
    if stat.S_ISLNK(before.st_mode) or getattr(before, "st_file_attributes", 0) & 0x400 or not stat.S_ISREG(before.st_mode):
        raise ValueError
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as f:
        initial = os.fstat(f.fileno())
        # As in the parent reader: fd/path ctime can have different meanings
        # on Windows. Keep each family's own before/after comparison strict.
        if _stamp(initial)[:-1] != _stamp(before)[:-1] or not 5 <= initial.st_size <= MAX_PDF:
            raise ValueError
        data = f.read(MAX_PDF + 1)
        after, named = os.fstat(f.fileno()), path.lstat()
        if (_stamp(initial) != _stamp(after) or _stamp(before) != _stamp(named)
                or _stamp(after)[:-1] != _stamp(named)[:-1]):
            raise ValueError
    if (not data.startswith(b"%PDF-") or len(data) != request["source_bytes"] or
            len(data) != initial.st_size or hashlib.sha256(data).hexdigest() != request["source_sha256"]):
        raise ValueError
    return data


def extract(request):
    sys.addaudithook(_deny_network)
    try:
        if version("pypdfium2") != "5.14.0": raise ParserUnavailable
        import pypdfium2 as pdf
        import pypdfium2.raw as raw
    except (PackageNotFoundError, ImportError, OSError):
        raise ParserUnavailable from None
    assets = distribution("pypdfium2")
    libraries = [p for p in assets.files if str(p).endswith(("libpdfium.so", "pdfium.dll", "libpdfium.dylib"))]
    if len(libraries) != 1:
        raise ValueError
    parser = {"adapter": "stk.pdfium-character-stream/1", "pypdfium2": version("pypdfium2"),
              "pdfium": str(pdf.PDFIUM_INFO), "binary_sha256": hashlib.sha256(assets.locate_file(libraries[0]).read_bytes()).hexdigest(),
              "worker_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "reading_order": "pdfium_stream_unreviewed", "normalization": "none", "paragraphs": "line_hypotheses_split_at_2048",
              "text_positions": "unicode_scalar", "unicode_mapping": "pdfium_codepoints_and_utf16_surrogate_pairs"}
    pages, paragraphs, total = [], [], 0
    with pdf.PdfDocument(_source(request)) as doc:
        if not 1 <= len(doc) <= MAX_PAGES:
            raise ValueError
        for number in range(len(doc)):
            page, textpage = doc[number], None
            try:
                textpage = page.get_textpage()
                count = textpage.count_chars()
                if count < 0 or total + count > MAX_CHARS:
                    raise ValueError
                total += count
                width, height = page.get_size()
                bbox = list(page.get_bbox())
                if not all(math.isfinite(x) and abs(x) <= 100000 for x in (width, height, *bbox)) or min(width, height) <= 0:
                    raise ValueError
                chars, text, diagnostics = [], [], []
                for index in range(count):
                    u = raw.FPDFText_GetUnicode(textpage, index)
                    generated = raw.FPDFText_IsGenerated(textpage, index)
                    map_error = raw.FPDFText_HasUnicodeMapError(textpage, index)
                    box = None
                    try:
                        candidate = list(textpage.get_charbox(index))
                        if (len(candidate) == 4 and all(math.isfinite(v) and abs(v) <= 100000 for v in candidate)
                                and candidate[0] <= candidate[2] and candidate[1] <= candidate[3]):
                            box = candidate
                    except (ValueError, RuntimeError):
                        pass
                    chars.append({"index": index, "unicode": u, "box": box, "generated": generated == 1,
                                  "mapping_error": generated < 0 or map_error != 0})
                # PDFium can expose a supplementary scalar as two UTF-16
                # surrogate character indices. Both indices retain their raw
                # geometry and map to the SAME Python Unicode-scalar span.
                index = 0
                while index < count:
                    u = chars[index]["unicode"]
                    pair = (0xd800 <= u <= 0xdbff and index + 1 < count and
                            0xdc00 <= chars[index + 1]["unicode"] <= 0xdfff)
                    scalar = 0x10000 + ((u - 0xd800) << 10) + chars[index + 1]["unicode"] - 0xdc00 if pair else u
                    invalid = scalar == 0 or scalar > 0x10ffff or 0xd800 <= scalar <= 0xdfff
                    scalar = 0xfffd if invalid else scalar
                    character = chr(scalar); position = len(text)
                    for raw_index in range(index, index + (2 if pair else 1)):
                        item = chars[raw_index]
                        item.update(scalar=scalar, text_start=position, text_end=position + 1,
                                    mapping_error=item["mapping_error"] or invalid)
                        if item["mapping_error"] or (item["box"] is None and not character.isspace()):
                            diagnostics.append({"character_index": raw_index,
                                "code": "unicode_mapping" if item["mapping_error"] else "missing_geometry"})
                    text.append(character); index += 2 if pair else 1
                text = "".join(text)
                status = "needs_ocr_or_blank" if not text.strip() else "needs_review" if diagnostics else "mapped"
                pages.append({"page_index": number, "width": width, "height": height, "page_box": bbox,
                              "rotation": page.get_rotation(), "character_count": count, "text": text,
                              "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                              "characters": chars, "status": status, "diagnostics": diagnostics})
                cursor = 0
                for line in text.splitlines(keepends=True):
                    end = cursor + len(line)
                    start, stop = cursor, end
                    while start < stop and text[start].isspace(): start += 1
                    while stop > start and text[stop - 1].isspace(): stop -= 1
                    for begin in range(start, stop, 2048):
                        finish = min(begin + 2048, stop)
                        value = text[begin:finish]
                        item = {"page_index": number, "start": begin, "end": finish,
                                "text": value, "text_sha256": hashlib.sha256(value.encode("utf-8")).hexdigest()}
                        item["paragraph_id"] = digest({"source_sha256": request["source_sha256"], "parser": parser,
                                                        **{k: item[k] for k in ("page_index", "start", "end", "text_sha256")}})
                        paragraphs.append(item)
                    cursor = end
                if cursor != len(text):
                    raise ValueError
            finally:
                if textpage is not None: textpage.close()
                page.close()
    result = {"format": FORMAT, "source_sha256": request["source_sha256"], "source_bytes": request["source_bytes"],
              "parser": parser, "all_pages_accounted": True, "page_count": len(pages), "character_count": total,
              "text_status": "mapped" if all(p["status"] == "mapped" for p in pages) else "incomplete",
              "structure_status": "unreviewed", "pages": pages, "paragraphs": paragraphs}
    result["extraction_id"] = digest(result)
    return result


def main():
    # Resource bounds supplement the parent's wall timeout; there is no runtime
    # install/download fallback, external document action, or model invocation.
    if os.name == "posix":
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
        resource.setrlimit(resource.RLIMIT_CPU, (120, 120))
    request_path, output_path = map(Path, sys.argv[1:])
    raw = request_path.read_bytes()
    if len(raw) > 4096: raise ValueError
    request = json.loads(raw)
    if set(request) != {"source", "source_sha256", "source_bytes"}: raise ValueError
    result = canonical(extract(request))
    if len(result) > MAX_OUTPUT: raise ValueError
    with output_path.open("xb") as f:
        f.write(result); f.flush(); os.fsync(f.fileno())


if __name__ == "__main__":
    try:
        main()
    except ParserUnavailable:
        raise SystemExit(3)
    except Exception:
        # No source paths, PDF text, passwords, or raw third-party errors in logs.
        raise SystemExit(2)
