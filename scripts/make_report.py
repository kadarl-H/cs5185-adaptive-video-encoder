"""Generate the draft report (.docx) and slides (.pptx) from the logged results.

Run with the bundled runtime Python (it ships python-docx / python-pptx):

    python scripts/make_report.py
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"
REPORTS = ROOT / "reports"
OUT_DIR = ROOT / "report"
OUT_DIR.mkdir(exist_ok=True)

DEV = ["01_FourPeople", "02_Beauty", "03_Bosphorus", "04_HoneyBee", "07_Mobcal", "08_Shields"]
TEST = ["05_Jockey", "06_ShakeNDry", "09_Parkrun", "10_Stockholm"]


def load(name):
    path = LOGS / name
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def feature_stats(video_id):
    path = REPORTS / "features" / f"{video_id}.csv"
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    diff = [float(r["frame_diff"]) for r in rows]
    edge = [float(r["edge_fraction"]) for r in rows]
    return sum(diff) / len(diff), sum(edge) / len(edge)


def mb(value):
    return f"{int(value) / 1e6:.2f}"


# --------------------------------------------------------------------------- docx
def build_docx():
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Inches, Pt

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10.5)

    title = doc.add_heading("Content-Adaptive Video Encoding with FFmpeg / x264", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub = doc.add_paragraph("CS5185 group project — draft report")
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph(f"Date: {date.today().isoformat()}    Group: ______    Members: ______")
    doc.add_paragraph()

    doc.add_heading("1. Task and constraints", level=1)
    doc.add_paragraph(
        "Compress the twelve provided 1280x720, 30 fps, silent clips to 5% and 2% of their original "
        "file size, using only FFmpeg's libx264 encoder. The system analyses content, chooses x264 "
        "parameters from the target budget, encodes, verifies size/decodability/quality, and re-encodes "
        "when the budget is missed. Removing frames or shortening clips is not allowed."
    )
    doc.add_paragraph(
        "All encoding and muxing is done by FFmpeg. Python, OpenCV and NumPy are used only for metadata, "
        "feature extraction, quality measurement and logging."
    )

    doc.add_heading("2. System design", level=1)
    doc.add_paragraph(
        "The pipeline is a closed loop. Each stage is a separate module so that decisions and measurements "
        "can be traced from the logs:"
    )
    for item in [
        "probe: read duration/size from the dataset metadata (or ffprobe), compute target_bytes = floor(S*r) "
        "and video_bps = 0.98*8*target_bytes/T.",
        "features: per-frame mean absolute grayscale difference (temporal change) and edge-pixel fraction "
        "(spatial detail), written as CSV and a timeline figure.",
        "decision: content-dependent candidate set (preset medium / veryslow, plus either an AQ-motion or a "
        "long-GOP candidate), each candidate encoded and measured.",
        "encode: two-pass x264 with a hard VBV cap (-maxrate = target bitrate, -bufsize = 2x), feedback "
        "re-encoding up to the attempt budget; every candidate is kept on disk.",
        "evaluate: aggregate PSNR-Y (squared error summed over all pixels and frames) and MS-SSIM, plus "
        "aligned reference/output frame export.",
    ]:
        doc.add_paragraph(item, style="List Bullet")

    doc.add_heading("3. Content analysis", level=1)
    doc.add_paragraph(
        "Two cheap features already separate the development clips into three regimes: static meeting "
        "scenes, smooth low-detail motion, and fast/shaky motion with dense texture."
    )
    stats = [(v, feature_stats(v)) for v in DEV]
    table = doc.add_table(rows=1, cols=3)
    table.style = "Light Grid Accent 1"
    hdr = table.rows[0].cells
    for cell, text in zip(hdr, ["Video", "Mean frame difference", "Mean edge fraction"]):
        cell.text = text
    for video, stat in stats:
        if not stat:
            continue
        row = table.add_row().cells
        row[0].text = video
        row[1].text = f"{stat[0]:.2f}"
        row[2].text = f"{stat[1]:.3f}"

    fig = REPORTS / "features" / "07_Mobcal.png"
    if fig.exists():
        doc.add_picture(str(fig), width=Inches(6.2))
        doc.add_paragraph("Figure 1 — Feature timeline for 07_Mobcal: periodic frame-difference spikes "
                          "from camera shake, edge fraction falling as the camera pulls back.").italic = True

    doc.add_heading("4. Parameter decision and feedback", level=1)
    doc.add_paragraph(
        "The first baseline attempt used plain two-pass ABR. On these five-second clips it consistently "
        "overshot the budget by 40-50% (e.g. 4,890 kbps requested, 7,319 kbps produced; 6,828 requested, "
        "9,534 produced). The fix was a VBV constraint tied to the target bitrate. With -maxrate and "
        "-bufsize the size error fell from +5.0% to +0.2% on the worst case and PSNR improved, because "
        "bits were no longer wasted on a few over-allocated frames."
    )
    doc.add_paragraph(
        "The adaptive controller then searches a small candidate set per clip: medium-default, "
        "veryslow-default, and one content-specific candidate (AQ-motion for high-motion clips, long-GOP "
        "for static clips). Each candidate is encoded at the target bitrate and measured; the best result "
        "inside the +-3% size window is kept. This makes the adaptive run, by construction, never worse "
        "than the baseline apart from measurement noise."
    )

    doc.add_heading("5. Experiments", level=1)
    doc.add_heading("5.1 Unified baseline (development set)", level=2)
    base = [r for r in load("baseline.csv")]
    if base:
        t = doc.add_table(rows=1, cols=7)
        t.style = "Light Grid Accent 1"
        for cell, text in zip(t.rows[0].cells, ["Video", "Ratio", "Target", "Actual", "Error", "PSNR-Y", "MS-SSIM"]):
            cell.text = text
        for r in sorted(base, key=lambda x: (x["video_id"], x["ratio"])):
            cells = t.add_row().cells
            cells[0].text = r["video_id"]
            cells[1].text = r["ratio"]
            cells[2].text = f"{mb(r['target_bytes'])} MB"
            cells[3].text = f"{mb(r['actual_bytes'])} MB"
            cells[4].text = f"{float(r['rel_error']) * 100:.2f}%"
            cells[5].text = r["psnr_y_db"]
            cells[6].text = r["ms_ssim"]

    doc.add_heading("5.2 Adaptive vs baseline (development set)", level=2)
    doc.add_paragraph(
        "Both runs are constrained to the same size budget, so PSNR is directly comparable. The adaptive "
        "search wins on 8 of 12 cases, with a mean gain of only +0.03 dB while encoding time grows about "
        "5x. In other words, on this dataset parameter choice at a fixed budget moves quality far less "
        "than the budget itself does."
    )
    adaptive = {(r["video_id"], r["ratio"]): r for r in load("results.csv") if r.get("mode") == "adaptive"}
    if base and adaptive:
        t = doc.add_table(rows=1, cols=6)
        t.style = "Light Grid Accent 1"
        for cell, text in zip(t.rows[0].cells, ["Video", "Ratio", "Baseline", "Adaptive", "Delta", "Candidate"]):
            cell.text = text
        for r in sorted(base, key=lambda x: (x["video_id"], x["ratio"])):
            a = adaptive.get((r["video_id"], r["ratio"]))
            if not a:
                continue
            cells = t.add_row().cells
            cells[0].text = r["video_id"]
            cells[1].text = r["ratio"]
            cells[2].text = r["psnr_y_db"]
            cells[3].text = a["psnr_y_db"]
            cells[4].text = f"{float(a['psnr_y_db']) - float(r['psnr_y_db']):+.3f}"
            cells[5].text = a.get("candidate", "")

    fig = REPORTS / "adaptive_vs_baseline.png"
    if fig.exists():
        doc.add_picture(str(fig), width=Inches(6.4))
        doc.add_paragraph("Figure 2 — PSNR-Y at matched size budgets.").italic = True

    doc.add_heading("5.3 Held-out test set", level=2)
    doc.add_paragraph(
        "The final controller was applied once to the reserved clips (05, 06, 09, 10) without any tuning. "
        "All eight outputs met the budget; 09_Parkrun is the hardest case, losing roughly 3.6 dB between "
        "the two ratios."
    )
    rows = [r for r in load("results.csv") if r.get("mode") == "adaptive" and r["video_id"][:2] in {"05", "06", "09", "10"}]
    if rows:
        t = doc.add_table(rows=1, cols=6)
        t.style = "Light Grid Accent 1"
        for cell, text in zip(t.rows[0].cells, ["Video", "Ratio", "Actual", "Error", "PSNR-Y", "Candidate"]):
            cell.text = text
        for r in sorted(rows, key=lambda x: (x["video_id"], x["ratio"])):
            cells = t.add_row().cells
            cells[0].text = r["video_id"]
            cells[1].text = r["ratio"]
            cells[2].text = f"{mb(r['actual_bytes'])} MB"
            cells[3].text = f"{float(r['rel_error']) * 100:.2f}%"
            cells[4].text = r["psnr_y_db"]
            cells[5].text = r.get("candidate", "")

    frame = REPORTS / "frames" / "07_Mobcal_2%" / "t02.50s.png"
    if frame.exists():
        doc.add_picture(str(frame), width=Inches(6.4))
        doc.add_paragraph("Figure 3 — 07_Mobcal at 2%: reference (left) and decoded output (right) at t=2.5 s.").italic = True

    doc.add_heading("6. Discussion", level=1)
    for item in [
        "Budget headroom matters far more than parameter tuning: the same clip loses 0.5-3.6 dB when the "
        "budget drops from 5% to 2%, while preset/AQ changes at a fixed budget are worth ~0.1 dB.",
        "Content sensitivity is very uneven. 04_HoneyBee (static, fine texture) loses 0.55 dB from 5% to 2%, "
        "while 03_Bosphorus loses 3.15 dB on the same budget change, which is exactly the kind of clip an "
        "adaptive allocation should protect.",
        "VBV is essential for short clips; without it two-pass ABR overshoots by up to 50%.",
        "The search-based controller is simple and reproducible but costs ~5x encode time; the veryslow "
        "candidate rarely wins at 5%, and wins more often at 2%.",
    ]:
        doc.add_paragraph(item, style="List Bullet")

    doc.add_heading("7. Limitations and reproducibility", level=1)
    for item in [
        "Features are global per-clip statistics; no per-shot segmentation or VLM reasoning is used yet.",
        "Quality is measured with aggregate PSNR-Y and MS-SSIM only; no subjective scoring was collected.",
        "Commands: python -m src.probe, python -m src.pipeline --split dev --ratios 0.05 0.02 [--baseline], "
        "python -m scripts.summarize, python -m scripts.compare.",
        "FFmpeg build and Python package versions are recorded in the repository (tools/ is not committed).",
    ]:
        doc.add_paragraph(item, style="List Bullet")

    doc.add_heading("8. Contributions and third-party sources", level=1)
    doc.add_paragraph("Member contributions: ______ (to be completed by the group).")
    doc.add_paragraph(
        "Dataset: CS5185 course package (Xiph, SVT, NTIA and Sintel sources; see data/.../licenses). "
        "Tools: FFmpeg/libx264, OpenCV, NumPy, Matplotlib. No third-party code was copied into this project."
    )

    path = OUT_DIR / "CS5185_Project_Report.docx"
    doc.save(path)
    return path


# --------------------------------------------------------------------------- pptx
def build_pptx():
    from pptx import Presentation
    from pptx.util import Inches, Pt

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]

    def slide(title, bullets=None, image=None):
        s = prs.slides.add_slide(blank)
        box = s.shapes.add_textbox(Inches(0.6), Inches(0.35), Inches(12.1), Inches(0.9))
        tf = box.text_frame
        tf.text = title
        tf.paragraphs[0].runs[0].font.size = Pt(30)
        tf.paragraphs[0].runs[0].font.bold = True
        if bullets:
            height = Inches(1.8) if image else Inches(4.6)
            body = s.shapes.add_textbox(Inches(0.7), Inches(1.35), Inches(11.9), height)
            tfb = body.text_frame
            tfb.word_wrap = True
            for i, line in enumerate(bullets):
                p = tfb.paragraphs[0] if i == 0 else tfb.add_paragraph()
                p.text = line
                p.font.size = Pt(18)
                p.space_after = Pt(10)
        if image and Path(image).exists():
            from PIL import Image
            with Image.open(image) as im:
                ratio = im.height / im.width
            width = min(11.0, 4.1 / ratio)
            s.shapes.add_picture(str(image), Inches((13.333 - width) / 2), Inches(3.05), width=Inches(width))
        return s

    s = prs.slides.add_slide(blank)
    tb = s.shapes.add_textbox(Inches(0.8), Inches(2.2), Inches(11.7), Inches(1.4))
    tb.text_frame.text = "Content-Adaptive Video Encoding with FFmpeg / x264"
    tb.text_frame.paragraphs[0].runs[0].font.size = Pt(36)
    tb.text_frame.paragraphs[0].runs[0].font.bold = True
    sb = s.shapes.add_textbox(Inches(0.8), Inches(3.8), Inches(11.7), Inches(1.2))
    sb.text_frame.text = "CS5185 group project · 5-minute presentation · group members: ______"
    sb.text_frame.paragraphs[0].runs[0].font.size = Pt(18)

    slide("Task and constraints", [
        "12 clips, 1280x720 @ 30 fps, no audio; compress to 5% and 2% of original size.",
        "Only FFmpeg libx264 may encode; parameter tuning only, no x264 source changes.",
        "Outputs must remain complete and decodable; no frame dropping or shortening.",
        "Grading weights completeness and evidence more than raw numbers.",
    ])

    slide("System workflow", [
        "probe: metadata -> target_bytes, target bitrate (0.98 overhead margin).",
        "features: frame difference + edge fraction -> timeline.",
        "decision: content-dependent candidate set (medium / veryslow / AQ-motion or long-GOP).",
        "encode: two-pass x264 with VBV cap; feedback re-encode, candidates kept.",
        "evaluate: aggregate PSNR-Y, MS-SSIM, aligned frame pairs.",
    ])

    slide("Content features separate the clips", [
        "Static (01, 04): low frame difference, high edge density.",
        "Fast/shaky (07, 08): frame difference 17-20, edge density 0.5+.",
        "Feature timeline explains where the encoder should spend bits.",
    ], image=REPORTS / "features" / "07_Mobcal.png")

    slide("Results: adaptive vs baseline", [
        "All 12 baseline and 12 adaptive runs met the +-3% budget.",
        "Adaptive wins 8/12 at matched size, mean gain +0.03 dB, ~5x encode time.",
        "Main finding: budget dominates quality; parameters are second order.",
    ], image=REPORTS / "adaptive_vs_baseline.png")

    slide("Findings and limitations", [
        "Two-pass ABR overshoots 40-50% on 5 s clips; VBV fixes it.",
        "03_Bosphorus loses 3.15 dB from 5% to 2%; 04_HoneyBee only 0.55 dB.",
        "Search-based controller is reproducible but costly; features are clip-global.",
        "Next: per-shot feature windows, CRF search, subjective scoring.",
    ])

    path = OUT_DIR / "CS5185_Project_Slides.pptx"
    prs.save(path)
    return path


if __name__ == "__main__":
    docx_path = build_docx()
    pptx_path = build_pptx()
    print(f"DOCX: {docx_path}")
    print(f"PPTX: {pptx_path}")
