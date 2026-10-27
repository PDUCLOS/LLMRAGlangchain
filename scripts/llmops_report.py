"""Génère le tableau de bord HTML LLMOps à partir de data/llmops/report.json.

Usage : python scripts/llmops_report.py [--report ...] [--tests ...] [--out ...]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = Path(__file__).with_name("llmops_report_template.html")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default=str(ROOT / "data" / "llmops" / "report.json"))
    parser.add_argument("--extra", default=str(ROOT / "data" / "llmops" / "context.json"))
    parser.add_argument("--out", default=str(ROOT / "data" / "llmops" / "llmops_dashboard.html"))
    args = parser.parse_args()

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    extra_path = Path(args.extra)
    report["context"] = (
        json.loads(extra_path.read_text(encoding="utf-8")) if extra_path.exists() else {}
    )
    payload = json.dumps(report, ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8").replace("/*__DATA__*/null", payload)
    Path(args.out).write_text(html, encoding="utf-8")
    print(f"Tableau de bord : {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
