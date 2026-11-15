"""Expanded candidate pool: formula-generated plan + 4 references.

    python -m scripts.expanded_pipeline

Five plans per clip, chosen by content features, then PSNR within budget.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np

from src import config, decision, encode, evaluate, probe

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"
DATASET = ROOT / "data" / "CS5185_Project_Video_Dataset"
OUT = ROOT / "out" / "expanded"
DEV = ["01_FourPeople", "02_Beauty", "03_Bosphorus", "04_HoneyBee", "07_Mobcal", "08_Shields"]
TEST = ["05_Jockey", "06_ShakeNDry", "09_Parkrun", "10_Stockholm"]
RATIOS = [0.05, 0.02]
FEATURES = ROOT / "reports" / "features"


def load_features(names):
    out = {}
    for name in names:
        with (FEATURES / f"{name}.csv").open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        diff = np.array([float(r["frame_diff"]) for r in rows[1:]])
        edge = np.array([float(r["edge_fraction"]) for r in rows[1:]])
        out[name] = (float(diff.mean()), float(edge.mean()))
    return out


def plans(feat: tuple[float, float]) -> list[dict]:
    diff, edge = feat
    g = max(60, min(250, round(250 - 6 * diff)))
    low_detail = edge < 0.12
    aq_mode = 2 if low_detail else 1
    aq_str = 0.8 if low_detail else 1.0

    base = [
        {"name": "medium-default", "preset": "medium", "x264_params": {}, "keyint": None,
         "reason": ["对照：medium 默认"]},
        {"name": "veryslow-default", "preset": "veryslow", "x264_params": {}, "keyint": None,
         "reason": ["对照：veryslow"]},
    ]
    formula = {
        "name": "formula", "preset": "medium", "keyint": g,
        "x264_params": {"aq-mode": aq_mode, "aq-strength": aq_str},
        "reason": [f"公式：g=250-6*{diff:.1f}={g}, aq={aq_mode}/{aq_str}"],
    }
    aq2 = {
        "name": "aq-contrast", "preset": "medium", "keyint": None,
        "x264_params": {"aq-mode": 2, "aq-strength": 0.8},
        "reason": ["AQ2 + 0.8：测试区域码率重分配"],
    }
    if low_detail:
        psy = {"name": "deblock-soft", "preset": "medium", "keyint": None,
               "x264_params": {}, "extra_args": ["-deblock", "1:1"],
               "reason": ["低细节：deblock 1:1 抑制块效应"]}
    else:
        psy = {"name": "psy-detail", "preset": "medium", "keyint": None,
               "x264_params": {}, "extra_args": ["-psy-rd", "1.0:0.0"],
               "reason": ["高细节：psy-rd 1.0:0.0 保纹理"]}
    return base + [formula, aq2, psy]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    args = parser.parse_args()
    names = DEV if args.split == "dev" else TEST
    feats = load_features(names)
    rows = []
    for name in names:
        video = DATASET / f"{name}.mp4"
        info = probe.describe(video)
        for ratio in RATIOS:
            tag = f"{int(round(ratio * 100))}%"
            target = int(info[f"target_bytes_{tag}"])
            best, best_psnr, best_plan, best_in = None, float("-inf"), None, False
            for plan in plans(feats[name]):
                enc_args = decision.ffmpeg_args(plan) + plan.get("extra_args", [])
                cand, _ = encode.encode_to_budget(
                    video=video, ratio=ratio, target_bytes=target,
                    duration_s=float(info["duration_s"]),
                    out_dir=OUT / name / f"{int(ratio*100)}pct" / plan["name"],
                    extra_args=enc_args, max_attempts=2,
                )
                if not cand:
                    continue
                metrics = evaluate.compare(video, Path(cand["output"]))
                psnr = float(metrics.get("psnr_y_db", float("-inf")))
                in_budget = abs(float(cand["rel_error"])) <= config.SIZE_TOLERANCE
                better = (in_budget and not best_in) or (in_budget == best_in and psnr > best_psnr)
                if best is None or better:
                    best, best_psnr, best_plan, best_in = cand, psnr, plan, in_budget
            row = {
                "mode": "adaptive-expanded", "video_id": name, "ratio": tag,
                "target_bytes": target, "actual_bytes": best["actual_bytes"] if best else 0,
                "rel_error": best["rel_error"] if best else "",
                "psnr_y_db": best_psnr, "candidate": best_plan["name"] if best_plan else "",
                "in_budget": best_in, "output": best["output"] if best else "",
            }
            rows.append(row)
            print(row)

    out_name = "expanded_results.csv" if args.split == "dev" else "expanded_test_results.csv"
    with (LOGS / out_name).open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print("written", LOGS / out_name)


if __name__ == "__main__":
    main()
