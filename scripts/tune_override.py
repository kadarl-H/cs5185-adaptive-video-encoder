"""Content overrides on top of -tune animation.

A: tune only
B: tune + GOP from frame difference
C: tune + AQ1 for high-edge clips (tune already uses AQ2)
D: tune + both
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np

from src import config, encode, evaluate, probe

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"
DATASET = ROOT / "data" / "CS5185_Project_Video_Dataset"
OUT = ROOT / "out" / "tune_override"
DEV = ["01_FourPeople", "02_Beauty", "03_Bosphorus", "04_HoneyBee", "07_Mobcal", "08_Shields"]
TEST = ["05_Jockey", "06_ShakeNDry", "09_Parkrun", "10_Stockholm"]
RATIOS = [0.05, 0.02]
FEATURES = ROOT / "reports" / "features"


def features(name: str) -> tuple[float, float]:
    with (FEATURES / f"{name}.csv").open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    diff = np.mean([float(r["frame_diff"]) for r in rows[1:]])
    edge = np.mean([float(r["edge_fraction"]) for r in rows[1:]])
    return float(diff), float(edge)


def variants(diff: float, edge: float) -> dict[str, list[str]]:
    g = max(60, min(250, round(250 - 6 * diff)))
    gop = ["-g", str(g)]
    aq = ["-x264-params", "aq-mode=1"] if edge >= 0.12 else []
    base = ["-preset", "medium", "-tune", "animation"]
    return {
        "A_tune": base,
        "B_tune_g": base + gop,
        "C_tune_aq": base + aq,
        "D_tune_g_aq": base + gop + aq,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    args = parser.parse_args()
    names = DEV if args.split == "dev" else TEST
    rows = []
    for name in names:
        video = DATASET / f"{name}.mp4"
        info = probe.describe(video)
        diff, edge = features(name)
        for ratio in RATIOS:
            tag = f"{int(round(ratio * 100))}%"
            target = int(info[f"target_bytes_{tag}"])
            best, best_psnr, best_var, best_in, best_ms = None, float("-inf"), None, False, float("-inf")
            cache: dict[tuple, tuple] = {}
            for vname, extra in variants(diff, edge).items():
                key = tuple(extra)
                if key in cache:
                    cand, metrics = cache[key]
                else:
                    cand, _ = encode.encode_to_budget(
                        video=video, ratio=ratio, target_bytes=target,
                        duration_s=float(info["duration_s"]),
                        out_dir=OUT / name / f"{int(ratio*100)}pct" / vname,
                        extra_args=extra, max_attempts=2,
                    )
                    metrics = evaluate.compare(video, Path(cand["output"])) if cand else {}
                    cache[key] = (cand, metrics)
                if not cand:
                    continue
                psnr = float(metrics.get("psnr_y_db", float("-inf")))
                in_budget = abs(float(cand["rel_error"])) <= config.SIZE_TOLERANCE
                better = (in_budget and not best_in) or (in_budget == best_in and psnr > best_psnr)
                if best is None or better:
                    best, best_psnr, best_var, best_in = cand, psnr, vname, in_budget
                    best_ms = float(metrics.get("ms_ssim", float("-inf")))
            rows.append({
                "video": name, "ratio": tag, "diff": round(diff, 2), "edge": round(edge, 3),
                "psnr": best_psnr, "variant": best_var,
                "rel_error": best["rel_error"] if best else "",
                "ms_ssim": best_ms,
            })
            print(rows[-1])

    out_name = f"tune_override_{args.split}.csv"
    with (LOGS / out_name).open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print("written", LOGS / out_name)


if __name__ == "__main__":
    main()
