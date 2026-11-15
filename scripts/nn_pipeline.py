"""Run the adaptive pipeline with MobileNetV2 features instead of frame difference.

Same candidate parameter sets and same selection rule as the rule-based controller;
only the content signal changes (handcrafted diff/edge -> CNN embedding drift/spread).

    python -m scripts.nn_pipeline
"""
from __future__ import annotations

import csv
from pathlib import Path

from src import config, decision, encode, evaluate, probe

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"
REPORTS = ROOT / "reports"
DATASET = ROOT / "data" / "CS5185_Project_Video_Dataset"
OUT = ROOT / "out" / "nn"
DEV = ["01_FourPeople", "02_Beauty", "03_Bosphorus", "04_HoneyBee", "07_Mobcal", "08_Shields"]
RATIOS = [0.05, 0.02]

# thresholds calibrated on the six development clips (median split, rounded)
MOTION_HIGH = 0.12    # nn_drift
DETAIL_HIGH = 0.012   # nn_spread


def load_nn():
    with (REPORTS / "features_nn.csv").open(encoding="utf-8-sig") as fh:
        return {r["video"]: r for r in csv.DictReader(fh)}


def plans_from_nn(row: dict) -> list[dict]:
    drift = float(row["nn_drift"])
    spread = float(row["nn_spread"])
    plans = [
        {"name": "medium-default", "preset": "medium", "x264_params": {}, "keyint": None,
         "reason": ["候选：preset=medium，默认参数"]},
        {"name": "veryslow-default", "preset": "veryslow", "x264_params": {}, "keyint": None,
         "reason": ["候选：preset=veryslow"]},
    ]
    if drift >= MOTION_HIGH:
        plans.append({"name": "nn-aq-motion", "preset": "medium",
                      "x264_params": {"aq-mode": 2, "aq-strength": 1.0, "refs": 3, "bf": 3},
                      "keyint": 60,
                      "reason": [f"NN drift {drift:.3f} → aq-motion"]})
    else:
        plans.append({"name": "nn-long-gop", "preset": "medium",
                      "x264_params": {"aq-mode": 1, "aq-strength": 1.0, "refs": 5, "bf": 0},
                      "keyint": 120,
                      "reason": [f"NN drift {drift:.3f}, spread {spread:.3f} → long-gop"]})
    return plans


def main():
    nn = load_nn()
    rows = []
    for name in DEV:
        video = DATASET / f"{name}.mp4"
        info = probe.describe(video)
        for ratio in RATIOS:
            tag = f"{int(round(ratio * 100))}%"
            target = int(info[f"target_bytes_{tag}"])
            out_root = OUT / name / f"{int(ratio*100)}pct"
            best = None
            best_psnr = float("-inf")
            best_plan = None
            all_logs = []
            for plan in plans_from_nn(nn[name]):
                candidate, logs = encode.encode_to_budget(
                    video=video, ratio=ratio, target_bytes=target,
                    duration_s=float(info["duration_s"]),
                    out_dir=out_root / plan["name"],
                    extra_args=decision.ffmpeg_args(plan), max_attempts=2,
                )
                all_logs.extend(logs)
                if not candidate:
                    continue
                metrics = evaluate.compare(video, Path(candidate["output"]))
                psnr = float(metrics.get("psnr_y_db", float("-inf")))
                if best is None or psnr > best_psnr:
                    best, best_psnr, best_plan = candidate, psnr, plan
            row = {
                "mode": "adaptive-nn", "video_id": name, "ratio": tag,
                "target_bytes": target, "actual_bytes": best["actual_bytes"] if best else 0,
                "rel_error": best["rel_error"] if best else "",
                "psnr_y_db": best_psnr, "candidate": best_plan["name"] if best_plan else "",
                "nn_drift": nn[name]["nn_drift"], "nn_spread": nn[name]["nn_spread"],
                "output": best["output"] if best else "",
            }
            rows.append(row)
            print(row)

    with (LOGS / "nn_results.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print("written", LOGS / "nn_results.csv")


if __name__ == "__main__":
    main()
