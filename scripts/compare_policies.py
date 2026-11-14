"""Compare baseline / rule-search / LLM parameter decisions.

    python -m scripts.compare_policies

Reads:
  logs/baseline.csv            (dev, unified baseline)
  logs/results_rule_backup.csv (dev+test, rule-search run)
  logs/results.csv             (LLM run appended; rows with mode adaptive-llm)
  logs/llm_decisions.jsonl     (fallback counts)
Writes:
  reports/llm_vs_rule.md
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"
REPORTS = ROOT / "reports"


def load(name):
    path = LOGS / name
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def main():
    base = {(r["video_id"], r["ratio"]): r for r in load("baseline.csv")}
    rule = {(r["video_id"], r["ratio"]): r for r in load("results_rule_backup.csv")
            if r.get("mode") == "adaptive"}
    llm_name = sys.argv[1] if len(sys.argv) > 1 else "llm_results.csv"
    llm = {(r["video_id"], r["ratio"]): r for r in load(llm_name)}

    keys = sorted(set(base) & set(rule) & set(llm))
    if not keys:
        print("no overlapping rows")
        return

    rows = []
    for key in keys:
        b, r, l = base[key], rule[key], llm[key]
        rows.append({
            "video": key[0], "ratio": key[1],
            "base": float(b["psnr_y_db"]),
            "rule": float(r["psnr_y_db"]),
            "llm": float(l["psnr_y_db"]),
            "llm_candidate": l.get("candidate", ""),
            "llm_preset": l.get("preset", ""),
            "llm_err": float(l["rel_error"]),
        })

    sources = {}
    if (LOGS / "llm_decisions.jsonl").exists():
        for line in (LOGS / "llm_decisions.jsonl").read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            sources[rec["source"]] = sources.get(rec["source"], 0) + 1

    lines = ["# LLM vs rule-search vs baseline", ""]
    lines.append("| Video | Ratio | Baseline | Rule | LLM | LLM-Rule | LLM candidate | LLM err |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in rows:
        lines.append(
            f"| {r['video']} | {r['ratio']} | {r['base']:.3f} | {r['rule']:.3f} | "
            f"{r['llm']:.3f} | {r['llm'] - r['rule']:+.3f} | {r['llm_candidate']} | {r['llm_err']:.2%} |"
        )

    d = [r["llm"] - r["rule"] for r in rows]
    wins = sum(1 for x in d if x > 0)
    lines += [
        "",
        "## Summary",
        "",
        f"- cases: {len(rows)}",
        f"- mean LLM - rule: {sum(d) / len(d):+.3f} dB",
        f"- LLM better: {wins}/{len(rows)}",
        f"- decision sources: {sources}",
        "",
    ]
    (REPORTS / "llm_vs_rule.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
