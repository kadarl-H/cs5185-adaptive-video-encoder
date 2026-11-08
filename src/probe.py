"""Metadata reading and bitrate-budget calculation.

    python -m src.probe --data data/CS5185_Project_Video_Dataset --out logs/videos.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
from pathlib import Path

from . import config

VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".y4m"}


def ffprobe_json(path: Path) -> dict:
    """Return ffprobe's JSON for *path* (raises if ffprobe is missing)."""
    exe = shutil.which("ffprobe")
    if not exe:
        raise RuntimeError("找不到 ffprobe，请先安装 FFmpeg 并加入 PATH。")
    cmd = [
        exe, "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def video_duration(path: Path) -> float:
    return float(ffprobe_json(path)["format"]["duration"])


def load_metadata(video: Path) -> dict:
    """Load the dataset's metadata/<stem>.json if it exists, else {}."""
    for meta_dir in (video.parent / "metadata", video.parent.parent / "metadata"):
        candidate = meta_dir / f"{video.stem}.json"
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8"))
    return {}


def budget(size_bytes: int, ratio: float, duration_s: float) -> dict:
    """Target size in whole bytes and the initial video bitrate."""
    target_bytes = int(size_bytes * ratio)  # floor，不四舍五入到 MB
    video_bps = config.OVERHEAD * 8.0 * target_bytes / duration_s
    return {
        "ratio": ratio,
        "target_bytes": target_bytes,
        "target_kbps": round(video_bps / 1000.0, 1),
    }


def describe(video: Path) -> dict:
    meta = load_metadata(video)
    if meta.get("duration") and meta.get("bytes"):
        duration = float(meta["duration"])
        size = int(meta["bytes"])
        width, height = meta.get("width"), meta.get("height")
        fps = meta.get("fps")
    else:
        probe = ffprobe_json(video)
        stream = next(s for s in probe["streams"] if s.get("codec_type") == "video")
        duration = float(probe["format"]["duration"])
        size = int(probe["format"]["size"])
        width, height = stream.get("width"), stream.get("height")
        fps = stream.get("avg_frame_rate")

    row = {
        "video_id": video.stem,
        "file": video.name,
        "duration_s": duration,
        "bytes": size,
        "width": width,
        "height": height,
        "fps": fps,
    }
    for r in config.RATIOS:
        b = budget(size, r, duration)
        tag = f"{int(round(r * 100))}%"
        row[f"target_bytes_{tag}"] = b["target_bytes"]
        row[f"target_kbps_{tag}"] = b["target_kbps"]
    return row


def collect(dataset_dir: Path) -> list[dict]:
    files = sorted(p for p in dataset_dir.rglob("*") if p.suffix.lower() in VIDEO_SUFFIXES)
    rows = []
    for video in files:
        try:
            rows.append(describe(video))
        except Exception as exc:  # noqa: BLE001 - report and continue
            print(f"[warn] {video.name}: {exc}")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="读取视频元数据并计算两档预算")
    parser.add_argument("--data", type=Path, default=config.DATA_DIR / config.DATASET_DIRNAME)
    parser.add_argument("--out", type=Path, default=config.LOG_DIR / "videos.csv")
    args = parser.parse_args()

    config.ensure_dirs()
    rows = collect(args.data)
    if not rows:
        print(f"没有在 {args.data} 找到视频文件。")
        return

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"已写入 {args.out}（{len(rows)} 个视频）")

    for row in rows:
        print(
            f"{row['video_id']:<24} {row['bytes']/1e6:8.1f} MB  "
            f"5%: {row['target_bytes_5%']/1e6:6.2f} MB / {row['target_kbps_5%']:7.1f} kbps  "
            f"2%: {row['target_bytes_2%']/1e6:6.2f} MB / {row['target_kbps_2%']:7.1f} kbps"
        )


if __name__ == "__main__":
    main()
