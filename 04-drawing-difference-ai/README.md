# Drawing / PDF Compare AI

Compares two PDF revisions (Tekla / structural drawings, medical lab reports & prescriptions, or any
PDF) and tells you **what changed**.

**How it works:** deterministic detection first, LLM explanation second.
LLMs are poor at spotting a `4500 -> 4800` change in a dense drawing, so:

```
PDF A ─┐   extract text+coords ─┐
       ├─► match sheets ─► align ─► text diff (words/lines) ─┐
PDF B ─┘   render pages ────────┘   pixel diff (ink) ────────┼─► classify ─► (LLM explain) ─► report
```

* **Text diff** - exact word/line differences with bounding boxes (dimensions, profiles, bolts, notes, lab values).
* **Pixel diff** - finds geometry changes (added/removed lines, plates, braces) that text can't see; regions
  already explained by text are dropped to avoid duplicates.
* **Domain layer** - `tekla` classifies member sizes / dimensions / bolts / welds / marks and summarises
  entity counts per sheet; `medical` parses lab rows (value, unit, reference range) and medication doses and
  flags out-of-range changes; `generic` for anything else.
* **LLM (optional)** - each changed region is sent as ONE side-by-side image (A left, B right) + nearby text;
  the model returns JSON (`change_type, description, old, new, severity, confidence`) and writes the executive summary.
  Backends: `ollama` (local, e.g. `llama3.2-vision`) or `anthropic` (cloud). `none` works with no LLM at all.

## Install

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run

**Web UI**
```bash
streamlit run app.py
```

**CLI**
```bash
python cli.py samples/tekla_GA101_revA.pdf samples/tekla_GA101_revB.pdf --domain tekla --out output
python cli.py samples/lab_report_A.pdf samples/lab_report_B.pdf --domain medical --out output_med

# with a local LLM
ollama pull llama3.2-vision
python cli.py old.pdf new.pdf --domain tekla --backend ollama --model llama3.2-vision

# with Claude
export ANTHROPIC_API_KEY=...
python cli.py old.pdf new.pdf --domain tekla --backend anthropic
```
Outputs in `--out`: `report.html` (self-contained, open in browser, print to PDF), `changes.json`, `changes.csv`, `images/`.

## Python API
```python
from drawing_diff import compare_pdfs, CompareOptions, write_outputs
res = compare_pdfs("a.pdf", "b.pdf", CompareOptions(domain="tekla", backend="none", out_dir="out"))
write_outputs(res, "out")
```

## Tips
* **Best accuracy for Tekla:** compare the models (IFC export or Tekla Open API, diff by GUID/profile/position)
  rather than PDFs. This project is for when only PDFs exist.
* Sheets are matched by sheet number found in the bottom-right title block (e.g. `GA-101`); otherwise by page
  index (`--match-by index` to force).
* Scanned PDFs: `--ocr` (needs `pytesseract` + Tesseract). Vector PDFs from Tekla need no OCR.
* If pages have different scale/offset, alignment uses ORB + homography only when the correction is small and sane.
* Too many tiny visual regions? Raise `--dpi` noise tolerance or lower `max_regions` in `CompareOptions`.
* **Medical:** change highlighter only, not a clinical tool; keep a human reviewer and use a local LLM (`ollama`) for patient data.
* Add a domain: subclass `Domain` in `drawing_diff/domains.py` and register it in `DOMAINS`.

## Layout
```
app.py            Streamlit UI            cli.py          command line
drawing_diff/     extract.py  PDF text/raster (PyMuPDF or pdfium+pdfplumber fallback)
                  imaging.py  align, pixel diff, crops   textdiff.py  word/line diff
                  domains.py  tekla / medical / generic  llm.py        ollama / anthropic
                  pipeline.py orchestration              report.py     HTML/JSON/CSV
samples/          demo PDFs + make_samples.py
```
