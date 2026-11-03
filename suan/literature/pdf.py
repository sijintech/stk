"""Explicit isolated all-page PDFium extraction, without importing PDFium here."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile

from ._io import LiteratureError, fail, inspect_pdf

MAX_OUTPUT = 64 * 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{64}\Z")


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def checksum(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def validate_extraction(value, source_sha256, source_bytes):
    """Recheck identities, complete page accounting and exact citation mappings."""
    try:
        expected = {"format", "source_sha256", "source_bytes", "parser", "all_pages_accounted", "page_count",
                    "character_count", "text_status", "structure_status", "pages", "paragraphs", "extraction_id"}
        if type(value) is not dict or set(value) != expected or value["format"] != "stk.literature-extraction/1":
            fail()
        if value["source_sha256"] != source_sha256 or value["source_bytes"] != source_bytes or value["all_pages_accounted"] is not True:
            fail("source_changed", "Extraction source identity differs")
        unsigned = {k: v for k, v in value.items() if k != "extraction_id"}
        if value["extraction_id"] != checksum(unsigned): fail()
        parser = value["parser"]
        if (type(parser) is not dict or parser.get("adapter") != "stk.pdfium-character-stream/1"
                or parser.get("pypdfium2") != "5.14.0" or parser.get("normalization") != "none"
                or parser.get("text_positions") != "unicode_scalar"
                or parser.get("unicode_mapping") != "pdfium_codepoints_and_utf16_surrogate_pairs"
                or not _SHA.fullmatch(parser.get("worker_sha256", "")) or not _SHA.fullmatch(parser.get("binary_sha256", ""))): fail()
        pages = value["pages"]
        if type(pages) is not list or not 1 <= len(pages) <= 256 or type(value["page_count"]) is not int or value["page_count"] != len(pages): fail()
        total = 0
        for number, page in enumerate(pages):
            text, chars = page["text"], page["characters"]
            if (type(page["page_index"]) is not int or page["page_index"] != number or type(text) is not str or type(chars) is not list
                    or type(page["character_count"]) is not int or page["character_count"] != len(chars)): fail()
            if page["text_sha256"] != hashlib.sha256(text.encode("utf-8")).hexdigest(): fail()
            if page["status"] not in {"mapped", "needs_review", "needs_ocr_or_blank"}: fail()
            if (type(page["page_box"]) is not list or len(page["page_box"]) != 4
                    or any(type(x) not in (int, float) or not math.isfinite(x) or abs(x)>100000 for x in [page["width"], page["height"], *page["page_box"]])
                    or min(page["width"],page["height"])<=0 or type(page["rotation"]) is not int or page["rotation"] not in (0,90,180,270)): fail()
            for i, character in enumerate(chars):
                if any(type(character[k]) is not int for k in ("index","text_start","text_end","scalar")) or character["index"] != i: fail()
                u = character["unicode"]
                if type(u) is not int or not 0 <= u <= 0xffffffff: fail()
                if type(character["generated"]) is not bool or type(character["mapping_error"]) is not bool: fail()
                box = character["box"]
                if box is not None and (type(box) is not list or len(box) != 4 or any(type(x) not in (int, float) or not math.isfinite(x) for x in box) or box[0] > box[2] or box[1] > box[3]): fail()
            index, position = 0, 0
            while index < len(chars):
                u = chars[index]["unicode"]
                pair = (0xd800 <= u <= 0xdbff and index + 1 < len(chars) and
                        0xdc00 <= chars[index + 1]["unicode"] <= 0xdfff)
                scalar = 0x10000 + ((u - 0xd800) << 10) + chars[index + 1]["unicode"] - 0xdc00 if pair else u
                invalid = scalar == 0 or scalar > 0x10ffff or 0xd800 <= scalar <= 0xdfff
                scalar = 0xfffd if invalid else scalar
                if position >= len(text) or text[position] != chr(scalar): fail()
                for raw_index in range(index, index + (2 if pair else 1)):
                    c = chars[raw_index]
                    if c["scalar"] != scalar or c["text_start"] != position or c["text_end"] != position + 1 or (invalid and not c["mapping_error"]): fail()
                index += 2 if pair else 1; position += 1
            if position != len(text): fail()
            total += len(chars)
        if type(value["character_count"]) is not int or value["character_count"] != total or total > 250000: fail()
        if value["structure_status"] != "unreviewed" or value["text_status"] != ("mapped" if all(p["status"] == "mapped" for p in pages) else "incomplete"): fail()
        if type(value["paragraphs"]) is not list or len(value["paragraphs"]) > 10000: fail()
        seen = set()
        for paragraph in value["paragraphs"]:
            if set(paragraph) != {"page_index", "start", "end", "text", "text_sha256", "paragraph_id"}: fail()
            page, start, end = paragraph["page_index"], paragraph["start"], paragraph["end"]
            if any(type(x) is not int for x in (page, start, end)) or not 0 <= page < len(pages) or not 0 <= start < end <= len(pages[page]["text"]) or end-start > 2048: fail()
            if paragraph["text"] != pages[page]["text"][start:end] or paragraph["text_sha256"] != hashlib.sha256(paragraph["text"].encode("utf-8")).hexdigest(): fail()
            identity = checksum({"source_sha256": source_sha256, "parser": parser, **{k: paragraph[k] for k in ("page_index", "start", "end", "text_sha256")}})
            if paragraph["paragraph_id"] != identity or identity in seen: fail()
            seen.add(identity)
        return value
    except LiteratureError:
        raise
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        fail("invalid_extraction", "Extraction evidence is inconsistent")


def extract_pdf(source, *, python, expected_sha256, expected_bytes, timeout=60):
    """Run the pinned parser once with a wall deadline and sanitized environment.

    The interpreter must already contain the explicitly provisioned pinned wheel.
    This function never installs a dependency or chooses another interpreter.
    """
    if (not Path(python).is_absolute() or type(expected_sha256) is not str or not _SHA.fullmatch(expected_sha256)
            or type(expected_bytes) is not int or not 5 <= expected_bytes <= 32 * 1024**2
            or type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 120): fail()
    source = Path(source)
    if inspect_pdf(source) != {"sha256": expected_sha256, "bytes": expected_bytes}:
        fail("source_changed", "PDF bytes differ from the selected version")
    worker = Path(__file__).with_name("pdf_worker.py")
    safe = {k: v for k, v in os.environ.items() if k in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG", "LC_ALL"}}
    safe["STK_TOKEN_PLAN_API_KEY"] = ""
    with tempfile.TemporaryDirectory(prefix="stk-literature-") as name:
        root = Path(name); request, output = root / "request.json", root / "extraction.json"
        request.write_bytes(canonical({"source": str(source), "source_sha256": expected_sha256, "source_bytes": expected_bytes}))
        if os.name != "nt": request.chmod(0o600)
        try:
            result = subprocess.run([str(python), "-I", str(worker), str(request), str(output)],
                                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    env=safe, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            fail("parse_timeout", "PDF extraction exceeded its time budget")
        except OSError:
            fail("parser_unavailable", "The selected PDF parser is unavailable")
        if result.returncode == 3:
            fail("parser_unavailable", "The selected interpreter has no pinned PDFium parser")
        if result.returncode or not output.is_file():
            fail("parse_failed", "PDF extraction failed or its format is unsupported")
        if output.stat().st_size > MAX_OUTPUT: fail("parse_budget", "PDF extraction exceeds its output budget")
        with output.open("rb") as stream: encoded = stream.read(MAX_OUTPUT + 1)
        if len(encoded) > MAX_OUTPUT: fail("parse_budget", "PDF extraction exceeds its output budget")
        try:
            value = json.loads(encoded.decode("utf-8"), parse_constant=lambda _: fail())
        except (ValueError, UnicodeError, RecursionError):
            fail("invalid_extraction", "PDF extraction evidence cannot be decoded")
        if value.get("parser", {}).get("worker_sha256") != hashlib.sha256(worker.read_bytes()).hexdigest():
            fail("parser_changed", "PDF parser changed during extraction")
        return validate_extraction(value, expected_sha256, expected_bytes)
