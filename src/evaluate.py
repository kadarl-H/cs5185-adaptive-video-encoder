"""Quality evaluation: PSNR-Y, MS-SSIM and aligned frame export."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from . import config

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

C1 = (0.01 * 255) ** 2
C2 = (0.03 * 255) ** 2
MS_WEIGHTS = (0.0448, 0.2856, 0.3001, 0.2363, 0.1333)


def _require_cv2() -> None:
    if cv2 is None:
        raise RuntimeError("需要 opencv-python：pip install opencv-python")


def _ssim(a: np.ndarray, b: np.ndarray) -> float:
    mu1 = cv2.GaussianBlur(a, (11, 11), 1.5)
    mu2 = cv2.GaussianBlur(b, (11, 11), 1.5)
    mu1_sq, mu2_sq, mu1_mu2 = mu1 ** 2, mu2 ** 2, mu1 * mu2
    sigma1_sq = cv2.GaussianBlur(a * a, (11, 11), 1.5) - mu1_sq
    sigma2_sq = cv2.GaussianBlur(b * b, (11, 11), 1.5) - mu2_sq
    sigma12 = cv2.GaussianBlur(a * b, (11, 11), 1.5) - mu1_mu2
    ssim_map = ((2 * mu1_mu2 + C1) * (2 * sigma12 + C2)) / (
        (mu1_sq + mu2_sq + C1) * (sigma1_sq + sigma2_sq + C2)
    )
    return float(ssim_map.mean())


def ms_ssim(a: np.ndarray, b: np.ndarray) -> float:
    """Multi-scale SSIM on grayscale float images (0..255)."""
    values = []
    for level in range(len(MS_WEIGHTS)):
        values.append(max(_ssim(a, b), 0.0))
        if level < len(MS_WEIGHTS) - 1:
            a = cv2.pyrDown(a)
            b = cv2.pyrDown(b)
    return float(np.prod([v ** w for v, w in zip(values, MS_WEIGHTS)]))


def compare(ref: Path, out: Path, stride: int = 5) -> dict:
    """Aggregate PSNR-Y over all frames; sample MS-SSIM every *stride* frames."""
    _require_cv2()
    cap_ref = cv2.VideoCapture(str(ref))
    cap_out = cv2.VideoCapture(str(out))
    if not (cap_ref.isOpened() and cap_out.isOpened()):
        raise RuntimeError("无法打开参考或输出视频。")

    sq_sum = 0.0
    pixels = 0
    frames = 0
    msssim_values: list[float] = []

    while True:
        ok1, f1 = cap_ref.read()
        ok2, f2 = cap_out.read()
        if not (ok1 and ok2):
            break
        y1 = cv2.cvtColor(f1, cv2.COLOR_BGR2YCrCb)[:, :, 0].astype(np.float32)
        y2 = cv2.cvtColor(f2, cv2.COLOR_BGR2YCrCb)[:, :, 0].astype(np.float32)
        if y1.shape != y2.shape:
            raise RuntimeError(f"分辨率不一致：{y1.shape} vs {y2.shape}")

        diff = y1 - y2
        sq_sum += float(np.sum(diff * diff))
        pixels += diff.size
        frames += 1
        if frames % stride == 0:
            msssim_values.append(ms_ssim(y1, y2))

    cap_ref.release()
    cap_out.release()

    if not pixels:
        raise RuntimeError("没有可比对的帧。")
    mse = sq_sum / pixels
    psnr = float("inf") if mse == 0 else float(10 * np.log10(255.0 ** 2 / mse))
    return {
        "frames_compared": frames,
        "psnr_y_db": round(psnr, 3) if psnr != float("inf") else "inf",
        "ms_ssim": round(float(np.mean(msssim_values)), 5) if msssim_values else None,
    }


def export_frames(ref: Path, out: Path, times: list[float], dst_dir: Path) -> list[str]:
    """Save side-by-side reference/output frames at the given timestamps."""
    _require_cv2()
    dst_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    cap_ref = cv2.VideoCapture(str(ref))
    cap_out = cv2.VideoCapture(str(out))
    fps = cap_ref.get(cv2.CAP_PROP_FPS) or 30.0
    for t in times:
        idx = int(round(t * fps))
        cap_ref.set(cv2.CAP_PROP_POS_FRAMES, idx)
        cap_out.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok1, f1 = cap_ref.read()
        ok2, f2 = cap_out.read()
        if not (ok1 and ok2):
            continue
        pair = np.hstack([f1, f2])
        name = dst_dir / f"t{t:05.2f}s.png"
        cv2.imwrite(str(name), pair)
        saved.append(str(name))
    cap_ref.release()
    cap_out.release()
    return saved


def main() -> None:
    parser = argparse.ArgumentParser(description="PSNR-Y / MS-SSIM / 抽帧对比")
    parser.add_argument("--ref", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--frames", default="", help="逗号分隔的时间点，如 0,2.5")
    parser.add_argument("--outdir", type=Path, default=config.REPORT_DIR / "frames")
    args = parser.parse_args()

    metrics = compare(args.ref, args.out)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))

    if args.frames:
        times = [float(x) for x in args.frames.split(",") if x.strip()]
        saved = export_frames(args.ref, args.out, times, args.outdir / args.out.stem)
        print(f"已保存 {len(saved)} 张对比帧到 {args.outdir / args.out.stem}")


if __name__ == "__main__":
    main()
