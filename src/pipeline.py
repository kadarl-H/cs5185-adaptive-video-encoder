"""End-to-end pipeline: probe -> features -> decision -> encode -> evaluate.

    python -m src.pipeline --split dev --ratios 0.05 0.02
    python -m src.pipeline --video data/.../01_FourPeople.mp4 --ratio 0.05
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

from . import config, decision, encode, evaluate, features, probe


def discover(split: str) -> list[Path]:
    dataset = config.DATA_DIR / config.DATASET_DIRNAME
    videos = sorted(p for p in dataset.rglob("*.mp4"))
    if split == "all":
        return videos
    keep = config.DEV_IDS if split == "dev" else config.TEST_IDS
    return [p for p in videos if p.stem[:2] in keep]


def features_for(video: Path) -> dict:
    cache = config.REPORT_DIR / "features" / f"{video.stem}.csv"
    if cache.exists():
        with cache.open(encoding="utf-8") as fh:
            rows = [
                {k: (float(v) if k != "frame" else int(v)) for k, v in row.items()}
                for row in csv.DictReader(fh)
            ]
    else:
        rows = features.extract(video)
        features.save_csv(rows, cache)
        features.plot(rows, cache.with_suffix(".png"), title=video.stem)
    return features.summary(rows)


def append_result(row: dict) -> None:
    path = config.LOG_DIR / "results.csv"
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(row.keys()))
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def run_one(video: Path, ratio: float, attempts: int, do_eval: bool) -> dict:
    info = probe.describe(video)
    tag = f"{int(round(ratio * 100))}%"

    try:
        feat = features_for(video)
    except Exception as exc:  # noqa: BLE001 - features are optional for a first run
        print(f"[warn] 特征提取失败（{exc}），使用默认参数。")
        feat = {"diff_mean": 0.0, "edge_mean": 0.0}

    plan = decision.choose(feat, ratio)
    target = int(info[f"target_bytes_{tag}"])

    start = time.perf_counter()
    best, logs = encode.encode_to_budget(
        video=video,
        ratio=ratio,
        target_bytes=target,
        duration_s=float(info["duration_s"]),
        out_dir=config.OUT_DIR / video.stem / f"{tag}pct",
        extra_args=decision.ffmpeg_args(plan),
        max_attempts=attempts,
    )

    metrics = {}
    if best and do_eval:
        try:
            metrics = evaluate.compare(video, Path(best["output"]))
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] 评测失败：{exc}")

    elapsed = time.perf_counter() - start
    row = {
        "video_id": info["video_id"],
        "ratio": tag,
        "target_bytes": target,
        "target_kbps": info[f"target_kbps_{tag}"],
        "actual_bytes": best["actual_bytes"] if best else 0,
        "actual_kbps": best["actual_kbps"] if best else 0,
        "rel_error": best["rel_error"] if best else "",
        "attempts": len(logs),
        "decode_ok": best["decode_ok"] if best else False,
        "psnr_y_db": metrics.get("psnr_y_db", ""),
        "ms_ssim": metrics.get("ms_ssim", ""),
        "encode_time_s": round(sum(x.get("encode_time_s", 0) for x in logs), 2),
        "total_time_s": round(elapsed, 2),
        "preset": plan["preset"],
        "x264_params": json.dumps(plan["x264_params"], separators=(",", ":")),
        "output": best["output"] if best else "",
        "reason": " | ".join(plan["reason"]),
    }

    log_path = config.LOG_DIR / f"{video.stem}_{tag}_attempts.jsonl"
    log_path.write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in logs) + "\n",
        encoding="utf-8",
    )
    append_result(row)
    print(json.dumps(row, ensure_ascii=False, indent=2))
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description="内容自适应编码流水线")
    parser.add_argument("--video", type=Path, action="append", default=None)
    parser.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    parser.add_argument("--ratios", type=float, nargs="+", default=list(config.RATIOS))
    parser.add_argument("--ratio", type=float, default=None)
    parser.add_argument("--attempts", type=int, default=config.MAX_ATTEMPTS)
    parser.add_argument("--no-eval", action="store_true")
    args = parser.parse_args()

    config.ensure_dirs()
    ratios = [args.ratio] if args.ratio else args.ratios
    videos = args.video or discover(args.split)
    if not videos:
        print("没有找到视频，请检查 data/ 目录结构。")
        return

    for video in videos:
        for ratio in ratios:
            print(f"\n=== {video.name} @ {ratio:.0%} ===")
            run_one(video, ratio, args.attempts, not args.no_eval)


if __name__ == "__main__":
    main()
