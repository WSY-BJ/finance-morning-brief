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

def blocks(page_id: str) -> list[dict]:
    return next((page.get("blocks", []) for page in report.get("pages", []) if page.get("id") == page_id), [])


def short(value: str, limit: int) -> str:
    value = " ".join(str(value).split())
    return value if len(value) <= limit else value[:limit - 1] + "…"


# A usable text edition stays in the message when an in-app browser cannot open Pages.
lines = [f"【{'测试 · ' if test_mode else ''}自动晨报】{today}", summary, "", "关键指标（值、观测日、上次变化）："]
for item in blocks("markets"):
    if item.get("type") == "explainer":
        lines.append("• " + short(item.get("title", "") + "：" + item.get("summary", "") + " " + (item.get("paragraphs") or [""])[0], 125))
lines += ["", "过去 24 小时财经新闻："]
news = [item for item in blocks("news") if item.get("type") == "explainer"]
lines += ["• " + short(item.get("summary", ""), 120) for item in news[:10]] or ["• 本期可核实新闻不足，请勿将空白当作没有事件。"]
lines += ["", "产业利润线索："]
radar = [item for item in blocks("radar") if item.get("type") == "explainer"]
lines += ["• " + short(item.get("title", "") + "：" + (item.get("paragraphs") or [""])[1], 175) for item in radar[:4]] or ["• 本期线索不足，未填充未经验证的结论。"]
lines += ["", "完整因果、原文来源和历史归档：", f"[打开 {today} 晨报]({daily_url})", daily_url]
desp = "\n\n".join(lines)
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
