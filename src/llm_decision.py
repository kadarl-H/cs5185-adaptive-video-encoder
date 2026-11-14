"""Optional LLM-based encoding-parameter decision.

Design goals
------------
* The model only sees numbers (features, budget, allowed values, history).
* Its answer must be strict JSON and is validated before use.
* Any failure (timeout, bad JSON, out-of-range value) falls back to rules.
* Every request/response is logged so a run can be audited.

Offline demo (no API key needed):

    python -m src.llm_decision --demo

Real use:

    set LLM_API_KEY=...
    set LLM_BASE_URL=https://api.deepseek.com
    set LLM_MODEL=deepseek-chat
    python -m src.llm_decision --demo --live
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from typing import Any

ALLOWED = {
    "preset": ["medium", "slow", "veryslow"],
    "g": [30, 60, 120, 250],
    "aq_mode": [1, 2, 3],
    "aq_strength": [0.8, 1.0, 1.2],
    "refs": [1, 3, 5],
    "bf": [0, 2, 3],
}

SYSTEM_PROMPT = """You are a video encoding parameter selector for FFmpeg/libx264.
Given content features, a size budget, the allowed parameter space and the history
of previous attempts, choose the next encoding plan.

Rules:
- Reply with ONE JSON object and nothing else.
- Keys: kbps, preset, g, x264_params, reason.
- kbps must be within allowed.kbps_range.
- preset, g, aq-mode, aq-strength, refs, bf must come from the allowed lists.
- Optimise PSNR-Y at the target size; do not exceed the target by more than 3%.
- If history shows an undershoot, raise kbps; if overshoot, lower it.
- reason: at most 40 words."""


def build_payload(features: dict, target_bytes: int, duration_s: float,
                   ratio: float, history: list[dict], attempts_left: int,
                   video_id: str = "") -> dict:
    target_kbps = 0.98 * 8 * target_bytes / duration_s / 1000
    return {
        "video_id": video_id,
        "duration_s": duration_s,
        "target_bytes": target_bytes,
        "target_kbps": round(target_kbps),
        "ratio": ratio,
        "features": features,
        "allowed": {
            **ALLOWED,
            "kbps_range": [round(target_kbps * 0.5), round(target_kbps * 1.5)],
        },
        "history": history,
        "attempts_left": attempts_left,
    }


def _coerce(text: str):
    """Turn '2' / '1.0' into numbers, leave other strings untouched."""
    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return text


def validate(text: str, payload: dict) -> dict:
    """Parse and validate the model answer; raise ValueError when invalid."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
    obj = json.loads(text)
    allowed = payload["allowed"]

    preset = obj.get("preset")
    if preset not in allowed["preset"]:
        raise ValueError(f"preset not allowed: {preset!r}")

    g = obj.get("g")
    if g not in allowed["g"]:
        raise ValueError(f"g not allowed: {g!r}")

    kbps = int(obj.get("kbps", 0))
    lo, hi = allowed["kbps_range"]
    if kbps <= 0:
        raise ValueError("kbps must be positive")
    kbps = max(lo, min(hi, kbps))

    params = obj.get("x264_params") or {}
    if isinstance(params, str):
        parsed = {}
        for part in params.split(":"):
            part = part.strip()
            if not part:
                continue
            key, _, value = part.partition("=")
            parsed[key.strip().replace("_", "-")] = _coerce(value.strip())
        params = parsed
    if not isinstance(params, dict):
        raise ValueError("x264_params must be an object or a k=v:k=v string")

    mapping = {"aq-mode": "aq_mode", "aq-strength": "aq_strength", "refs": "refs",
               "bf": "bf", "bframes": "bf"}
    clean = {}
    for key, value in params.items():
        key = key.replace("_", "-")
        if key not in mapping:
            raise ValueError(f"unknown x264 param: {key}")
        value = _coerce(str(value))
        if value not in allowed[mapping[key]]:
            raise ValueError(f"{key} not allowed: {value!r}")
        clean[key] = value

    return {
        "kbps": kbps,
        "preset": preset,
        "keyint": g,
        "x264_params": clean,
        "reason": str(obj.get("reason", ""))[:300],
    }


def rule_fallback(features: dict, payload: dict) -> dict:
    """Deterministic fallback when the model is unavailable or invalid."""
    motion = float(features.get("diff_mean", 0))
    detail = float(features.get("edge_mean", 0))
    if motion >= 6.0:
        params = {"aq-mode": 2, "aq-strength": 1.0, "refs": 3, "bf": 3}
        g = 60
    else:
        params = {"aq-mode": 1, "aq-strength": 1.0, "refs": 5, "bf": 0}
        g = 120
    if detail < 0.12:
        params["aq-strength"] = 0.8
    return {
        "kbps": payload["target_kbps"],
        "preset": "medium",
        "keyint": g,
        "x264_params": params,
        "reason": "rule fallback",
    }


class MockClient:
    """Deterministic stand-in for offline demos/tests."""

    def __call__(self, payload: dict) -> str:
        motion = payload["features"].get("diff_mean", 0)
        kbps = payload["target_kbps"]
        if motion >= 6.0:
            plan = {"kbps": kbps, "preset": "medium", "g": 60,
                    "x264_params": {"aq-mode": 2, "aq-strength": 1.0, "refs": 3, "bf": 3},
                    "reason": "high motion: stronger AQ and more references"}
        else:
            plan = {"kbps": kbps, "preset": "medium", "g": 120,
                    "x264_params": {"aq-mode": 1, "aq-strength": 0.8, "refs": 5, "bf": 0},
                    "reason": "low motion: long GOP saves bits"}
        return json.dumps(plan)


class HTTPClient:
    def __init__(self) -> None:
        self.key = os.environ.get("LLM_API_KEY", "")
        self.base = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
        if not self.key:
            raise RuntimeError("LLM_API_KEY is not set")

    def __call__(self, payload: dict) -> str:
        body = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
        }
        req = urllib.request.Request(
            f"{self.base}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.key}"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]


def get_client():
    """Mock client for offline runs, HTTP client otherwise."""
    if os.environ.get("LLM_MOCK") == "1":
        return MockClient()
    return HTTPClient()


def decide(payload: dict, client) -> tuple[dict, str]:
    """Return (plan, source, raw) with bounded retries and a rule fallback."""
    last: Exception | None = None
    for attempt in range(2):
        try:
            raw = client(payload)
            return validate(raw, payload), "llm", raw
        except Exception as exc:  # noqa: BLE001 - any failure must not stop the pipeline
            last = exc
            if attempt == 0:
                time.sleep(0.5)
    print(f"[warn] llm decision failed after retries: {last}; using rules")
    return rule_fallback(payload["features"], payload), "fallback", ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()

    features = {"diff_mean": 17.2, "edge_mean": 0.54, "scene_cuts": 2}
    payload = build_payload(features, target_bytes=4_862_625, duration_s=5.0,
                            ratio=0.05, history=[], attempts_left=2, video_id="07_Mobcal")
    client = HTTPClient() if args.live else MockClient()
    plan, source, _raw = decide(payload, client)
    print("payload:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"\nplan ({source}):")
    print(json.dumps(plan, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
