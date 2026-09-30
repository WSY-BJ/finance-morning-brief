#!/usr/bin/env python3
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
report = json.loads((ROOT / "report.json").read_text(encoding="utf-8"))
today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
assert report.get("reportDate") == today, "report date is not today in Asia/Shanghai"
assert report.get("status") == "published"
assert len(report.get("pages", [])) >= 4
assert len(report.get("sources", [])) >= 4
if report.get("quality"):
    assert report["quality"]["indicatorCount"] >= 5, "too few real market indicators"
    required_pages = {"overview", "markets", "news", "radar", "lesson", "goldminers"}
    assert required_pages.issubset({page.get("id") for page in report["pages"]}), "missing learning or industry section"
    assert 6 <= report["quality"]["news24hCount"] <= 10, "past 24h news must contain 6–10 verified items"
    assert 2 <= report["quality"]["radarCount"] <= 4, "industry radar must contain 2–4 evidence-backed leads"
blob = json.dumps(report, ensure_ascii=False).lower()
for forbidden in ("sendkey", "api_key", "authorization", "private holding", "account number"):
    assert forbidden not in blob, f"forbidden field or secret marker: {forbidden}"
for source in report["sources"]:
    assert re.match(r"^https://", source.get("url", "")), "source must use HTTPS"
archive = ROOT / "archive" / f"{today}.json"
assert archive.exists(), "today archive missing"
print(f"Validated {today}: {len(report['pages'])} pages, {len(report['sources'])} sources")
