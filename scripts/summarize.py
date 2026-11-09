"""Summarize logs/baseline.csv into a markdown table and a PSNR chart.

    python -m scripts.summarize
"""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "logs"
REPORT = ROOT / "reports"


def load(name: str) -> list[dict]:
    path = LOG / name
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def fmt_mb(b) -> str:
    return f"{int(b) / 1e6:.2f}"


def main() -> None:
    rows = load("baseline.csv")
    if not rows:
        print("没有 baseline.csv")
        return

    lines = ["# 统一基线结果（baseline）", ""]
    lines.append("| 视频 | 档位 | 目标 | 实际 | 误差 | PSNR-Y | MS-SSIM | 尝试 | 编码(s) |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        lines.append(
            f"| {r['video_id']} | {r['ratio']} | {fmt_mb(r['target_bytes'])} MB | "
            f"{fmt_mb(r['actual_bytes'])} MB | {float(r['rel_error']) * 100:.2f}% | "
            f"{r['psnr_y_db']} | {r['ms_ssim']} | {r['attempts']} | {r['encode_time_s']} |"
        )

    errors = [abs(float(r["rel_error"])) for r in rows]
    psnr5 = [float(r["psnr_y_db"]) for r in rows if r["ratio"] == "5%"]
    psnr2 = [float(r["psnr_y_db"]) for r in rows if r["ratio"] == "2%"]
    lines += [
        "",
        "## 汇总",
        "",
        f"- 用例数：{len(rows)}（6 视频 × 2 档）",
        f"- 平均绝对误差：{sum(errors) / len(errors) * 100:.2f}%",
        f"- 最大绝对误差：{max(errors) * 100:.2f}%",
        f"- 5% 档平均 PSNR-Y：{sum(psnr5) / len(psnr5):.2f} dB",
        f"- 2% 档平均 PSNR-Y：{sum(psnr2) / len(psnr2):.2f} dB",
        f"- 解码校验通过：{sum(1 for r in rows if r['decode_ok'] == 'True')}/{len(rows)}",
        "",
    ]
    (REPORT / "baseline_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("未安装 matplotlib，跳过图。")
        return

    videos = sorted({r["video_id"] for r in rows})
    x = np.arange(len(videos))
    w = 0.38
    fig, ax = plt.subplots(figsize=(11, 4.5))
    for i, ratio in enumerate(("5%", "2%")):
        vals = []
        for v in videos:
            match = [float(r["psnr_y_db"]) for r in rows if r["video_id"] == v and r["ratio"] == ratio]
            vals.append(match[0] if match else 0)
        ax.bar(x + (i - 0.5) * w, vals, w, label=ratio)
    ax.set_xticks(x)
    ax.set_xticklabels(videos, rotation=20, ha="right")
    ax.set_ylabel("PSNR-Y (dB)")
    ax.set_title("Unified baseline: PSNR-Y per video and target ratio")
    ax.legend()
    fig.tight_layout()
    fig.savefig(REPORT / "baseline_psnr.png", dpi=150)
    plt.close(fig)
    print(f"图已保存：{REPORT / 'baseline_psnr.png'}")


if __name__ == "__main__":
    main()
