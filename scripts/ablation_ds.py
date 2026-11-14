"""2x2 ablation on the DS pipeline: preset {medium,slow} x AQ {1,2}, default GOP."""
from __future__ import annotations

import csv
from pathlib import Path

from src import config, encode, evaluate, probe

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "ablation"
LOGS = ROOT / "logs"
REPORTS = ROOT / "reports"
DATASET = ROOT / "data" / "CS5185_Project_Video_Dataset"
VIDEOS = ["01_FourPeople", "03_Bosphorus", "07_Mobcal"]
RATIOS = [0.05, 0.02]

CONFIGS = {
    "A_medium_aq1": ["-preset", "medium"],
    "B_slow_aq1": ["-preset", "slow"],
    "C_medium_aq2": ["-preset", "medium", "-x264-params", "aq-mode=2:aq-strength=1.0"],
    "D_slow_aq2": ["-preset", "slow", "-x264-params", "aq-mode=2:aq-strength=1.0"],
}


def main():
    rows = []
    for name in VIDEOS:
        video = DATASET / f"{name}.mp4"
        info = probe.describe(video)
        duration = float(info["duration_s"])
        for ratio in RATIOS:
            tag = f"{int(round(ratio * 100))}%"
            target = int(info[f"target_bytes_{tag}"])
            for cfg, args in CONFIGS.items():
                out_dir = OUT / name / f"{int(ratio*100)}pct" / cfg
                best, logs = encode.encode_to_budget(
                    video=video, ratio=ratio, target_bytes=target,
                    duration_s=duration, out_dir=out_dir,
                    extra_args=args, max_attempts=3,
                )
                if not best:
                    print("FAILED", name, tag, cfg)
                    continue
                metrics = evaluate.compare(video, Path(best["output"]))
                row = {
                    "video": name, "ratio": tag, "config": cfg,
                    "actual_bytes": best["actual_bytes"],
                    "rel_error": best["rel_error"],
                    "psnr": metrics.get("psnr_y_db", ""),
                    "ms_ssim": metrics.get("ms_ssim", ""),
                    "encode_s": best["encode_time_s"],
                }
                rows.append(row)
                print(row)

    out_csv = LOGS / "ablation.csv"
    with out_csv.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    lines = ["# DS 2x2 ablation (default GOP)", "",
             "| video | ratio | config | PSNR | MS-SSIM | size err |",
             "|---|---|---|---:|---:|---:|"]
    for r in rows:
        lines.append(f"| {r['video']} | {r['ratio']} | {r['config']} | "
                     f"{float(r['psnr']):.3f} | {float(r['ms_ssim']):.5f} | {float(r['rel_error']):+.2%} |")
    (REPORTS / "ablation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("written", out_csv)


if __name__ == "__main__":
    main()
