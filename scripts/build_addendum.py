"""Build the supplementary experiments report (docx)."""
from __future__ import annotations

import csv
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"
REPORTS = ROOT / "reports"
OUT = ROOT / "report" / "CS5185_Experiments_Addendum.docx"


def load(name):
    with (LOGS / name).open(encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def cn_font(doc):
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10.5)
    style.element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")


def table(doc, header, rows, widths=None):
    t = doc.add_table(rows=1, cols=len(header))
    t.style = "Table Grid"
    t.autofit = False
    for i, text in enumerate(header):
        cell = t.rows[0].cells[i]
        cell.text = str(text)
        for p in cell.paragraphs:
            for r in p.runs:
                r.bold = True
    for row in rows:
        cells = t.add_row().cells
        for i, text in enumerate(row):
            cells[i].text = str(text)
    for row in t.rows:
        for cell in row.cells:
            for p in cell.paragraphs:
                for r in p.runs:
                    r.font.size = Pt(8)
    if widths:
        for row in t.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = Inches(w)
    # keep rows intact and repeat the header when a table spans pages
    for row in t.rows:
        trPr = row._tr.get_or_add_trPr()
        cant = trPr.makeelement(qn("w:cantSplit"), {})
        trPr.append(cant)
    hdr = t.rows[0]._tr.get_or_add_trPr()
    hdr.append(hdr.makeelement(qn("w:tblHeader"), {}))
    doc.add_paragraph()
    return t


def main():
    doc = Document()
    cn_font(doc)
    doc.add_heading("CS5185 补充实验", level=1)
    doc.add_paragraph(
        "本附录汇总主报告之外的实验：测试集基线、基线 GOP 敏感性、逐视频决策表、"
        "2×2 参数消融、主观比较材料、LLM 决策对照，以及边缘特征的定位。"
    )

    # 1 test baseline
    base = {(r["video_id"], r["ratio"]): r for r in load("baseline.csv") if r["mode"] == "baseline"}
    ada = {(r["video_id"], r["ratio"]): r for r in load("results.csv") if r["mode"] == "adaptive"}
    test_ids = ["05_Jockey", "06_ShakeNDry", "09_Parkrun", "10_Stockholm"]
    doc.add_heading("1. 测试集：统一基线与自适应", level=2)
    rows = []
    deltas = []
    for vid in test_ids:
        for ratio in ("5%", "2%"):
            b, a = base[(vid, ratio)], ada[(vid, ratio)]
            d = float(a["psnr_y_db"]) - float(b["psnr_y_db"])
            deltas.append(d)
            rows.append([vid, ratio, f'{float(b["psnr_y_db"]):.3f}', f'{float(a["psnr_y_db"]):.3f}',
                         f'{d:+.3f}', a["candidate"]])
    table(doc, ["视频", "档", "基线 PSNR", "自适应 PSNR", "ΔPSNR", "胜出候选"], rows)
    doc.add_paragraph(
        f"8 个测试任务中自适应胜 7 个，平均 ΔPSNR = {sum(deltas)/len(deltas):+.3f} dB；"
        "唯一退步是 10_Stockholm @5%（−0.159 dB），两者都选中 medium，差异来自码率落点。"
        "测试集此前只跑自适应，本表补齐了同预算基线，使比较完整。"
    )

    # 2 baseline sensitivity
    doc.add_heading("2. 基线 GOP 敏感性", level=2)
    doc.add_paragraph(
        "统一基线固定 medium、AQ1，但 GOP 有两种选择：x264 默认（250，整段一个 I 帧）"
        "与附录示例值 60（5 秒约 3 个 I 帧）。用同一流水线重跑 12 个开发任务后："
    )
    table(doc, ["基线定义", "平均 PSNR（12 任务）", "自适应相对它"], [
        ["medium / 默认 GOP 250 / AQ1", "38.94 dB", "+0.026 dB，8/12"],
        ["medium / GOP 60 / AQ1", "38.81 dB", "+0.161 dB，12/12"],
    ])
    doc.add_paragraph(
        "GOP60 基线在 12 个任务上全部低于默认 GOP 基线，平均低 0.135 dB。"
        "原因是 5 秒 150 帧的片段里，GOP60 多出约 2 个 I 帧，低码率下这些比特要从残差中扣除。"
        "因此“自适应相对 GOP60 基线提升更大”主要来自基线变弱，而不是自适应变强。"
        "报告主表采用默认 GOP 基线，附录同时给出 GOP60 结果以避免基线选择性偏差。"
    )

    # 3 per-video decision table
    doc.add_heading("3. 逐视频决策表", level=2)
    param_path = REPORTS / "param_table.csv"
    param_rows = []
    if param_path.exists():
        with param_path.open(encoding="utf-8-sig") as fh:
            param_rows = list(csv.DictReader(fh))
    rows = []
    for r in param_rows:
        params = r["x264_params"]
        if params in ("{}", ""):
            params = "默认" if r["preset"] == "medium" else r["preset"]
        else:
            params = params.strip("{}").replace('"', "")
            params = params.replace("aq-strength:1.0,", "").replace("aq-mode:", "aq=")
            params = params.replace("refs:", "refs=").replace("bf:", "bf=")
            params = params.replace(",", ", ")
            params = params if r["preset"] == "medium" else f'{r["preset"]}, {params}'
        rows.append([r["video"], r["ratio"], r["winner"], params,
                     f'{r["target_mb"]}/{r["actual_mb"]}', r["rel_error"], r["psnr"]])
    if rows:
        table(doc, ["视频", "档", "胜者（3 候选）", "参数", "目标/实际 MB", "误差", "PSNR"],
              rows, widths=[1.5, 0.4, 1.0, 1.55, 0.8, 0.55, 0.45])
    doc.add_paragraph(
        "12 个开发任务中，内容相关候选只在 02_Beauty @5% 胜出（aq-motion）；"
        "long-gop 从未胜出；其余胜者是 medium-default 或 veryslow-default。"
        "这张表是“内容分析确实进入了候选构造、但最终由实测 PSNR 裁决”的直接证据，"
        "也是本系统增益有限的原因。"
    )

    # 4 ablation
    doc.add_heading("4. 2×2 参数消融（默认 GOP）", level=2)
    abl = load("ablation.csv")
    lookup = {(r["video"], r["ratio"], r["config"]): r for r in abl}
    rows = []
    for vid in ("01_FourPeople", "03_Bosphorus", "07_Mobcal"):
        for ratio in ("5%", "2%"):
            a = float(lookup[(vid, ratio, "A_medium_aq1")]["psnr"])
            b = float(lookup[(vid, ratio, "B_slow_aq1")]["psnr"])
            c = float(lookup[(vid, ratio, "C_medium_aq2")]["psnr"])
            d = float(lookup[(vid, ratio, "D_slow_aq2")]["psnr"])
            rows.append([vid, ratio, f"{a:.3f}", f"{b:.3f}", f"{c:.3f}", f"{d:.3f}",
                         f"{b-a:+.3f}", f"{c-a:+.3f}", f"{d-a:+.3f}"])
    table(doc, ["视频", "档", "A m/AQ1", "B s/AQ1", "C m/AQ2", "D s/AQ2",
                "slow", "AQ2", "D−A"], rows,
          widths=[1.25, 0.45, 0.75, 0.75, 0.75, 0.75, 0.6, 0.6, 0.6])
    doc.add_paragraph(
        "slow 的影响在 ±0.05 dB 以内，个别片段（01 @2%）甚至 −0.155 dB；"
        "AQ2 的影响更大且依赖内容：01 上 +0.02~+0.03 dB，03 上约 −0.01 dB，"
        "07_Mobcal（高细节、edge 0.54）上 −0.18~−0.19 dB。"
        "这与 02_Beauty（edge 0.097）上 aq-motion 胜出的结果方向一致："
        "AQ2 有利于低细节内容，不利于高纹理内容。"
    )

    # 5 subjective
    doc.add_heading("5. 案例分析：03_Bosphorus @2%", level=2)
    doc.add_paragraph(
        "内容特征：帧差均值 6.12、边缘占比 0.246，属于中等运动 + 较高结构细节。"
        "候选集为 medium-default / veryslow-default / aq-motion；两档最终都选中 veryslow-default，"
        "5% 档 PSNR 40.170 dB、2% 档 36.991 dB，预算下降导致 −3.18 dB。"
        "画面观察：2% 档船体黑色边缘开始出现轻微方块，船尾白浪与水面细纹最先糊成一片，"
        "远处岸线的树木层次明显减少；5% 档这些区域仍可分辨。"
        "这说明结构细节在低码率下最先丢失，也解释了为什么 03 在 2% 档需要更慢的 preset。"
    )
    doc.add_heading("5.1 主观比较材料", level=2)
    doc.add_paragraph(
        "按作业 3.5 要求，对 3 个视频 × 两档预算做原片、基线、自适应的并排比较。"
        "下图是 03_Bosphorus @2% 在 t=2.5 s 的三联图（左：原片，中：基线，右：自适应）。"
        "完整材料见 reports/subjective/index.html，含 01/03/07 × 5%/2% 共 6 张图和打分表。"
    )
    img = REPORTS / "subjective" / "03_Bosphorus_2pct.png"
    if img.exists():
        doc.add_picture(str(img), width=Inches(6.4))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph(
        "评分维度：清晰度、块效应、运动流畅性，各 1–5 分。"
        "观察重点：2% 档下船尾白浪与水面细纹是否糊成一片、船体边缘是否出现方块、"
        "远处岸线是否丢失层次。主观分数需由组员实际观看后填写，本文档不代填。"
    )

    # 6 LLM
    doc.add_heading("6. LLM 决策对照（可选接口）", level=2)
    table(doc, ["组", "平均 PSNR", "相对规则", "体积 ±3%", "调用次数"], [
        ["规则 + 候选搜索", "39.09 dB", "—", "12/12", "0"],
        ["LLM 一次性", "38.82 dB", "−0.268 dB", "11/12", "12"],
        ["LLM 带历史回灌", "38.86 dB", "−0.226 dB", "12/12", "21"],
    ])
    doc.add_paragraph(
        "按附录 D 实现了特征/预算/候选/历史输入、JSON 校验、重试与规则回退。"
        "DeepSeek 一次性组 0/12 胜出，加入体积历史后体积合格率提升到 12/12，"
        "但仍低于实测候选搜索。结论：LLM 适合做参数建议与解释，不适合替代 PSNR 裁决。"
    )

    # 7 edge feature
    doc.add_heading("7. 边缘特征的定位", level=2)
    doc.add_paragraph(
        "edge_mean 在 3.2 中计算并画入时间线，但当前候选构造只使用 diff_mean 决定 "
        "aq-motion / long-gop。消融显示 AQ2 的收益与细节密度相关（02 低细节获益、07 高细节受损），"
        "因此下一步应把 edge_mean 接入 AQ 选择，而不是只作为解释性指标。"
        "本报告如实标注：当前版本中边缘特征不参与最终参数决策。"
    )

    # 8 reproduce
    doc.add_heading("8. 复现命令", level=2)
    for cmd in [
        r"python -m src.pipeline --split dev --ratios 0.05 0.02",
        r"python -m src.pipeline --split test --ratios 0.05 0.02 --baseline",
        r"python -m src.pipeline --split dev --ratios 0.05 0.02 --baseline --baseline-gop 60",
        r"python -m scripts.make_param_table",
        r"python -m scripts.ablation_ds",
        r"python -m scripts.make_subjective_kit",
    ]:
        p = doc.add_paragraph(cmd)
        p.runs[0].font.name = "Consolas"

    # 9 contributions
    doc.add_heading("9. 成员贡献（待填写）", level=2)
    table(doc, ["成员", "负责内容", "占比"], [
        ["（姓名/学号）", "内容特征、参数决策、编码流水线", ""],
        ["（姓名/学号）", "评测脚本、PSNR/MS-SSIM、图表", ""],
        ["（姓名/学号）", "报告撰写、实验设计", ""],
        ["（姓名/学号）", "PPT、演示与复现", ""],
    ])
    doc.add_paragraph("请按实际分工填写姓名、学号与百分比，并删除本行提示。")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT)
    print("written", OUT)


if __name__ == "__main__":
    main()
