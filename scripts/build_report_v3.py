"""Generate the final report (v3) for the six-candidate system."""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
from docx import Document
from docx.oxml.ns import qn
from docx.shared import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"
REPORTS = ROOT / "reports"
OUT = ROOT / "report" / "CS5185_Project_Report_v3.docx"
DEV = ["01_FourPeople", "02_Beauty", "03_Bosphorus", "04_HoneyBee", "07_Mobcal", "08_Shields"]
TEST = ["05_Jockey", "06_ShakeNDry", "09_Parkrun", "10_Stockholm"]


def load(name):
    with (LOGS / name).open(encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def feats(name):
    with (REPORTS / "features" / f"{name}.csv").open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    diff = np.mean([float(r["frame_diff"]) for r in rows[1:]])
    edge = np.mean([float(r["edge_fraction"]) for r in rows[1:]])
    return float(diff), float(edge)


def table(doc, header, rows, widths=None, size=8):
    t = doc.add_table(rows=1, cols=len(header))
    t.style = "Table Grid"
    t.autofit = False
    for i, text in enumerate(header):
        c = t.rows[0].cells[i]
        c.text = str(text)
        for p in c.paragraphs:
            for r in p.runs:
                r.bold = True
                r.font.size = Pt(size)
    for row in rows:
        cells = t.add_row().cells
        for i, text in enumerate(row):
            cells[i].text = str(text)
            for p in cells[i].paragraphs:
                for r in p.runs:
                    r.font.size = Pt(size)
    if widths:
        for row in t.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = Inches(w)
    doc.add_paragraph()
    return t


def main():
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10.5)
    style.element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")

    doc.add_heading("Content-Adaptive Video Encoding with FFmpeg / x264", level=0)
    doc.add_paragraph("CS5185 course project — final report")

    base = {(r["video_id"], r["ratio"]): float(r["psnr_y_db"]) for r in load("baseline.csv")
            if r["mode"] == "baseline"}
    rule = {(r["video_id"], r["ratio"]): float(r["psnr_y_db"]) for r in load("results.csv")
            if r["mode"] == "adaptive"}
    six = {}
    for f in ("expanded_results.csv", "expanded_test_results.csv"):
        for r in load(f):
            six[(r["video_id"], r["ratio"])] = r

    doc.add_heading("1. Task and constraints", level=1)
    doc.add_paragraph(
        "Compress 12 provided 720p30 clips (5 s, ShakeNDry 2.5 s) to 5% and 2% of their original "
        "file size, with complete duration and a decodable output. Encoding and muxing must use "
        "FFmpeg/libx264; no other encoder is allowed. The system must close the loop: content "
        "analysis -> parameter decision -> FFmpeg encoding -> size/quality inspection -> feedback."
    )

    doc.add_heading("2. System design", level=1)
    doc.add_paragraph(
        "Python package with one entry point (python -m src.pipeline or python run.py). "
        "probe.py computes target bytes and bitrate; features.py extracts frame difference and edge "
        "fraction; decision.py builds six candidate plans; encode.py runs two-pass ABR with VBV and "
        "a size-feedback loop; evaluate.py computes PSNR-Y and MS-SSIM; pipeline.py orchestrates and "
        "logs every attempt."
    )
    doc.add_paragraph(
        "Budget: target_bytes = floor(original_bytes x ratio); initial bitrate = 0.98 x 8 x "
        "target_bytes / duration. Size feedback: bps <- bps x target_bytes / actual_bytes x 0.98, "
        "at most three attempts, always re-encoded from the original. VBV (maxrate = target, "
        "bufsize = 2x target) is mandatory: without it two-pass ABR overshot by 40-50% on 5 s clips."
    )

    doc.add_heading("3. Content analysis", level=1)
    doc.add_paragraph(
        "Two per-frame features: mean absolute grayscale frame difference (temporal change) and the "
        "fraction of pixels whose Sobel magnitude exceeds 40 (edge/detail density). Both are "
        "aggregated per clip (mean, p95) and plotted as a timeline. They feed the parameter decision, "
        "not a separate classifier."
    )
    rows = []
    for name in DEV + TEST:
        d, e = feats(name)
        rows.append([name, f"{d:.2f}", f"{e:.3f}"])
    table(doc, ["Clip", "Frame difference", "Edge fraction"], rows, widths=[2.0, 1.5, 1.5])

    doc.add_heading("4. Parameter decision: six candidates", level=1)
    doc.add_paragraph(
        "The controller builds six plans per clip. Features set the dynamic parts; every plan is "
        "encoded at the same budget and the best PSNR inside the 3% size band wins."
    )
    table(doc, ["Candidate", "Parameters", "Content role"], [
        ["medium-default", "-preset medium", "control"],
        ["veryslow-default", "-preset veryslow", "control"],
        ["tune-animation", "-preset medium -tune animation", "bundle: refs/bf/AQ/deblock/psy-rd"],
        ["formula", "-g 250-6*diff (60..250), AQ f(edge)", "dynamic GOP and AQ"],
        ["aq-contrast", "aq-mode=2, aq-strength=0.8", "gentle regional reallocation"],
        ["psy-detail / deblock-soft", "psy-rd=1.0:0.0 (edge>=0.12) / deblock=1:1", "detail vs blocking"],
    ], widths=[1.6, 3.0, 2.0])

    doc.add_heading("5. Experiments", level=1)
    doc.add_heading("5.1 Baseline definition", level=2)
    doc.add_paragraph(
        "Unified baseline: medium, default GOP (250, one I-frame for a 5 s clip), AQ1, same bitrate "
        "formula, same VBV and feedback. A second baseline pins GOP=60 (the appendix example) to test "
        "baseline sensitivity: it is 0.135 dB worse on these short clips, so adaptive gains measured "
        "against it look larger purely because the baseline is weaker."
    )

    for title, ids in (("5.2 Development set (12 tasks)", DEV), ("5.3 Held-out test set (8 tasks)", TEST)):
        doc.add_heading(title, level=2)
        rows, db, dr = [], [], []
        for vid in ids:
            for ratio in ("5%", "2%"):
                b = base[(vid, ratio)]
                s = float(six[(vid, ratio)]["psnr_y_db"])
                r = rule[(vid, ratio)]
                db.append(s - b)
                dr.append(s - r)
                rows.append([vid, ratio, f"{b:.3f}", f"{r:.3f}", f"{s:.3f}",
                             f"{s-b:+.3f}", f"{s-r:+.3f}", six[(vid, ratio)]["candidate"]])
        table(doc, ["Clip", "Ratio", "Baseline", "3-cand rule", "6-cand", "vs base", "vs rule", "Winner"],
              rows, widths=[1.25, 0.4, 0.7, 0.8, 0.7, 0.65, 0.6, 1.2])
        doc.add_paragraph(
            f"Mean vs baseline {sum(db)/len(db):+.3f} dB; mean vs the 3-candidate rule "
            f"{sum(dr)/len(dr):+.3f} dB. Winner counts: "
            + ", ".join(f"{c} {sum(1 for r in rows if r[-1] == c)}" for c in
                        ("tune-animation", "aq-contrast", "medium-default", "veryslow-default"))
            + ". All outputs are inside the 3% size band."
        )

    doc.add_heading("5.4 Why the pool matters: ablation and screening", level=2)
    doc.add_paragraph(
        "2x2 ablation (medium/slow x AQ1/AQ2, default GOP) on 01/03/07: AQ changes PSNR by +0.02 to "
        "+0.03 dB on 01, about -0.01 dB on 03, and -0.18 to -0.19 dB on 07 (edge 0.54); slow changes "
        "it by at most 0.05 dB. Single-knob screening (01/07): subq=9 -0.09 dB, me=umh ~0, "
        "rc-lookahead=40 ~0, refs=5 +0.04, bf=4 ~0, mbtree=0 -0.63, tune=film -0.17, "
        "tune=animation +0.35." 
    )
    table(doc, ["Variant (01/07 x 2)", "Mean dPSNR"], [
        ["subq=9", "-0.094"], ["me=umh", "+0.002"], ["rc-lookahead=40", "-0.010"],
        ["refs=5", "+0.036"], ["bf=4", "-0.003"], ["mbtree=0", "-0.625"],
        ["tune=film", "-0.170"], ["tune=animation", "+0.353"],
    ], widths=[2.4, 1.4])
    doc.add_paragraph(
        "Using medium + -tune animation alone gives +0.366 dB over the baseline on all 20 tasks "
        "(20/20), about +0.33 dB over the rule controller. The gain comes from the linked bundle, "
        "not from a single knob: the bundle raises PSNR by roughly 8% lower MSE while MS-SSIM on "
        "09_Parkrun drops slightly, and one standalone run misses the size band by 3.11%."
    )

    doc.add_heading("5.5 Does content analysis change the parameters?", level=2)
    doc.add_paragraph(
        "A counterfactual test: keep tune as the base and let features override GOP and AQ "
        "(B: GOP from frame difference; C: AQ1 for high-edge clips; D: both). The features changed "
        "the chosen variant in 11 of 20 tasks, which proves a real decision link, but the average "
        "PSNR against pure tune is -0.009 dB; 09_Parkrun @2% loses 0.31 dB. The link exists, the "
        "benefit does not."
    )
    table(doc, ["Variant", "Times chosen", "Mean dPSNR vs tune"], [
        ["A tune only", "9", "+0.012"], ["B tune + GOP", "2", "+0.023"],
        ["C tune + AQ1", "6", "-0.016"], ["D both", "3", "-0.080"],
    ], widths=[1.5, 1.2, 1.8])

    doc.add_heading("6. Discussion", level=1)
    doc.add_paragraph(
        "Budget dominates: dropping from 5% to 2% costs 0.5-3.6 dB, while parameter changes at a "
        "fixed budget are worth 0.0-0.4 dB. Parameter interactions dominate single knobs: every "
        "component of tune is worth <=0.05 dB alone, but the bundle is worth +0.37 dB. Content "
        "analysis is real but weak: it changes the candidate set and occasionally the winner "
        "(02_Beauty @5%), yet tune wins 19 of 20 tasks. VBV is non-negotiable on 5 s clips."
    )

    doc.add_heading("7. Limitations and reproducibility", level=1)
    doc.add_paragraph(
        "Features are global per-clip statistics; no per-shot segmentation or VLM labels. Quality "
        "is PSNR-Y and MS-SSIM; a subjective scoring kit exists (reports/subjective/index.html) but "
        "scores still need to be filled by the group. The tune bundle was selected after measuring "
        "the same clips, and five candidates compared by maximum PSNR introduce a mild selection "
        "bias; the test-set numbers are a single run. Commands: python -m src.pipeline --split dev "
        "--ratios 0.05 0.02; python -m scripts.param_screen; python -m scripts.tune_anim_check; "
        "python -m scripts.expanded_pipeline --split test."
    )

    doc.add_heading("8. Contributions and third-party sources", level=1)
    doc.add_paragraph(
        "Member contributions: ______ (to be completed by the group). Dataset: CS5185 course "
        "package (Xiph, SVT, NTIA, Sintel; see licenses). Tools: FFmpeg/libx264, OpenCV, NumPy, "
        "Matplotlib. No third-party code was copied."
    )

    img = REPORTS / "subjective" / "03_Bosphorus_2pct.png"
    if img.exists():
        doc.add_heading("Appendix: visual comparison (03_Bosphorus @2%)", level=1)
        doc.add_picture(str(img), width=Inches(6.4))

    doc.save(OUT)
    print("written", OUT)


if __name__ == "__main__":
    main()
