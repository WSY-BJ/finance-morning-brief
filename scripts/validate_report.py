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
blob = json.dumps(report, ensure_ascii=False).lower()
for forbidden in ("sendkey", "api_key", "authorization", "private holding", "account number"):
    assert forbidden not in blob, f"forbidden field or secret marker: {forbidden}"
for source in report["sources"]:
    assert re.match(r"^https://", source.get("url", "")), "source must use HTTPS"
archive = ROOT / "archive" / f"{today}.json"
assert archive.exists(), "today archive missing"
print(f"Validated {today}: {len(report['pages'])} pages, {len(report['sources'])} sources")
