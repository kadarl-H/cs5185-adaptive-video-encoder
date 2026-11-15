"""One-at-a-time screening of additional x264 knobs.

For two clips and both budgets, compare the default medium/AQ1 plan against
single-parameter changes (subq, me, lookahead, refs, bf, mbtree, tune).
"""
from __future__ import annotations

import csv
from pathlib import Path

from src import encode, evaluate, probe

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"
DATASET = ROOT / "data" / "CS5185_Project_Video_Dataset"
OUT = ROOT / "out" / "screen"
VIDEOS = ["01_FourPeople", "07_Mobcal"]
RATIOS = [0.05, 0.02]

VARIANTS = {
    "base": [],
    "subq9": ["-x264-params", "subq=9"],
    "me_umh": ["-x264-params", "me=umh"],
    "lookahead40": ["-rc-lookahead", "40"],
    "refs5": ["-refs", "5"],
    "bf4": ["-bf", "4"],
    "mbtree_off": ["-mbtree", "0"],
    "tune_film": ["-tune", "film"],
    "tune_animation": ["-tune", "animation"],
}


def main():
    rows = []
    for name in VIDEOS:
        video = DATASET / f"{name}.mp4"
        info = probe.describe(video)
        for ratio in RATIOS:
            tag = f"{int(round(ratio * 100))}%"
            target = int(info[f"target_bytes_{tag}"])
            for variant, extra in VARIANTS.items():
                best, _ = encode.encode_to_budget(
                    video=video, ratio=ratio, target_bytes=target,
                    duration_s=float(info["duration_s"]),
                    out_dir=OUT / name / f"{int(ratio*100)}pct" / variant,
                    extra_args=["-preset", "medium"] + extra,
                    max_attempts=2,
                )
                if not best:
                    continue
                metrics = evaluate.compare(video, Path(best["output"]))
                row = {
                    "video": name, "ratio": tag, "variant": variant,
                    "rel_error": best["rel_error"],
                    "psnr": float(metrics.get("psnr_y_db", "")),
                    "ms_ssim": float(metrics.get("ms_ssim", "")),
                    "encode_s": best["encode_time_s"],
                }
                rows.append(row)
                print(row)

    with (LOGS / "param_screen.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print("written", LOGS / "param_screen.csv")


if __name__ == "__main__":
    main()
