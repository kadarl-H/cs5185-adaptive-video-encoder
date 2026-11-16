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

    # 8 NN
    doc.add_heading("8. 神经网络内容分析（MobileNetV2）", level=2)
    doc.add_paragraph(
        "为回答“用深度学习做内容分析会不会更好”，用预训练 MobileNetV2（ONNX，ImageNet 权重）"
        "对每个视频均匀抽取 8 帧，取 1280 维 embedding，计算相邻帧余弦漂移 nn_drift 与帧间离散度 "
        "nn_spread，并用与规则组相同的候选集和 PSNR 搜索跑 12 个开发任务。"
        "阈值按开发集中位数取 nn_drift 0.12、nn_spread 0.012；这是事后校准，不是独立验证。"
    )
    nn_path = LOGS / "nn_results.csv"
    if nn_path.exists():
        with nn_path.open(encoding="utf-8-sig") as fh:
            nn_rows = {(r["video_id"], r["ratio"]): r for r in csv.DictReader(fh)}
        base_map = {(r["video_id"], r["ratio"]): r for r in load("baseline.csv") if r["mode"] == "baseline"}
        rule_map = {(r["video_id"], r["ratio"]): r for r in load("results.csv") if r["mode"] == "adaptive"}
        rows = []
        d_base, d_rule = [], []
        for vid in ("01_FourPeople", "02_Beauty", "03_Bosphorus", "04_HoneyBee", "07_Mobcal", "08_Shields"):
            for ratio in ("5%", "2%"):
                n = float(nn_rows[(vid, ratio)]["psnr_y_db"])
                b = float(base_map[(vid, ratio)]["psnr_y_db"])
                r = float(rule_map[(vid, ratio)]["psnr_y_db"])
                d_base.append(n - b)
                d_rule.append(n - r)
                rows.append([vid, ratio, f"{b:.3f}", f"{r:.3f}", f"{n:.3f}",
                             f"{n-r:+.3f}", nn_rows[(vid, ratio)]["candidate"]])
        table(doc, ["视频", "档", "基线", "规则", "NN", "NN−规则", "NN 胜者"], rows,
              widths=[1.4, 0.45, 0.8, 0.8, 0.8, 0.85, 1.3])
        doc.add_paragraph(
            f"NN 组相对基线 {sum(d_base)/len(d_base):+.4f} dB（{sum(x>0 for x in d_base)}/12 胜），"
            f"相对规则组 {sum(d_rule)/len(d_rule):+.4f} dB（{sum(x>0 for x in d_rule)}/12 胜）。"
            "两者在统计上基本持平：NN 略低于规则，但仍略高于统一基线。"
        )
    doc.add_paragraph(
        "特征层面的检查更能说明问题：nn_drift 与手工帧差的 Spearman 相关只有 0.27，"
        "中位数分组一致率 0.60；nn_spread 与边缘占比的相关为 −0.10。"
        "原因是 MobileNet 的 embedding 描述的是语义/外观，而不是像素运动："
        "02_Beauty 的漂移 0.105 被分到“低运动”，因此丢掉了 aq-motion 候选，"
        "而它恰好是规则组唯一一次内容候选胜出（+0.087 dB）。"
        "结论：在本数据集上，预训练 CNN 特征没有带来质量收益，却引入 14 MB 模型与额外推理依赖；"
        "因此最终系统仍用手工帧差/边缘，NN 结果作为对照实验保留。"
    )

    # 8.1 flow
    doc.add_heading("8.1 光流特征（Farneback）", level=2)
    doc.add_paragraph(
        "为区分“模型方向不对”与“运动估计不够准”，再用非神经的 Farneback 稠密光流替代帧差："
        "每帧半分辨率（640×360）计算平均流幅值 flow_mean，阈值 1.0 像素/帧决定 "
        "aq-motion / long-gop 候选，其余与规则组完全一致。"
    )
    flow_path = LOGS / "flow_results.csv"
    if flow_path.exists():
        with flow_path.open(encoding="utf-8-sig") as fh:
            flow_rows = {(r["video_id"], r["ratio"]): r for r in csv.DictReader(fh)}
        base_map = {(r["video_id"], r["ratio"]): r for r in load("baseline.csv") if r["mode"] == "baseline"}
        rule_map = {(r["video_id"], r["ratio"]): r for r in load("results.csv") if r["mode"] == "adaptive"}
        rows = []
        d_base, d_rule = [], []
        for vid in ("01_FourPeople", "02_Beauty", "03_Bosphorus", "04_HoneyBee", "07_Mobcal", "08_Shields"):
            for ratio in ("5%", "2%"):
                f = float(flow_rows[(vid, ratio)]["psnr_y_db"])
                b = float(base_map[(vid, ratio)]["psnr_y_db"])
                r = float(rule_map[(vid, ratio)]["psnr_y_db"])
                d_base.append(f - b)
                d_rule.append(f - r)
                rows.append([vid, ratio, f"{b:.3f}", f"{r:.3f}", f"{f:.3f}",
                             f"{f-r:+.3f}", flow_rows[(vid, ratio)]["candidate"]])
        table(doc, ["视频", "档", "基线", "规则", "光流", "光流−规则", "光流胜者"], rows,
              widths=[1.4, 0.45, 0.8, 0.8, 0.8, 0.95, 1.3])
        doc.add_paragraph(
            f"光流组相对基线 {sum(d_base)/len(d_base):+.4f} dB（{sum(x>0 for x in d_base)}/12 胜），"
            f"相对规则组 {sum(d_rule)/len(d_rule):+.4f} dB（{sum(x>0 for x in d_rule)}/12 胜）。"
            "差异在噪声量级，说明更换运动估计器并没有改变决策；"
            "光流与帧差的秩相关为 0.77，分类结果几乎相同（01/04 低运动，其余高运动）。"
            "结合 CNN 实验可以确认：瓶颈不在特征提取，而在候选设计与“特征→参数”的映射。"
        )

    # 8.2 expanded pool
    doc.add_heading("8.2 扩展候选池（5 个候选）", level=2)
    doc.add_paragraph(
        "针对“3 个固定套餐锁死上限”的问题，把候选扩到 5 个，并让其中两个由特征动态生成："
        "公式方案 g=max(60,min(250,250−6×diff))、低细节用 aq-mode=2/aq-strength=0.8、"
        "高细节用 aq-mode=1/aq-strength=1.0；另外加入 aq-contrast（AQ2/0.8）与 "
        "psy-detail（psy-rd=1.0:0.0）或 deblock-soft（deblock=1:1），仍由 PSNR 在预算内选优。"
    )
    exp_rows = []
    for fname in ("expanded5_results.csv", "expanded5_test_results.csv"):
        path = LOGS / fname
        if path.exists():
            with path.open(encoding="utf-8-sig") as fh:
                exp_rows.extend(list(csv.DictReader(fh)))
    if exp_rows:
        base_all = {(r["video_id"], r["ratio"]): r for r in load("baseline.csv") if r["mode"] == "baseline"}
        rule_all = {(r["video_id"], r["ratio"]): r for r in load("results.csv") if r["mode"] == "adaptive"}
        rows = []
        dev_b, dev_r, test_b, test_r = [], [], [], []
        for r in exp_rows:
            key = (r["video_id"], r["ratio"])
            b = float(base_all[key]["psnr_y_db"])
            ru = float(rule_all[key]["psnr_y_db"])
            e = float(r["psnr_y_db"])
            target = dev_b if r["video_id"] in ("01_FourPeople", "02_Beauty", "03_Bosphorus",
                                                "04_HoneyBee", "07_Mobcal", "08_Shields") else test_b
            target_r = dev_r if target is dev_b else test_r
            target.append(e - b)
            target_r.append(e - ru)
            rows.append([r["video_id"], r["ratio"], f"{b:.3f}", f"{ru:.3f}", f"{e:.3f}",
                         f"{e-ru:+.3f}", r["candidate"]])
        table(doc, ["视频", "档", "基线", "规则", "5 候选", "5候选−规则", "胜者"], rows,
              widths=[1.35, 0.42, 0.72, 0.72, 0.8, 0.95, 1.35])
        parts = []
        if dev_b:
            parts.append(
                f"开发集：相对基线 {sum(dev_b)/len(dev_b):+.4f} dB，"
                f"相对规则 {sum(dev_r)/len(dev_r):+.4f} dB。")
        if test_b:
            parts.append(
                f"测试集：相对基线 {sum(test_b)/len(test_b):+.4f} dB，"
                f"相对规则 {sum(test_r)/len(test_r):+.4f} dB。")
        combined = dev_r + test_r
        if combined:
            parts.append(f"共 {len(combined)} 个任务，相对规则 {sum(combined)/len(combined):+.4f} dB。")
        from collections import Counter
        dist = "、".join(f"{name} {count} 次" for name, count in Counter(r[6] for r in rows).most_common())
        parts.append(
            f"胜者分布：{dist}。所有任务体积都在 ±3% 内。"
            "需要注意：5 个候选取 PSNR 最大值会带来轻微的选择偏差，测试集只跑了一次，"
            "因此 +0.05~+0.07 dB 应视为“小幅但方向一致”，而不是稳定的大幅提升。"
        )
        doc.add_paragraph("".join(parts))

    # 8.3 screening + tune
    doc.add_heading("8.3 其他参数筛选与 tune 组合", level=2)
    screen_path = LOGS / "param_screen.csv"
    if screen_path.exists():
        with screen_path.open(encoding="utf-8-sig") as fh:
            screen = list(csv.DictReader(fh))
        base = {(r["video"], r["ratio"]): float(r["psnr"]) for r in screen if r["variant"] == "base"}
        variants = sorted({r["variant"] for r in screen if r["variant"] != "base"})
        rows = []
        for v in variants:
            ds = [float(r["psnr"]) - base[(r["video"], r["ratio"])]
                  for r in screen if r["variant"] == v]
            rows.append([v, f"{sum(ds)/len(ds):+.3f}", f"{min(ds):+.3f}", f"{max(ds):+.3f}"])
        table(doc, ["变体", "平均 ΔPSNR", "最小", "最大"], rows,
              widths=[1.6, 1.1, 0.9, 0.9])
        doc.add_paragraph(
            "单参数筛选（01/07 × 两档，共 4 个任务）：subq=9、me=umh、rc-lookahead=40、"
            "refs=5、bf=4、mbtree=0、tune=film、tune=animation。"
            "结果是大多数参数在 ±0.05 dB 内，mbtree 关闭损失 0.6 dB，subq=9 反而 −0.09 dB；"
            "唯一大幅正向的是 tune=animation（约 +0.35 dB）。"
        )
    tune_rows = []
    for fname in ("tune_anim_dev.csv", "tune_anim_test.csv"):
        path = LOGS / fname
        if path.exists():
            with path.open(encoding="utf-8-sig") as fh:
                tune_rows.extend(list(csv.DictReader(fh)))
    if tune_rows:
        base_all = {(r["video_id"], r["ratio"]): float(r["psnr_y_db"])
                    for r in load("baseline.csv") if r["mode"] == "baseline"}
        rows = []
        for r in tune_rows:
            key = (r["video"], r["ratio"])
            rows.append([r["video"], r["ratio"], f"{base_all[key]:.3f}",
                         f"{float(r['psnr']):.3f}", f"{float(r['psnr'])-base_all[key]:+.3f}",
                         r["rel_error"]])
        table(doc, ["视频", "档", "基线", "tune animation", "ΔPSNR", "体积误差"], rows,
              widths=[1.35, 0.45, 0.75, 1.1, 0.75, 0.8])
        ds = [float(r["psnr"]) - base_all[(r["video"], r["ratio"])] for r in tune_rows]
        doc.add_paragraph(
            f"单独使用 `-preset medium -tune animation`（不换 AQ、不换 GOP）在 20 个任务上"
            f"平均 {sum(ds)/len(ds):+.3f} dB，20/20 全部高于基线；相对规则组约 +0.33 dB。"
            "原因是 tune 不是单个参数，而是一组联动设置（参考帧、B 帧、AQ、deblock、psy-rd），"
            "其组合效应远大于逐个调参。代价：09_Parkrun 的 MS-SSIM 略降（PSNR 与结构相似性分歧），"
            "10_Stockholm @2% 体积误差 3.11%，略超 3% 带。"
            "因此它应作为候选之一交给 PSNR 裁决，而不是无条件替换所有方案。"
        )

    # 8.4 six candidates
    doc.add_heading("8.4 六候选（加入 tune animation）", level=2)
    six_rows = []
    for fname in ("expanded_results.csv", "expanded_test_results.csv"):
        path = LOGS / fname
        if path.exists():
            with path.open(encoding="utf-8-sig") as fh:
                six_rows.extend(list(csv.DictReader(fh)))
    if six_rows:
        base_all = {(r["video_id"], r["ratio"]): float(r["psnr_y_db"])
                    for r in load("baseline.csv") if r["mode"] == "baseline"}
        rule_all = {(r["video_id"], r["ratio"]): float(r["psnr_y_db"])
                    for r in load("results.csv") if r["mode"] == "adaptive"}
        dev = [(float(r["psnr_y_db"]) - base_all[(r["video_id"], r["ratio"])],
                float(r["psnr_y_db"]) - rule_all[(r["video_id"], r["ratio"])])
               for r in six_rows if r["video_id"][:2] in ("01", "02", "03", "04", "07", "08")]
        test = [(float(r["psnr_y_db"]) - base_all[(r["video_id"], r["ratio"])],
                 float(r["psnr_y_db"]) - rule_all[(r["video_id"], r["ratio"])])
                for r in six_rows if r["video_id"][:2] in ("05", "06", "09", "10")]
        table(doc, ["数据", "任务数", "相对基线", "相对规则"], [
            ["开发集", len(dev), f"{sum(x[0] for x in dev)/len(dev):+.4f}", f"{sum(x[1] for x in dev)/len(dev):+.4f}"],
            ["测试集", len(test), f"{sum(x[0] for x in test)/len(test):+.4f}", f"{sum(x[1] for x in test)/len(test):+.4f}"],
            ["合计", len(dev) + len(test),
             f"{sum(x[0] for x in dev+test)/(len(dev)+len(test)):+.4f}",
             f"{sum(x[1] for x in dev+test)/(len(dev)+len(test)):+.4f}"],
        ], widths=[1.0, 0.9, 1.3, 1.3])
        from collections import Counter
        dist = "、".join(f"{k} {v} 次" for k, v in Counter(r["candidate"] for r in six_rows).most_common())
        doc.add_paragraph(
            f"胜者分布：{dist}。加入 tune 后，绝大多数任务直接选中 tune-animation，"
            "六候选相对五候选的提升与 tune 单独使用几乎相同；"
            "这说明在本数据集上，收益主要来自 tune 这一组联动参数，而不是“更多候选”本身。"
            "所有输出体积都在 ±3% 内。"
        )

    # 8.5 tune overrides
    doc.add_heading("8.5 在 tune 之上做内容覆盖", level=2)
    override = []
    for fname in ("tune_override_dev.csv", "tune_override_test.csv"):
        path = LOGS / fname
        if path.exists():
            with path.open(encoding="utf-8-sig") as fh:
                override.extend(list(csv.DictReader(fh)))
    tune_ref = {}
    for fname in ("tune_anim_dev.csv", "tune_anim_test.csv"):
        path = LOGS / fname
        if path.exists():
            with path.open(encoding="utf-8-sig") as fh:
                for r in csv.DictReader(fh):
                    tune_ref[(r["video"], r["ratio"])] = float(r["psnr"])
    if override and tune_ref:
        ds = [float(r["psnr"]) - tune_ref[(r["video"], r["ratio"])] for r in override]
        from collections import Counter
        counts = Counter(r["variant"] for r in override)
        rows = [[v, counts[v], f"{sum(float(r['psnr']) - tune_ref[(r['video'], r['ratio'])] for r in override if r['variant'] == v)/counts[v]:+.4f}"]
                for v in ("A_tune", "B_tune_g", "C_tune_aq", "D_tune_g_aq") if counts[v]]
        table(doc, ["变体", "被选中次数", "相对纯 tune 平均 ΔPSNR"], rows,
              widths=[1.5, 1.2, 2.0])
        doc.add_paragraph(
            "A=纯 tune；B=tune + 由帧差算出的 GOP；C=tune + 高细节改 AQ1；D=两者都改。"
            f"20 个任务中，内容覆盖改变了 {sum(1 for r in override if r['variant'] != 'A_tune')} 次选择"
            f"（A 被选 {counts['A_tune']} 次），但相对纯 tune 平均 {sum(ds)/len(ds):+.4f} dB。"
            "也就是说：特征确实改变了参数，却没有带来可测的画质提升；"
            "09_Parkrun @2% 的 D 变体甚至因为“体积合格优先”被选中，PSNR 比纯 tune 低 0.31 dB。"
            "这条实验提供了“内容分析影响参数选择”的直接证据，同时也说明在该数据集上，"
            "覆盖 tune 的默认值并不划算。"
        )

    # 9 reproduce
    doc.add_heading("9. 复现命令", level=2)
    for cmd in [
        r"python -m src.pipeline --split dev --ratios 0.05 0.02",
        r"python -m src.pipeline --split test --ratios 0.05 0.02 --baseline",
        r"python -m src.pipeline --split dev --ratios 0.05 0.02 --baseline --baseline-gop 60",
        r"python -m scripts.make_param_table",
        r"python -m scripts.ablation_ds",
        r"python -m scripts.make_subjective_kit",
        r"python -m scripts.nn_features   # MobileNetV2 特征",
        r"python -m scripts.nn_pipeline   # NN 特征驱动的自适应",
        r"python -m scripts.flow_features # Farneback 光流特征",
        r"python -m scripts.flow_pipeline # 光流特征驱动的自适应",
        r"python -m scripts.expanded_pipeline            # 5 候选（开发集）",
        r"python -m scripts.expanded_pipeline --split test  # 5 候选（测试集）",
        r"python -m scripts.tune_override --split dev   # tune + 内容覆盖",
        r"python -m scripts.tune_override --split test",
    ]:
        p = doc.add_paragraph(cmd)
        p.runs[0].font.name = "Consolas"

    # 10 contributions
    doc.add_heading("10. 成员贡献（待填写）", level=2)
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
