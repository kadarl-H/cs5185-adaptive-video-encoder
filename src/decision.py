"""Rule-based mapping from content features to x264 parameters.

Keep this small and explainable; replace or extend it with search / a model / an LLM.
Every returned plan carries a ``reason`` so the report can trace decisions.
"""
from __future__ import annotations

# 经验阈值（在开发集上校准后请更新，并写进报告）
HIGH_MOTION_DIFF = 6.0      # 平均帧差
HIGH_DETAIL_EDGE = 0.12     # 平均边缘像素占比


def choose(feature_summary: dict, ratio: float) -> dict:
    """Return x264 parameters plus an explanation."""
    motion = feature_summary.get("diff_mean", 0.0)
    detail = feature_summary.get("edge_mean", 0.0)

    high_motion = motion >= HIGH_MOTION_DIFF
    high_detail = detail >= HIGH_DETAIL_EDGE

    plan: dict = {
        "preset": "medium",
        "x264_params": {},
        "keyint": 60,
        "reason": [],
    }

    if high_motion:
        # 运动大：多参考帧 + B 帧有助于预测，但别用太慢的 preset
        plan["x264_params"].update({"refs": 3, "bf": 3, "aq-mode": 2})
        plan["keyint"] = 60
        plan["reason"].append(f"高运动(帧差 {motion:.1f}) → refs=3, bf=3, aq-mode=2")
    else:
        # 静态/幻灯片：长 GOP 更省码率，弱化自适应量化
        plan["x264_params"].update({"refs": 5, "bf": 0, "aq-mode": 1})
        plan["keyint"] = 120
        plan["reason"].append(f"低运动(帧差 {motion:.1f}) → 长 GOP(g=120), refs=5, bf=0")

    if high_detail:
        plan["x264_params"]["aq-strength"] = 1.0
        plan["reason"].append(f"高细节(边缘 {detail:.2f}) → 保留 aq-strength=1.0")
    else:
        plan["x264_params"]["aq-strength"] = 0.8
        plan["reason"].append(f"低细节(边缘 {detail:.2f}) → aq-strength=0.8 省码率")

    if ratio <= 0.02:
        # 2% 档压力大：允许更慢的 preset 换取同码率下更好的质量
        plan["preset"] = "slow"
        plan["reason"].append("2% 目标 → preset=slow")

    return plan


def ffmpeg_args(plan: dict) -> list[str]:
    """Translate a plan into extra FFmpeg arguments."""
    args = ["-preset", plan["preset"], "-g", str(plan["keyint"])]
    params = plan.get("x264_params", {})
    if params:
        joined = ":".join(f"{k}={v}" for k, v in params.items())
        args += ["-x264-params", joined]
    return args
