"""Two-pass x264 encoding with a size-feedback loop."""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

from . import config

NULL_SINK = "NUL" if os.name == "nt" else "/dev/null"


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("找不到 ffmpeg，请安装 FFmpeg 并加入 PATH。")
    return exe


def two_pass(
    src: Path,
    dst: Path,
    kbps: int,
    extra_args: list[str] | None = None,
    job_prefix: Path | None = None,
) -> float:
    """Encode *src* to *dst* with two passes; returns elapsed seconds."""
    exe = _ffmpeg()
    extra_args = extra_args or []
    job_prefix = job_prefix or dst.with_suffix("")
    job_prefix.parent.mkdir(parents=True, exist_ok=True)

    common = [
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-b:v", f"{kbps}k",
        # 短片段上纯 ABR 两遍会明显超预算，VBV 上限把实际码率压回目标
        "-maxrate", f"{kbps}k",
        "-bufsize", f"{kbps * 2}k",
        *extra_args,
        "-passlogfile", str(job_prefix),
    ]

    pass1 = [exe, "-hide_banner", "-y", "-i", str(src), "-an", *common,
             "-pass", "1", "-f", "null", NULL_SINK]
    pass2 = [exe, "-hide_banner", "-y", "-i", str(src), "-an", *common,
             "-pass", "2", "-movflags", "+faststart", str(dst)]

    start = time.perf_counter()
    subprocess.run(pass1, check=True, capture_output=True)
    subprocess.run(pass2, check=True, capture_output=True)
    return time.perf_counter() - start


def decode_check(path: Path) -> bool:
    """Validate that the file decodes end-to-end."""
    exe = _ffmpeg()
    cmd = [exe, "-v", "error", "-xerror", "-i", str(path),
           "-map", "0:v:0", "-f", "null", NULL_SINK]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode == 0


def encode_to_budget(
    video: Path,
    ratio: float,
    target_bytes: int,
    duration_s: float,
    out_dir: Path,
    extra_args: list[str] | None = None,
    max_attempts: int = config.MAX_ATTEMPTS,
    tolerance: float = config.SIZE_TOLERANCE,
    initial_kbps: int | None = None,
) -> tuple[dict | None, list[dict]]:
    """Try up to *max_attempts* encodes, keeping every candidate on disk.

    Returns (best_attempt, all_attempts). ``best_attempt`` is the one closest to
    the target size among decodable candidates.
    """
    tag = f"{int(round(ratio * 100))}pct"
    out_dir.mkdir(parents=True, exist_ok=True)

    bps = config.OVERHEAD * 8.0 * target_bytes / duration_s
    if initial_kbps:
        bps = float(initial_kbps) * 1000.0
    attempts: list[dict] = []
    best: dict | None = None

    for i in range(max_attempts):
        kbps = max(1, round(bps / 1000.0))
        dst = out_dir / f"{video.stem}_{tag}_a{i}.mp4"
        record: dict = {"attempt": i, "kbps": kbps, "output": str(dst)}

        try:
            elapsed = two_pass(video, dst, kbps, extra_args,
                               job_prefix=out_dir / f"{video.stem}_{tag}_a{i}")
        except subprocess.CalledProcessError as exc:
            record.update(status="encode_failed",
                          error=(exc.stderr or b"").decode("utf-8", "ignore")[-2000:])
            attempts.append(record)
            continue

        actual = dst.stat().st_size if dst.exists() else 0
        ok = bool(actual) and decode_check(dst)
        error = abs(actual - target_bytes) / target_bytes if target_bytes else 1.0
        record.update(
            actual_bytes=actual,
            actual_kbps=round(8 * actual / duration_s / 1000.0, 1),
            rel_error=round(error, 4),
            decode_ok=ok,
            encode_time_s=round(elapsed, 2),
            status="ok" if ok else "decode_failed",
        )
        attempts.append(record)

        if ok and (best is None or error < best["rel_error"]):
            best = record
        if ok and error <= tolerance:
            break

        if actual:
            bps = bps * target_bytes / actual * config.OVERHEAD
        else:
            bps *= 0.8

    return best, attempts
