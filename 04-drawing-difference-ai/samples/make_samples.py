"""Generate demo PDFs (needs: pip install reportlab).  python samples/make_samples.py"""
import os

from reportlab.lib.pagesizes import A3, A4, landscape
from reportlab.pdfgen import canvas

HERE = os.path.dirname(os.path.abspath(__file__))


def ga(path, rev_b):
    w, h = landscape(A3)
    c = canvas.Canvas(path, pagesize=(w, h))
    c.setLineWidth(1.2)
    # grid + beams
    for x in (150, 500, 850):
        c.line(x, 150, x, 700)                      # columns
    c.line(150, 700, 850, 700)                      # top beam
    c.line(150, 420, 850, 420)                      # mid beam
    c.setFont("Helvetica", 11)
    c.drawString(300, 706, "B12  HEA240" if rev_b else "B12  HEA200")
    c.drawString(660, 706, "B13  IPE300")
    c.drawString(300, 426, "B20  IPE270")
    c.drawString(155, 120, "C1  HEB240")
    c.drawString(505, 120, "C2  HEB240")
    # dimensions
    c.setFont("Helvetica", 10)
    c.drawString(300, 740, "4800" if rev_b else "4500")
    c.drawString(660, 740, "3000")
    c.line(150, 735, 500, 735); c.line(500, 735, 850, 735)
    # bolts / welds
    c.drawString(870, 700, "6xM20" if rev_b else "4xM20")
    c.drawString(870, 420, "4xM16")
    c.drawString(870, 400, "FW6")
    # brace: removed in B ; plate: added in B
    if not rev_b:
        c.line(150, 420, 500, 700)
        c.drawString(260, 520, "BR1 L100x100x10")
    else:
        c.rect(520, 440, 120, 60)
        c.drawString(525, 505, "PL12")
    # notes
    c.drawString(60, 90, "NOTE: All steel S355JR." if rev_b else "NOTE: All steel S275JR.")
    c.drawString(60, 75, "All dimensions in mm.")
    # title block
    c.rect(w - 330, 30, 300, 110)
    c.drawString(w - 320, 120, "PROJECT: WAREHOUSE FRAME")
    c.drawString(w - 320, 100, "GENERAL ARRANGEMENT")
    c.setFont("Helvetica-Bold", 16)
    c.drawString(w - 320, 60, "GA-101")
    c.setFont("Helvetica", 10)
    c.drawString(w - 160, 60, "REV B" if rev_b else "REV A")
    c.save()


def lab(path, rev_b):
    c = canvas.Canvas(path, pagesize=A4)
    w, h = A4
    y = h - 60
    def line(t, f="Helvetica", s=10):
        nonlocal y
        c.setFont(f, s); c.drawString(50, y, t); y -= 18
    line("CITY DIAGNOSTICS - LABORATORY REPORT", "Helvetica-Bold", 13)
    line("Patient ID: DEMO-0001 (synthetic data)")
    line("Report date: 2026-10-02" if not rev_b else "Report date: 2026-11-05")
    y -= 8
    line("TEST  RESULT  UNIT  REFERENCE", "Helvetica-Bold")
    line("Hemoglobin 13.2 g/dL 12.0 - 15.5" if not rev_b else "Hemoglobin 11.4 g/dL 12.0 - 15.5")
    line("Glucose 95 mg/dL 70 - 99" if not rev_b else "Glucose 96 mg/dL 70 - 99")
    line("Creatinine 0.9 mg/dL 0.6 - 1.2")
    line("TSH 2.1 mIU/L 0.4 - 4.0")
    if rev_b:
        line("Ferritin 8 ng/mL 15 - 150")
    y -= 8
    line("MEDICATIONS", "Helvetica-Bold")
    line("Metformin 500 mg twice daily" if not rev_b else "Metformin 1000 mg twice daily")
    line("Atorvastatin 20 mg at night")
    if not rev_b:
        line("Aspirin 75 mg once daily")
    y -= 8
    line("Comments: Review in 3 months." if not rev_b else "Comments: Review in 4 weeks; repeat iron studies.")
    c.save()


if __name__ == "__main__":
    ga(os.path.join(HERE, "tekla_GA101_revA.pdf"), False)
    ga(os.path.join(HERE, "tekla_GA101_revB.pdf"), True)
    lab(os.path.join(HERE, "lab_report_A.pdf"), False)
    lab(os.path.join(HERE, "lab_report_B.pdf"), True)
    print("samples written to", HERE)
