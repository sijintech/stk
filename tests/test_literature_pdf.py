"""Actual PDFium extraction of self-authored PDFs; no models or network."""
import hashlib
import os
from pathlib import Path
import sys

import pytest

from suan.literature._io import LiteratureError, inspect_pdf
from suan.literature.pdf import extract_pdf, validate_extraction


def _pdf(objects):
    data = bytearray(b"%PDF-1.7\n%self-authored-test\n")
    offsets = [0]
    for number, value in enumerate(objects, 1):
        offsets.append(len(data))
        data += f"{number} 0 obj\n".encode() + value + b"\nendobj\n"
    start = len(data)
    data += f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode()
    for offset in offsets[1:]: data += f"{offset:010d} 00000 n \n".encode()
    data += f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()
    return bytes(data)


def _stream(data):
    return f"<< /Length {len(data)} >>\nstream\n".encode() + data + b"\nendstream"


def make_pdf(pages, *, rotation=0, crop=None):
    kids = " ".join(f"{4+i*2} 0 R" for i in range(len(pages)))
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode(),
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    for number, lines in enumerate(pages):
        content = b"BT /F1 8 Tf 20 770 Td 10 TL\n"
        for line in lines:
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            content += ("(" + escaped + ") Tj T*\n").encode("latin1")
        content += b"ET\n"
        box = "" if crop is None else " /CropBox [" + " ".join(map(str, crop)) + "]"
        objects += [f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]{box} /Rotate {rotation} /Resources << /Font << /F1 3 0 R >> >> /Contents {5+number*2} 0 R >>".encode(), _stream(content)]
    return _pdf(objects)


def unicode_pdf():
    cmap = b"""/CIDInit /ProcSet findresource begin 12 dict begin begincmap
/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def
/CMapName /STKTest def /CMapType 2 def
1 begincodespacerange <0000> <FFFF> endcodespacerange
4 beginbfchar <0001> <6C49> <0002> <5B57> <0003> <03B1> <0004> <D83DDE00> endbfchar
endcmap CMapName currentdict /CMap defineresource pop end end"""
    return _pdf([
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [7 0 R] /Count 1 >>",
        b"<< /Type /Font /Subtype /Type0 /BaseFont /STKTestUnicode /Encoding /Identity-H /DescendantFonts [4 0 R] /ToUnicode 5 0 R >>",
        b"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /STKTestUnicode /CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> /FontDescriptor 6 0 R /DW 600 /CIDToGIDMap /Identity >>",
        _stream(cmap),
        b"<< /Type /FontDescriptor /FontName /STKTestUnicode /Flags 4 /FontBBox [0 -200 1000 1000] /ItalicAngle 0 /Ascent 800 /Descent -200 /CapHeight 700 /StemV 80 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents 8 0 R >>",
        _stream(b"BT /F1 18 Tf 30 700 Td <0001000200030004> Tj ET")])


@pytest.fixture
def pdf_python():
    # Dedicated env is explicit. The full repo may intentionally have no PDFium;
    # this skip must not be counted as actual-parser acceptance in that env.
    python = os.environ.get("STK_LITERATURE_TEST_PYTHON", sys.executable)
    import subprocess
    check = subprocess.run([python, "-I", "-c", "from importlib.metadata import version;assert version('pypdfium2')=='5.14.0'"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if check.returncode: pytest.skip("Explicit pinned PDFium test environment is absent")
    return python


def _extract(path, python, **kwargs):
    selected = inspect_pdf(path)
    return extract_pdf(path, python=python, expected_sha256=selected["sha256"], expected_bytes=selected["bytes"], **kwargs)


def test_every_page_beyond_old_100000_character_cutoff_retains_exact_mapping(tmp_path, pdf_python):
    pages = [[f"Page {page:02d} line {line:02d} - source traceability and ferroelectric material evidence." for line in range(65)] for page in range(25)]
    pages[12][31] = "Middle evidence QUARTZ_MIDDLE_751 connects to the numerical comparison."
    pages[-1][-1] = "Last-page evidence ZIRCON_LAST_982 is preserved after the former cutoff."
    path = tmp_path / "self-authored-long.pdf"; path.write_bytes(make_pdf(pages))
    result = _extract(path, pdf_python)
    assert result["all_pages_accounted"] is True
    assert result["page_count"] == 25
    assert result["character_count"] > 100000
    assert result["text_status"] == "mapped"
    assert result["structure_status"] == "unreviewed"
    assert "QUARTZ_MIDDLE_751" in result["pages"][12]["text"]
    assert "ZIRCON_LAST_982" in result["pages"][-1]["text"]
    for page in result["pages"]:
        assert len(page["text"]) == len(page["characters"]) == page["character_count"]
        for item in page["characters"]:
            assert item["text_end"] == item["text_start"] + 1
            assert page["text"][item["text_start"]:item["text_end"]] == chr(item["scalar"])
    marker = next(p for p in result["paragraphs"] if "ZIRCON_LAST_982" in p["text"])
    page = result["pages"][marker["page_index"]]
    assert marker["text"] == page["text"][marker["start"]:marker["end"]]
    assert any(c["box"] is not None for c in page["characters"][marker["start"]:marker["end"]])
    assert validate_extraction(result, result["source_sha256"], path.stat().st_size) is result


def test_cjk_greek_supplementary_unicode_uses_pdfium_character_indices(tmp_path, pdf_python):
    path = tmp_path / "self-authored-unicode.pdf"; path.write_bytes(unicode_pdf())
    result = _extract(path, pdf_python)
    page = result["pages"][0]
    assert page["text"] == "汉字α😀"
    assert [c["unicode"] for c in page["characters"]] == [ord(c) for c in "汉字α"] + [0xd83d,0xde00]
    assert [c["index"] for c in page["characters"]] == [0, 1, 2, 3, 4]
    assert [(c["text_start"],c["text_end"]) for c in page["characters"]] == [(0,1),(1,2),(2,3),(3,4),(3,4)]
    assert len(page["text"].encode("utf-16-le")) // 2 == 5
    assert result["paragraphs"][0]["end"] == 4


def test_rotated_cropped_page_and_no_text_are_not_silent_complete_success(tmp_path, pdf_python):
    path = tmp_path / "self-authored-cropped.pdf"
    path.write_bytes(make_pdf([["Crop and rotation evidence"], []], rotation=90, crop=[10, 10, 600, 780]))
    result = _extract(path, pdf_python)
    assert result["page_count"] == 2
    assert result["pages"][0]["rotation"] == 90
    assert result["pages"][0]["page_box"] == [10, 10, 600, 780]
    assert result["pages"][1]["status"] == "needs_ocr_or_blank"
    assert result["text_status"] == "incomplete"


def test_bad_pdf_page_budget_and_timeout_fail_without_partial_receipt(tmp_path, pdf_python):
    bad = tmp_path / "bad.pdf"; bad.write_bytes(b"%PDF-1.7\nnot a PDF")
    with pytest.raises(LiteratureError): _extract(bad, pdf_python)
    many = tmp_path / "257-pages.pdf"; many.write_bytes(make_pdf([[]] * 257))
    with pytest.raises(LiteratureError): _extract(many, pdf_python)
    good = tmp_path / "timeout.pdf"; good.write_bytes(make_pdf([["deadline evidence"]]))
    with pytest.raises(LiteratureError) as caught: _extract(good, pdf_python, timeout=0.000001)
    assert caught.value.code == "parse_timeout"


def test_extraction_source_and_exact_span_tampering_are_rejected(tmp_path, pdf_python):
    import copy
    path = tmp_path / "evidence.pdf"; path.write_bytes(make_pdf([["Known source and exact paragraph"]]))
    result = _extract(path, pdf_python)
    for mutation in [lambda r:r["pages"][0].update(text="altered"), lambda r:r["paragraphs"][0].update(start=1),
                     lambda r:r.update(source_sha256="a" * 64),lambda r:r.update(page_count=2)]:
        changed = copy.deepcopy(result); mutation(changed)
        with pytest.raises(LiteratureError): validate_extraction(changed, result["source_sha256"], result["source_bytes"])


def test_missing_pinned_parser_does_not_install_or_fallback(tmp_path):
    python=os.environ.get("STK_LITERATURE_EMPTY_PYTHON")
    if not python:pytest.skip("Explicit no-PDFium interpreter not configured")
    path=tmp_path/"owned.pdf";path.write_bytes(make_pdf([["No runtime dependency download"]]))
    with pytest.raises(LiteratureError) as caught:_extract(path,python)
    assert caught.value.code=="parser_unavailable"


def _worker_source(path):
    import importlib.util
    spec=importlib.util.spec_from_file_location("literature_source_probe",Path(__file__).parents[1]/"suan/literature/pdf_worker.py")
    worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
    data=path.read_bytes()
    return lambda:worker._source({"source":str(path),"source_sha256":hashlib.sha256(data).hexdigest(),"source_bytes":len(data)})


def _ctime(info,value):
    from types import SimpleNamespace
    fields={key:getattr(info,key) for key in ("st_dev","st_ino","st_mode","st_size","st_mtime_ns","st_ctime_ns")}
    fields["st_ctime_ns"]=value
    return SimpleNamespace(**fields)


def test_cross_api_ctime_difference_does_not_reject_unchanged_pdf(tmp_path,monkeypatch):
    source=tmp_path/"owned.pdf";data=make_pdf([["Stable fd and path API families"]]);source.write_bytes(data)
    probe=_worker_source(source);real=os.fstat;identity=source.stat().st_ino
    def descriptor_stat(fd):
        info=real(fd)
        return _ctime(info,info.st_ctime_ns+1000000) if info.st_ino==identity else info
    monkeypatch.setattr(os,"fstat",descriptor_stat)
    assert inspect_pdf(source)=={"sha256":hashlib.sha256(data).hexdigest(),"bytes":len(data)}
    assert probe()==data


@pytest.mark.parametrize("layer",["io","worker"])
def test_same_fd_api_ctime_change_still_rejects_source(tmp_path,monkeypatch,layer):
    source=tmp_path/"owned.pdf";source.write_bytes(make_pdf([["Strict same fd API"]]));probe=_worker_source(source)
    real=os.fstat;identity=source.stat().st_ino;calls=0
    def descriptor_stat(fd):
        nonlocal calls
        info=real(fd)
        if info.st_ino!=identity:return info
        calls+=1
        return _ctime(info,info.st_ctime_ns+1000000+(calls-1))
    monkeypatch.setattr(os,"fstat",descriptor_stat)
    with pytest.raises((LiteratureError,ValueError)):
        inspect_pdf(source) if layer=="io" else probe()


@pytest.mark.parametrize("layer",["io","worker"])
def test_same_path_api_ctime_change_still_rejects_source(tmp_path,monkeypatch,layer):
    source=tmp_path/"owned.pdf";source.write_bytes(make_pdf([["Strict same path API"]]));probe=_worker_source(source)
    real=Path.lstat;calls=0
    def named_stat(path,*args,**kwargs):
        nonlocal calls
        info=real(path,*args,**kwargs)
        if path!=source:return info
        calls+=1
        return _ctime(info,info.st_ctime_ns+1000000+(calls-1))
    monkeypatch.setattr(Path,"lstat",named_stat)
    with pytest.raises((LiteratureError,ValueError)):
        inspect_pdf(source) if layer=="io" else probe()
