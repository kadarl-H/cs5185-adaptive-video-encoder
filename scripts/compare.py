"""Compare adaptive results against the unified baseline.

    python -m scripts.compare
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


def main() -> None:
    base = {(r["video_id"], r["ratio"]): r for r in load("baseline.csv")}
    adaptive = {(r["video_id"], r["ratio"]): r for r in load("results.csv") if r.get("mode") == "adaptive"}
    keys = sorted(set(base) & set(adaptive))
    if not keys:
        print("baseline.csv / results.csv 没有可对比的行")
        return

    rows = []
    for key in keys:
        b, a = base[key], adaptive[key]
        rows.append({
            "video_id": key[0],
            "ratio": key[1],
            "base_kbps": float(b["actual_kbps"]),
            "adap_kbps": float(a["actual_kbps"]),
            "base_psnr": float(b["psnr_y_db"]),
            "adap_psnr": float(a["psnr_y_db"]),
            "delta": float(a["psnr_y_db"]) - float(b["psnr_y_db"]),
            "base_err": abs(float(b["rel_error"])) * 100,
            "adap_err": abs(float(a["rel_error"])) * 100,
            "candidate": a.get("candidate", ""),
            "base_time": float(b["encode_time_s"]),
            "adap_time": float(a["encode_time_s"]),
        })

    lines = ["# 自适应 vs 统一基线", ""]
    lines.append("| 视频 | 档位 | 基线 PSNR | 自适应 PSNR | ΔPSNR | 基线误差 | 自适应误差 | 选中候选 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in rows:
        lines.append(
            f"| {r['video_id']} | {r['ratio']} | {r['base_psnr']:.3f} | {r['adap_psnr']:.3f} | "
            f"{r['delta']:+.3f} | {r['base_err']:.2f}% | {r['adap_err']:.2f}% | {r['candidate']} |"
        )

    deltas = [r["delta"] for r in rows]
    wins = sum(1 for d in deltas if d > 0)
    lines += [
        "",
        "## 汇总",
        "",
        f"- 用例数：{len(rows)}",
        f"- ΔPSNR 均值：{sum(deltas) / len(deltas):+.3f} dB",
        f"- ΔPSNR 中位数：{sorted(deltas)[len(deltas) // 2]:+.3f} dB",
        f"- 自适应更好：{wins}/{len(rows)}",
        f"- 平均编码耗时：基线 {sum(r['base_time'] for r in rows) / len(rows):.1f}s，"
        f"自适应 {sum(r['adap_time'] for r in rows) / len(rows):.1f}s",
        "",
    ]
    (REPORT / "adaptive_vs_baseline.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        return

    videos = sorted({r["video_id"] for r in rows})
    x = np.arange(len(videos))
    w = 0.2
    fig, ax = plt.subplots(figsize=(12, 4.5))
    for i, (ratio, color) in enumerate((("5%", "#1f77b4"), ("2%", "#ff7f0e"))):
        bvals = [next((r["base_psnr"] for r in rows if r["video_id"] == v and r["ratio"] == ratio), 0) for v in videos]
        avals = [next((r["adap_psnr"] for r in rows if r["video_id"] == v and r["ratio"] == ratio), 0) for v in videos]
        ax.bar(x + (i * 2 - 1.5) * w, bvals, w, color=color, alpha=0.55, label=f"baseline {ratio}")
        ax.bar(x + (i * 2 - 0.5) * w, avals, w, color=color, label=f"adaptive {ratio}")
    ax.set_xticks(x)
    ax.set_xticklabels(videos, rotation=20, ha="right")
    ax.set_ylabel("PSNR-Y (dB)")
    ax.set_title("Adaptive vs unified baseline (both constrained to the same size budget)")
    ax.legend(ncol=2, fontsize=8)
    fig.tight_layout()
    fig.savefig(REPORT / "adaptive_vs_baseline.png", dpi=150)
    print(f"图：{REPORT / 'adaptive_vs_baseline.png'}")


if __name__ == "__main__":
    main()
