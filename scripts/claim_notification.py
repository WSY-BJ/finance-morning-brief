#!/usr/bin/env python3
"""Commit an at-most-once daily claim before contacting ServerChan."""
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

root = Path(__file__).resolve().parents[1]
today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
report = json.loads((root / "report.json").read_text(encoding="utf-8"))
if report.get("reportDate") != today:
    raise SystemExit("Not today's report; cannot claim notification")
path = root / ".state" / "notifications" / f"{today}.json"
if path.exists():
    print(f"Notification already claimed for {today}; no second push")
    claimed = False
else:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"date": today, "status": "pending", "delivery": "unverified"}, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Claimed notification for {today}; commit before API request")
    claimed = True
with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
    output.write(f"claimed={str(claimed).lower()}\n")
