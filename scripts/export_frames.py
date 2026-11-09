"""Export aligned reference/output frame pairs for representative videos.

    python -m scripts.export_frames
"""
from __future__ import annotations

import csv
from pathlib import Path

from src import config, evaluate

WANTED = {("03_Bosphorus", "5%"), ("03_Bosphorus", "2%"),
          ("04_HoneyBee", "5%"), ("07_Mobcal", "5%"), ("07_Mobcal", "2%")}
TIMES = [0.5, 2.5, 4.5]


def main() -> None:
    path = config.LOG_DIR / "results.csv"
    with path.open(encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))

    dataset = config.DATA_DIR / config.DATASET_DIRNAME
    for row in rows:
        key = (row["video_id"], row["ratio"])
        if key not in WANTED or row.get("mode") != "adaptive":
            continue
        ref = dataset / f"{row['video_id']}.mp4"
        out = Path(row["output"])
        dst = config.REPORT_DIR / "frames" / f"{row['video_id']}_{row['ratio']}"
        saved = evaluate.export_frames(ref, out, TIMES, dst)
        print(f"{key}: {len(saved)} frames -> {dst}")


if __name__ == "__main__":
    main()
