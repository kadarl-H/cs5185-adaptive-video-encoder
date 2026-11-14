"""Create report v2: update limitations/contributions and append supplementary summary."""
from __future__ import annotations

import csv
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "report" / "CS5185_Project_Report.docx"
DST = ROOT / "report" / "CS5185_Project_Report_v2.docx"
LOGS = ROOT / "logs"


def load(name):
    with (LOGS / name).open(encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def add_table(doc, header, rows):
    t = doc.add_table(rows=1, cols=len(header))
    t.style = "Table Grid"
    for i, text in enumerate(header):
        c = t.rows[0].cells[i]
        c.text = str(text)
        for p in c.paragraphs:
            for r in p.runs:
                r.bold = True
                r.font.size = Pt(8)
    for row in rows:
        cells = t.add_row().cells
        for i, text in enumerate(row):
            cells[i].text = str(text)
            for p in cells[i].paragraphs:
                for r in p.runs:
                    r.font.size = Pt(8)
    doc.add_paragraph()


def main():
    doc = Document(SRC)
    style = doc.styles["Normal"]
    style.element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")

    for p in doc.paragraphs:
        if p.text.startswith("Quality is measured with aggregate PSNR-Y"):
            p.text = ("Quality is measured with aggregate PSNR-Y and MS-SSIM. "
                      "A subjective scoring kit (reports/subjective/index.html, six side-by-side sheets) "
                      "was prepared; the scores still need to be filled in by the group.")
        if p.text.startswith("Member contributions:"):
            p.text = ("Member contributions are listed in the supplementary document "
                      "(section 9); each member should confirm the percentages.")

    doc.add_heading("9. Supplementary experiments", level=1)
    doc.add_paragraph(
        "A companion document, CS5185_Experiments_Addendum.docx, contains the full tables: "
        "test-set baseline, GOP sensitivity, per-video decision table, 2x2 ablation, "
        "subjective comparison sheets and the optional LLM decision experiment. "
        "The key results are summarised here."
    )

    doc.add_heading("9.1 Baseline GOP sensitivity", level=2)
    add_table(doc, ["Baseline", "Mean PSNR (12 dev tasks)", "Adaptive vs it"], [
        ["medium / default GOP 250 / AQ1", "38.94 dB", "+0.026 dB, 8/12"],
        ["medium / GOP 60 / AQ1", "38.81 dB", "+0.161 dB, 12/12"],
    ])
    doc.add_paragraph(
        "GOP60 is 0.135 dB worse than the default GOP on these 5-second clips because it inserts "
        "about two extra I-frames at a fixed bitrate. The adaptive gain therefore looks larger "
        "against GOP60, but that is a weaker baseline, not a stronger method."
    )

    doc.add_heading("9.2 Test set with baseline", level=2)
    base = {(r["video_id"], r["ratio"]): r for r in load("baseline.csv") if r["mode"] == "baseline"}
    ada = {(r["video_id"], r["ratio"]): r for r in load("results.csv") if r["mode"] == "adaptive"}
    rows = []
    for vid in ("05_Jockey", "06_ShakeNDry", "09_Parkrun", "10_Stockholm"):
        for ratio in ("5%", "2%"):
            b, a = base[(vid, ratio)], ada[(vid, ratio)]
            rows.append([vid, ratio, f'{float(b["psnr_y_db"]):.3f}',
                         f'{float(a["psnr_y_db"]):.3f}',
                         f'{float(a["psnr_y_db"]) - float(b["psnr_y_db"]):+.3f}'])
    add_table(doc, ["Video", "Ratio", "Baseline PSNR", "Adaptive PSNR", "Delta"], rows)
    doc.add_paragraph(
        "Adaptive wins 7 of 8 held-out tasks (+0.042 dB on average); the only loss is "
        "10_Stockholm @5% (-0.159 dB), where both methods select medium and the gap comes from "
        "the rate-control landing point rather than from the parameter choice."
    )

    doc.add_heading("9.3 2x2 ablation and decision table", level=2)
    doc.add_paragraph(
        "The ablation (medium/slow x AQ1/AQ2, default GOP) shows that AQ is the dominant knob: "
        "AQ2 changes PSNR by +0.02 to +0.03 dB on 01, about -0.01 dB on 03, and -0.18 to -0.19 dB "
        "on 07_Mobcal, whose edge fraction is 0.54. Slow changes PSNR by at most 0.05 dB in most "
        "cases. The per-video table shows that the content-specific candidate wins only once "
        "(aq-motion on 02_Beauty @5%), which explains the modest overall gain."
    )

    doc.save(DST)
    print("written", DST)


if __name__ == "__main__":
    main()
