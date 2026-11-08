"""Content analysis: temporal change and spatial detail per frame.

    python -m src.features --video data/.../01_FourPeople.mp4
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from . import config

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None


def _require_cv2() -> None:
    if cv2 is None:
        raise RuntimeError("需要 opencv-python：pip install opencv-python")


def extract(video: Path, edge_threshold: int = 40) -> list[dict]:
    """Return per-frame measurements: time, mean abs frame difference, edge fraction."""
    _require_cv2()
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"无法打开视频：{video}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    rows: list[dict] = []
    prev_gray = None
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        if prev_gray is None:
            diff = 0.0
        else:
            diff = float(np.mean(cv2.absdiff(gray, prev_gray)))

        gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        mag = cv2.magnitude(gx, gy)
        edge_fraction = float(np.mean(mag > edge_threshold))

        rows.append({
            "frame": idx,
            "t": round(idx / fps, 3),
            "frame_diff": round(diff, 4),
            "edge_fraction": round(edge_fraction, 6),
        })
        prev_gray = gray
        idx += 1

    cap.release()
    if not rows:
        raise RuntimeError(f"视频没有可读帧：{video}")
    return rows


def summary(rows: list[dict]) -> dict:
    diff = np.array([r["frame_diff"] for r in rows], dtype=float)
    edge = np.array([r["edge_fraction"] for r in rows], dtype=float)
    return {
        "frames": len(rows),
        "duration_s": rows[-1]["t"] - rows[0]["t"],
        "diff_mean": round(float(diff.mean()), 4),
        "diff_std": round(float(diff.std()), 4),
        "diff_p95": round(float(np.percentile(diff, 95)), 4),
        "edge_mean": round(float(edge.mean()), 6),
        "edge_p95": round(float(np.percentile(edge, 95)), 6),
    }


def save_csv(rows: list[dict], dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def plot(rows: list[dict], dst: Path, title: str = "") -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("[warn] 未安装 matplotlib，跳过画图。")
        return

    t = [r["t"] for r in rows]
    fig, axes = plt.subplots(2, 1, figsize=(10, 5), sharex=True)
    axes[0].plot(t, [r["frame_diff"] for r in rows], color="#d62728")
    axes[0].set_ylabel("mean abs frame diff")
    axes[1].plot(t, [r["edge_fraction"] for r in rows], color="#1f77b4")
    axes[1].set_ylabel("edge pixel fraction")
    axes[1].set_xlabel("time (s)")
    if title:
        fig.suptitle(title)
    fig.tight_layout()
    dst.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(dst, dpi=150)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="提取帧差与边缘特征")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=config.REPORT_DIR)
    parser.add_argument("--no-plot", action="store_true")
    args = parser.parse_args()

    rows = extract(args.video)
    stem = args.video.stem
    csv_path = args.out_dir / "features" / f"{stem}.csv"
    save_csv(rows, csv_path)
    if not args.no_plot:
        plot(rows, args.out_dir / "features" / f"{stem}.png", title=stem)

    info = summary(rows)
    print(json.dumps(info, ensure_ascii=False, indent=2))
    print(f"CSV: {csv_path}")


if __name__ == "__main__":
    main()
