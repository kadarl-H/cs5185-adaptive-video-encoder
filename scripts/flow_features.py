"""Farneback optical-flow features (non-neural motion estimate).

For each development clip: dense flow between consecutive frames at half
resolution, mean/p95 magnitude. Writes reports/features_flow.csv.
"""
from __future__ import annotations

import csv
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "CS5185_Project_Video_Dataset"
OUT = ROOT / "reports" / "features_flow.csv"
DEV = ["01_FourPeople", "02_Beauty", "03_Bosphorus", "04_HoneyBee", "07_Mobcal", "08_Shields"]


def main():
    rows = []
    for name in DEV:
        cap = cv2.VideoCapture(str(DATASET / f"{name}.mp4"))
        ok, prev = cap.read()
        if not ok:
            continue
        prev = cv2.resize(cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY), (640, 360))
        mags = []
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            gray = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (640, 360))
            flow = cv2.calcOpticalFlowFarneback(
                prev, gray, None,
                pyr_scale=0.5, levels=3, winsize=21,
                iterations=3, poly_n=5, poly_sigma=1.2, flags=0,
            )
            mag = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
            mags.append(float(mag.mean()))
            prev = gray
        cap.release()
        arr = np.array(mags)
        row = {
            "video": name,
            "flow_mean": round(float(arr.mean()), 4),
            "flow_p95": round(float(np.percentile(arr, 95)), 4),
            "flow_max": round(float(arr.max()), 4),
        }
        rows.append(row)
        print(row)

    with OUT.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print("written", OUT)


if __name__ == "__main__":
    main()
