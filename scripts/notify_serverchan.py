#!/usr/bin/env python3
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sendkey = os.environ.get("SERVERCHAN_SENDKEY", "").strip()
site_url = os.environ["SITE_URL"].rstrip("/") + "/"
if not sendkey:
    raise SystemExit("SERVERCHAN_SENDKEY is not configured; notification not sent")
if not sendkey.startswith("SCT"):
    raise SystemExit("Expected a ServerChan Turbo SendKey beginning with SCT")
report = json.loads((ROOT / "report.json").read_text(encoding="utf-8"))
title = report["notification"]["title"].replace("\n", " ")[:32]
summary = report["notification"]["summary"]
desp = f"{summary}\n\n[点击阅读当天完整晨报]({site_url})\n\n备用入口：{site_url}"
endpoint = f"https://sctapi.ftqq.com/{sendkey}.send"
payload = urllib.parse.urlencode({"title": title, "desp": desp}).encode("utf-8")
request = urllib.request.Request(endpoint, data=payload, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded; charset=utf-8", "User-Agent": "finance-morning-brief/1.0"})
try:
    with urllib.request.urlopen(request, timeout=20) as response:
        result = json.loads(response.read().decode("utf-8"))
except Exception as exc:
    raise SystemExit(f"ServerChan request failed ({type(exc).__name__}); notification not confirmed")
if result.get("code") != 0:
    raise SystemExit(f"ServerChan rejected notification: code={result.get('code')}; message={result.get('message', 'unknown')}")
print("ServerChan accepted one notification (code=0)")
