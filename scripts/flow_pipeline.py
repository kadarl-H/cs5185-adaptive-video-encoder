"""Adaptive pipeline driven by Farneback optical-flow magnitude."""
from __future__ import annotations

import csv
from pathlib import Path

from src import decision, encode, evaluate, probe

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"
REPORTS = ROOT / "reports"
DATASET = ROOT / "data" / "CS5185_Project_Video_Dataset"
OUT = ROOT / "out" / "flow"
DEV = ["01_FourPeople", "02_Beauty", "03_Bosphorus", "04_HoneyBee", "07_Mobcal", "08_Shields"]
RATIOS = [0.05, 0.02]
FLOW_HIGH = 1.0  # px/frame at half resolution


def load_flow():
    with (REPORTS / "features_flow.csv").open(encoding="utf-8-sig") as fh:
        return {r["video"]: r for r in csv.DictReader(fh)}


def plans(row: dict) -> list[dict]:
    flow = float(row["flow_mean"])
    plans = [
        {"name": "medium-default", "preset": "medium", "x264_params": {}, "keyint": None,
         "reason": ["候选：preset=medium，默认参数"]},
        {"name": "veryslow-default", "preset": "veryslow", "x264_params": {}, "keyint": None,
         "reason": ["候选：preset=veryslow"]},
    ]
    if flow >= FLOW_HIGH:
        plans.append({"name": "flow-aq-motion", "preset": "medium",
                      "x264_params": {"aq-mode": 2, "aq-strength": 1.0, "refs": 3, "bf": 3},
                      "keyint": 60, "reason": [f"flow {flow:.2f} → aq-motion"]})
    else:
        plans.append({"name": "flow-long-gop", "preset": "medium",
                      "x264_params": {"aq-mode": 1, "aq-strength": 1.0, "refs": 5, "bf": 0},
                      "keyint": 120, "reason": [f"flow {flow:.2f} → long-gop"]})
    return plans


def main():
    flow = load_flow()
    rows = []
    for name in DEV:
        video = DATASET / f"{name}.mp4"
        info = probe.describe(video)
        for ratio in RATIOS:
            tag = f"{int(round(ratio * 100))}%"
            target = int(info[f"target_bytes_{tag}"])
            best, best_psnr, best_plan = None, float("-inf"), None
            for plan in plans(flow[name]):
                candidate, _ = encode.encode_to_budget(
                    video=video, ratio=ratio, target_bytes=target,
                    duration_s=float(info["duration_s"]),
                    out_dir=OUT / name / f"{int(ratio*100)}pct" / plan["name"],
                    extra_args=decision.ffmpeg_args(plan), max_attempts=2,
                )
                if not candidate:
                    continue
                metrics = evaluate.compare(video, Path(candidate["output"]))
                psnr = float(metrics.get("psnr_y_db", float("-inf")))
                if psnr > best_psnr:
                    best, best_psnr, best_plan = candidate, psnr, plan
            row = {
                "mode": "adaptive-flow", "video_id": name, "ratio": tag,
                "target_bytes": target, "actual_bytes": best["actual_bytes"] if best else 0,
                "rel_error": best["rel_error"] if best else "",
                "psnr_y_db": best_psnr, "candidate": best_plan["name"] if best_plan else "",
                "flow_mean": flow[name]["flow_mean"], "output": best["output"] if best else "",
            }
            rows.append(row)
            print(row)

    with (LOGS / "flow_results.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print("written", LOGS / "flow_results.csv")


if __name__ == "__main__":
    main()
