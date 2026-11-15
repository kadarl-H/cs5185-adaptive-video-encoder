"""Standalone check: medium + -tune animation on dev clips."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from src import encode, evaluate, probe

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "CS5185_Project_Video_Dataset"
OUT = ROOT / "out" / "tune_animation"
DEV = ["01_FourPeople", "02_Beauty", "03_Bosphorus", "04_HoneyBee", "07_Mobcal", "08_Shields"]
TEST = ["05_Jockey", "06_ShakeNDry", "09_Parkrun", "10_Stockholm"]
RATIOS = [0.05, 0.02]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    args = parser.parse_args()
    names = DEV if args.split == "dev" else TEST
    rows = []
    for name in names:
        video = DATASET / f"{name}.mp4"
        info = probe.describe(video)
        for ratio in RATIOS:
            tag = f"{int(round(ratio * 100))}%"
            target = int(info[f"target_bytes_{tag}"])
            best, _ = encode.encode_to_budget(
                video=video, ratio=ratio, target_bytes=target,
                duration_s=float(info["duration_s"]),
                out_dir=OUT / name / f"{int(ratio*100)}pct",
                extra_args=["-preset", "medium", "-tune", "animation"],
                max_attempts=2,
            )
            metrics = evaluate.compare(video, Path(best["output"]))
            row = {"video": name, "ratio": tag, "rel_error": best["rel_error"],
                   "psnr": float(metrics.get("psnr_y_db", "")),
                   "ms_ssim": float(metrics.get("ms_ssim", ""))}
            rows.append(row)
            print(row)
    out_name = "tune_anim_dev.csv" if args.split == "dev" else "tune_anim_test.csv"
    with (ROOT / "logs" / out_name).open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
