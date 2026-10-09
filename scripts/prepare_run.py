#!/usr/bin/env python3
"""Decide whether this Beijing edition needs generation or deployment."""
import hashlib
import json
import os
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

root = Path(__file__).resolve().parents[1]
today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
archive = root / "archive" / f"{today}.json"
generate = not archive.exists()
if not generate:
    report = json.loads(archive.read_text(encoding="utf-8"))
    if report.get("reportDate") != today or report.get("status") != "published":
        raise SystemExit("Existing archive has invalid date/status")
    quality = report.get("quality", {})
    # An incomplete edition is not a successful daily run. Retry collection on
    # the next cron, without touching the existing notification claim.
    generate = report.get("generatorVersion") != 3
    if not generate:
        (root / "report.json").write_text(archive.read_text(encoding="utf-8"), encoding="utf-8")

live = False
try:
    url = os.environ["SITE_URL"].rstrip("/") + "/report.json?check=" + str(int(datetime.now().timestamp()))
    with urllib.request.urlopen(urllib.request.Request(url, headers={"Cache-Control": "no-cache"}), timeout=12) as response:
        data = json.load(response)
    live = data == json.loads((root / "report.json").read_text())
    if live:
        for asset in ("app.js", "style.css", "index.html", "archive/index.json"):
            with urllib.request.urlopen(os.environ["SITE_URL"].rstrip("/") + "/" + asset + "?check=" + str(int(datetime.now().timestamp())), timeout=12) as response:
                live = live and hashlib.sha256(response.read()).digest() == hashlib.sha256((root / asset).read_bytes()).digest()
except (OSError, ValueError):
    pass
deploy = generate or not live
with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
    output.write(f"date={today}\ngenerate={str(generate).lower()}\ndeploy={str(deploy).lower()}\n")
print(f"Beijing date {today}; generate={generate}; deploy={deploy}; live_today={live}")
