#!/usr/bin/env python3
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sendkey = os.environ.get("SERVERCHAN_SENDKEY", "").strip()
site_url = os.environ["SITE_URL"].rstrip("/") + "/"
if not sendkey:
    raise SystemExit("SERVERCHAN_SENDKEY is not configured; notification not sent")
if not sendkey.startswith("SCT"):
    raise SystemExit("Expected a ServerChan Turbo SendKey beginning with SCT")
report = json.loads((ROOT / "report.json").read_text(encoding="utf-8"))
today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
if report.get("reportDate") != today:
    raise SystemExit("Local report is not today's Beijing edition; notification blocked")
receipt = ROOT / ".state" / "notifications" / f"{today}.json"
test_mode = os.environ.get("SERVERCHAN_TEST") == "1"
if not test_mode and (not receipt.exists() or json.loads(receipt.read_text(encoding="utf-8")).get("status") != "pending"):
    raise SystemExit("Notification claim missing; notification blocked")
title = report["notification"]["title"].replace("\n", " ")[:32]
if test_mode:
    title = "【测试】" + title
summary = report["notification"]["summary"]
daily_url = f"{site_url}?date={today}#overview"
desp = f"【自动晨报】{summary}\n\n[点击阅读 {today} 晨报]({daily_url})\n\n{daily_url}"
endpoint = f"https://sctapi.ftqq.com/{sendkey}.send"
payload = urllib.parse.urlencode({"title": title, "desp": desp}).encode("utf-8")
request = urllib.request.Request(endpoint, data=payload, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded; charset=utf-8", "User-Agent": "finance-morning-brief/1.0"})
def record(status: str) -> None:
    if not test_mode:
        receipt.write_text(json.dumps({"date": today, "status": status, "delivery": "unverified"}, ensure_ascii=False) + "\n", encoding="utf-8")

try:
    with urllib.request.urlopen(request, timeout=20) as response:
        result = json.loads(response.read().decode("utf-8"))
except Exception as exc:
    record("request_unknown")
    raise SystemExit(f"API request failed ({type(exc).__name__}); delivery state unknown, claim retained")
if result.get("code") != 0:
    record("rejected")
    raise SystemExit(f"ServerChan rejected notification: code={result.get('code')}; claim retained")
data = result.get("data") if isinstance(result.get("data"), dict) else {}
pushid = data.get("pushid", result.get("pushid"))
readkey = data.get("readkey", result.get("readkey"))
print(f"ServerChan {'TEST' if test_mode else 'daily'} accepted: code=0, pushid={pushid if pushid is not None else 'absent'}, readkey_present={bool(readkey)}; WeChat delivery unverified")
if not test_mode:
    receipt.write_text(json.dumps({"date": today, "status": "accepted", "acceptedAt": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"), "delivery": "unverified"}, ensure_ascii=False) + "\n", encoding="utf-8")
