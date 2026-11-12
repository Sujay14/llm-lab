"""Unit tests using synthetic PDFs (never a real patient report) and the fake embedder."""
import pymupdf
import pytest

from services.pdf_processor import extract_pages
from services.text_chunker import chunk_pages
from services.vector_store import ReportStore
from tests.fake_ollama import embed
from utils.errors import NoTextError, PDFError


def make_pdf(pages: list[str]) -> bytes:
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((50, 60), text, fontsize=10)
    return doc.tobytes()


HEADER = "Name: Jane Testperson\nLab ID: 9988776655\n"
PAGES = [
    HEADER + "LIPID PROFILE\nTotal Cholesterol 182.5 mg/dL  Ref: <200\nLDL 101.2 mg/dL\n" + "filler line\n" * 5 + "Page 1 of 3",
    HEADER + "THYROID\nTSH 2.35 uIU/mL  Ref: 0.4 - 4.0\n" + "filler line\n" * 5 + "Page 2 of 3",
    HEADER + "VITAMIN B12\nVitamin B12 310 pg/mL  Ref: 200 - 900\n" + "filler line\n" * 5 + "Page 3 of 3",
]


def test_extracts_pages_keeps_numbers_values_and_removes_identifiers():
    result = extract_pages(make_pdf(PAGES))
    assert [p.pdf_page for p in result.pages] == [1, 2, 3]
    assert [p.printed_label for p in result.pages] == ["Page 1 of 3", "Page 2 of 3", "Page 3 of 3"]
    text = "\n".join(p.text for p in result.pages)
    assert "182.5 mg/dL" in text and "0.4 - 4.0" in text  # decimals, units, ranges untouched
    assert "Testperson" not in text and "9988776655" not in text


def test_corrupt_and_empty_files_give_friendly_errors():
    with pytest.raises(PDFError):
        extract_pages(b"this is not a pdf")
    with pytest.raises(PDFError):
        extract_pages(b"")


def test_pdf_without_text_is_rejected_not_indexed():
    doc = pymupdf.open()
    doc.new_page()  # blank page = same as a scanned/image-only PDF with no text layer
    with pytest.raises(NoTextError):
        extract_pages(doc.tobytes())


def test_chunks_never_cross_pages_and_respect_size():
    pages = extract_pages(make_pdf(PAGES)).pages
    chunks = chunk_pages(pages, size=120, overlap=40)
    assert chunks and all(len(c.text) <= 120 + 1 for c in chunks)
    for c in chunks:  # each chunk's text must come from its own page only
        assert c.text.split("\n")[0] in next(p.text for p in pages if p.pdf_page == c.pdf_page)


def test_retrieval_returns_right_page():
    chunks = chunk_pages(extract_pages(make_pdf(PAGES)).pages)
    store = ReportStore()
    store.add(chunks, [embed(c.text) for c in chunks])
    top = store.query(embed("thyroid TSH result"), 1)[0]
    assert top.pdf_page == 2 and "TSH" in top.text
    store.close()


def test_two_reports_are_isolated():
    a, b = ReportStore(), ReportStore()
    ca = chunk_pages(extract_pages(make_pdf(["Report A only: Hemoglobin 13.5 g/dL " * 3])).pages)
    cb = chunk_pages(extract_pages(make_pdf(["Report B only: Glucose 85 mg/dL " * 3])).pages)
    a.add(ca, [embed(c.text) for c in ca])
    b.add(cb, [embed(c.text) for c in cb])
    texts_a = " ".join(r.text for r in a.query(embed("glucose"), 5))
    assert "Report B" not in texts_a and "Report A" in texts_a
    a.close(); b.close()
