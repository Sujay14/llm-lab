"""Command line: python cli.py old.pdf new.pdf --domain tekla --backend ollama"""
import argparse

from drawing_diff import CompareOptions, compare_pdfs, write_outputs


def main():
    ap = argparse.ArgumentParser(description="Compare two PDFs (drawings / medical docs) and explain the differences.")
    ap.add_argument("pdf_a", help="old revision (A)")
    ap.add_argument("pdf_b", help="new revision (B)")
    ap.add_argument("--domain", default="tekla", choices=["generic", "tekla", "medical"])
    ap.add_argument("--backend", default="none", choices=["none", "ollama", "anthropic"],
                    help="LLM used to explain visual changes (none = rule-based only)")
    ap.add_argument("--model", default=None, help="e.g. llama3.2-vision or claude-sonnet-5-5")
    ap.add_argument("--ollama-host", default="http://localhost:11434")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--llm-text", action="store_true", help="also LLM-explain text changes")
    ap.add_argument("--no-visual", action="store_true", help="skip the pixel diff")
    ap.add_argument("--visual", action="store_true", help="force the pixel diff on")
    ap.add_argument("--ocr", action="store_true", help="OCR scanned PDFs (needs pytesseract)")
    ap.add_argument("--match-by", default="auto", choices=["auto", "index"])
    ap.add_argument("--out", default="output")
    a = ap.parse_args()

    opts = CompareOptions(domain=a.domain, dpi=a.dpi, backend=a.backend, model=a.model, ollama_host=a.ollama_host,
                          llm_text=a.llm_text, ocr=a.ocr, match_by=a.match_by, out_dir=a.out,
                          visual=False if a.no_visual else True if a.visual else None)
    res = compare_pdfs(a.pdf_a, a.pdf_b, opts, progress=lambda m, f=None: print("..", m))
    paths = write_outputs(res, a.out)
    print("\n" + res["summary"])
    for c in res["changes"]:
        print(f"{c['id']} [{c['severity']:6}] [{c['page']}] {c['description']}")
    print("\nReport:", paths["html"])


if __name__ == "__main__":
    main()
