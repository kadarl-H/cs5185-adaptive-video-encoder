"""End-to-end pipeline: probe -> features -> decision -> encode -> evaluate.

    python -m src.pipeline --split dev --ratios 0.05 0.02
    python -m src.pipeline --video data/.../01_FourPeople.mp4 --ratio 0.05
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import time
from pathlib import Path

from . import config, decision, encode, evaluate, features, llm_decision, probe


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


def append_result(path: Path, row: dict) -> None:
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(row.keys()))
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def _evaluate(video: Path, output: str) -> dict:
    try:
        return evaluate.compare(video, Path(output))
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] 评测失败：{exc}")
        return {}


def _psnr(metrics: dict) -> float:
    try:
        return float(metrics.get("psnr_y_db"))
    except (TypeError, ValueError):
        return float("-inf")


def run_llm_candidate(video: Path, ratio: float, target: int, duration_s: float,
                      out_dir: Path, attempts: int, feat: dict, tag: str):
    """Iterative LLM decision: feed each attempt's result back into the next call."""
    history: list[dict] = []
    logs: list[dict] = []
    best = None
    client = llm_decision.get_client()
    provider = os.environ.get("LLM_PROVIDER", "deepseek")
    model = os.environ.get("LLM_MODEL", "deepseek-chat")

    for i in range(attempts):
        payload = llm_decision.build_payload(
            feat, target, duration_s, ratio, history,
            attempts_left=attempts - i, video_id=video.stem,
        )
        plan, source, raw = llm_decision.decide(payload, client)
        dst = out_dir / f"{video.stem}_{tag}_a{i}.mp4"
        record: dict = {"attempt": i, "kbps": plan["kbps"], "output": str(dst)}

        try:
            elapsed = encode.two_pass(video, dst, plan["kbps"],
                                      decision.ffmpeg_args(plan),
                                      job_prefix=out_dir / f"{video.stem}_{tag}_a{i}")
        except Exception as exc:  # noqa: BLE001
            record.update(status="encode_failed", error=str(exc)[-500:])
            logs.append(record)
            continue

        actual = dst.stat().st_size if dst.exists() else 0
        ok = bool(actual) and encode.decode_check(dst)
        error = abs(actual - target) / target if target else 1.0
        record.update(
            actual_bytes=actual,
            actual_kbps=round(8 * actual / duration_s / 1000.0, 1),
            rel_error=round(error, 4),
            decode_ok=ok,
            encode_time_s=round(elapsed, 2),
            status="ok" if ok else "decode_failed",
            candidate=f"llm-{source}",
            preset=plan["preset"],
            x264_params=plan["x264_params"],
            reason=plan.get("reason", ""),
        )
        logs.append(record)

        with (config.LOG_DIR / "llm_decisions.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "video_id": video.stem, "ratio": tag, "attempt": i,
                "source": source, "provider": provider, "model": model,
                "payload": payload, "plan": plan, "raw": raw,
            }, ensure_ascii=False) + "\n")

        history.append({"attempt": i, "kbps": plan["kbps"],
                        "actual_bytes": actual, "rel_error": round(error, 4)})
        if best is None or error < best["rel_error"]:
            best = record
        if ok and error <= config.SIZE_TOLERANCE:
            break

    return best, logs


def run_one(video: Path, ratio: float, attempts: int, do_eval: bool,
            baseline: bool = False, policy: str = "rule",
            baseline_gop: int | None = None) -> dict:
    info = probe.describe(video)
    tag = f"{int(round(ratio * 100))}%"
    target = int(info[f"target_bytes_{tag}"])

    initial_kbps = None
    if baseline:
        mode = "baseline" if not baseline_gop else f"baseline-gop{baseline_gop}"
        plans = [decision.baseline_plan(ratio, keyint=baseline_gop)]
        folder = "baseline" if not baseline_gop else f"baseline_gop{baseline_gop}"
        out_root = config.OUT_DIR / video.stem / f"{folder}_{tag}pct"
        per_attempt = attempts
    else:
        mode = "adaptive" if policy == "rule" else f"adaptive-{policy}"
        try:
            feat = features_for(video)
        except Exception as exc:  # noqa: BLE001 - features are optional for a first run
            print(f"[warn] 特征提取失败（{exc}），只用通用候选。")
            feat = {"diff_mean": 0.0, "edge_mean": 0.0}

        plans = decision.adaptive_candidates(feat, ratio)

        out_root = config.OUT_DIR / video.stem / f"{tag}pct"
        per_attempt = min(attempts, 2)

    start = time.perf_counter()
    best = None
    best_metrics: dict = {}
    best_plan = plans[0]
    best_in_budget = False
    logs: list[dict] = []

    if policy == "llm" and not baseline:
        candidate_best, candidate_logs = run_llm_candidate(
            video, ratio, target, float(info["duration_s"]),
            out_root, attempts, feat, tag,
        )
        best, logs = candidate_best, candidate_logs
        if best:
            best_metrics = _evaluate(video, best["output"]) if do_eval else {}
            best_plan = {"name": best.get("candidate", "llm"),
                         "preset": best["preset"],
                         "x264_params": best["x264_params"],
                         "reason": [best.get("reason", "")]}
            best_in_budget = abs(float(best["rel_error"])) <= config.SIZE_TOLERANCE
    else:
        for plan in plans:
            out_dir = out_root if baseline else out_root / plan["name"]
            candidate_best, candidate_logs = encode.encode_to_budget(
                video=video,
                ratio=ratio,
                target_bytes=target,
                duration_s=float(info["duration_s"]),
                out_dir=out_dir,
                extra_args=decision.ffmpeg_args(plan),
                max_attempts=per_attempt,
                initial_kbps=initial_kbps,
            )
            for item in candidate_logs:
                item["candidate"] = plan["name"]
            logs.extend(candidate_logs)
            if not candidate_best:
                continue

            metrics = _evaluate(video, candidate_best["output"]) if do_eval else {}
            in_budget = abs(float(candidate_best.get("rel_error", 1.0))) <= config.SIZE_TOLERANCE
            if best is None:
                best, best_metrics, best_plan = candidate_best, metrics, plan
                best_in_budget = in_budget
            elif in_budget or not best_in_budget:
                if _psnr(metrics) > _psnr(best_metrics) or (in_budget and not best_in_budget):
                    best, best_metrics, best_plan = candidate_best, metrics, plan
                    best_in_budget = in_budget
            if baseline:
                break

    elapsed = time.perf_counter() - start
    row = {
        "mode": mode,
        "video_id": info["video_id"],
        "ratio": tag,
        "target_bytes": target,
        "target_kbps": info[f"target_kbps_{tag}"],
        "actual_bytes": best["actual_bytes"] if best else 0,
        "actual_kbps": best["actual_kbps"] if best else 0,
        "rel_error": best["rel_error"] if best else "",
        "attempts": len(logs),
        "decode_ok": best["decode_ok"] if best else False,
        "psnr_y_db": best_metrics.get("psnr_y_db", ""),
        "ms_ssim": best_metrics.get("ms_ssim", ""),
        "encode_time_s": round(sum(x.get("encode_time_s", 0) for x in logs), 2),
        "total_time_s": round(elapsed, 2),
        "preset": best_plan["preset"],
        "x264_params": json.dumps(best_plan["x264_params"], separators=(",", ":")),
        "output": best["output"] if best else "",
        "reason": " | ".join(best_plan["reason"]),
    }
    if not baseline:
        row["candidate"] = best_plan["name"]
    elif baseline_gop:
        row["keyint"] = baseline_gop

    suffix = "baseline" if not baseline_gop else f"baseline_gop{baseline_gop}"
    if not baseline:
        suffix = "adaptive"
    log_path = config.LOG_DIR / f"{video.stem}_{tag}_{suffix}_attempts.jsonl"
    log_path.write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in logs) + "\n",
        encoding="utf-8",
    )
    if baseline:
        csv_name = "baseline.csv" if not baseline_gop else f"baseline_gop{baseline_gop}.csv"
    else:
        csv_name = "results.csv"
    append_result(config.LOG_DIR / csv_name, row)
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
    parser.add_argument("--baseline", action="store_true",
                        help="跑统一基线（固定 preset，不做内容自适应）")
    parser.add_argument("--baseline-gop", type=int, default=None,
                        help="基线固定关键帧间隔，例如 60；不填则用 x264 默认")
    parser.add_argument("--policy", choices=["rule", "llm"], default="rule",
                        help="参数决策方式：rule=规则+候选搜索，llm=大模型输出参数")
    args = parser.parse_args()

    config.ensure_dirs()
    if args.policy == "llm":
        try:
            llm_decision.get_client()
        except Exception as exc:  # noqa: BLE001
            print(f"LLM policy requested but client is unavailable: {exc}")
            return
    ratios = [args.ratio] if args.ratio else args.ratios
    videos = args.video or discover(args.split)
    if not videos:
        print("没有找到视频，请检查 data/ 目录结构。")
        return

    for video in videos:
        for ratio in ratios:
            print(f"\n=== {video.name} @ {ratio:.0%} "
                  f"({'baseline' if args.baseline else args.policy}) ===")
            run_one(video, ratio, args.attempts, not args.no_eval,
                    args.baseline, args.policy, args.baseline_gop)


if __name__ == "__main__":
    main()
