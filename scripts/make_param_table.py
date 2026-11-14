"""Build the per-video decision table: features -> candidates -> winner -> params."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from src import decision

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
LOGS = ROOT / "logs"
DEV = {"01", "02", "03", "04", "07", "08"}


def feature_summary(video_id: str) -> dict:
    path = REPORTS / "features" / f"{video_id}.csv"
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    diff = np.array([float(r["frame_diff"]) for r in rows[1:]])
    edge = np.array([float(r["edge_fraction"]) for r in rows[1:]])
    return {
        "frames": len(rows),
        "diff_mean": float(diff.mean()),
        "diff_p95": float(np.percentile(diff, 95)),
        "edge_mean": float(edge.mean()),
        "edge_p95": float(np.percentile(edge, 95)),
    }


def main():
    results = [r for r in csv.DictReader((LOGS / "results.csv").open(encoding="utf-8-sig"))
               if r.get("mode") == "adaptive"]
    table = []
    for row in results:
        vid = row["video_id"]
        if vid[:2] not in DEV:
            continue
        ratio = float(row["ratio"].rstrip("%")) / 100
        feat = feature_summary(vid)
        plans = decision.adaptive_candidates(feat, ratio)
        table.append({
            "video": vid,
            "ratio": row["ratio"],
            "diff_mean": round(feat["diff_mean"], 2),
            "edge_mean": round(feat["edge_mean"], 3),
            "candidates": " / ".join(p["name"] for p in plans),
            "winner": row["candidate"],
            "preset": row["preset"],
            "x264_params": row["x264_params"],
            "target_mb": round(int(row["target_bytes"]) / 1e6, 2),
            "actual_mb": round(int(row["actual_bytes"]) / 1e6, 2),
            "rel_error": f'{float(row["rel_error"]):+.2%}',
            "psnr": round(float(row["psnr_y_db"]), 3),
            "ms_ssim": round(float(row["ms_ssim"]), 5),
        })

    out = REPORTS / "param_table.csv"
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(table[0].keys()))
        writer.writeheader()
        writer.writerows(table)

    lines = ["| 视频 | 档 | diff_mean | edge_mean | 候选集 | 胜者 | preset | x264 参数 | 目标/实际 MB | 误差 | PSNR | MS-SSIM |",
             "|---|---|---:|---:|---|---|---|---|---|---:|---:|---:|"]
    for r in table:
        lines.append(
            f"| {r['video']} | {r['ratio']} | {r['diff_mean']} | {r['edge_mean']} | "
            f"{r['candidates']} | {r['winner']} | {r['preset']} | `{r['x264_params']}` | "
            f"{r['target_mb']}/{r['actual_mb']} | {r['rel_error']} | {r['psnr']} | {r['ms_ssim']} |"
        )
    (REPORTS / "param_table.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
