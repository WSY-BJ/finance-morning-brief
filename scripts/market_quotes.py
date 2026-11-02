#!/usr/bin/env python3
"""Free, timestamp-checked A-share / ETF quote snapshot. No third-party dependencies.

Tencent and Sina quote services are undocumented public endpoints, not licensed
exchange feeds. This snapshot must never be described as tick-by-tick real time.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone, time as clocktime
from pathlib import Path
from urllib.request import Request, urlopen

BJT = timezone(timedelta(hours=8))
WATCHLIST = (
    "sz159562",  # user's gold-equity ETF
    "sh518880",  # gold ETF
    "sh000001",  # SSE Composite
    "sh000300",  # CSI 300
    "sz399001",  # SZSE Component
    "sz399006",  # ChiNext
    "sh510300",  # CSI 300 ETF
    "sh512800",  # bank ETF
    "sh515080",  # dividend ETF
    "sh512480",  # semiconductor ETF
    "sh588000",  # STAR 50 ETF
    "sh561980",  # semiconductor equipment ETF
    "sh563300",  # broad A-share ETF, resolve name from quote
)
ROOT = Path(__file__).resolve().parent.parent
MARKET_DIR = ROOT / "market"
TENCENT_RE = re.compile(r'v_((?:sh|sz)\d{6})="([^"]*)"')
SINA_RE = re.compile(r'var\s+hq_str_((?:sh|sz)\d{6})="([^"]*)"')
MAX_FUTURE_SECONDS = 300
CURRENT_MAX_AGE_SECONDS = 900
SOURCE_COMPARISON_MAX_GAP_SECONDS = 600


def _float(value):
    try:
        x = float(value)
        if x != x or abs(x) == float("inf"):
            return None
        return x
    except (ValueError, TypeError):
        return None


def _quote_time(value, fmt):
    try:
        return datetime.strptime(value.strip(), fmt).replace(tzinfo=BJT)
    except (ValueError, AttributeError):
        return None


def _http(url, referer):
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; MarketSnapshot/1.0)",
        "Referer": referer,
        "Accept": "*/*",
    })
    with urlopen(req, timeout=12) as response:
        if response.status != 200:
            raise ValueError("HTTP " + str(response.status))
        return response.read(180_000).decode("gb18030", errors="replace")


def parse_tencent(payload):
    """Tencent fields: 3 current, 4 prev, 5 open, 30 time, 32 pct, 33/34 high/low."""
    result = {}
    for match in TENCENT_RE.finditer(payload):
        symbol, raw = match.groups()
        f = raw.split("~")
        if len(f) < 38:
            continue
        price, prev = _float(f[3]), _float(f[4])
        t = _quote_time(f[30], "%Y%m%d%H%M%S")
        if price is None or price <= 0 or prev is None or prev <= 0 or t is None:
            continue
        pct = (price / prev - 1) * 100
        if abs(pct) > 30:  # reject corrupted fields and extreme bad ticks
            continue
        result[symbol] = {
            "symbol": symbol, "name": f[1], "price": price,
            "previous_close": prev, "open": _float(f[5]),
            "high": _float(f[33]) if len(f) > 33 else None,
            "low": _float(f[34]) if len(f) > 34 else None,
            "change_percent": round(pct, 4),
            "volume_lots": _float(f[36]) if len(f) > 36 else None,
            "turnover_cny": round((_float(f[37]) or 0) * 10000, 2),
            "quote_time": t.isoformat(timespec="seconds"),
            "source": "tencent",
        }
    return result


def parse_sina(payload):
    """Sina standard A-share/ETF quote: 1 open, 2 prev, 3 latest, 30 date, 31 time."""
    result = {}
    for match in SINA_RE.finditer(payload):
        symbol, raw = match.groups()
        f = raw.split(",")
        if len(f) < 32:
            continue
        price, prev = _float(f[3]), _float(f[2])
        t = _quote_time(f[30].strip() + " " + f[31].strip(), "%Y-%m-%d %H:%M:%S")
        if price is None or price <= 0 or prev is None or prev <= 0 or t is None:
            continue
        pct = (price / prev - 1) * 100
        if abs(pct) > 30:
            continue
        result[symbol] = {
            "symbol": symbol, "name": f[0], "price": price,
            "previous_close": prev, "open": _float(f[1]),
            "high": _float(f[4]), "low": _float(f[5]),
            "change_percent": round(pct, 4),
            "volume_lots": round((_float(f[8]) or 0) / 100, 2),
            "turnover_cny": _float(f[9]),
            "quote_time": t.isoformat(timespec="seconds"),
            "source": "sina",
        }
    return result


def classify_time(now):
    """Clock phase only. Exchange holidays are detected from old source timestamps."""
    if now.weekday() >= 5:
        return "weekend"
    tm = now.time()
    if clocktime(9, 30) <= tm <= clocktime(11, 30) or clocktime(13) <= tm <= clocktime(15):
        return "possible_trading_session"
    if clocktime(9, 15) <= tm < clocktime(9, 30):
        return "preopen"
    if clocktime(11, 30) < tm < clocktime(13):
        return "lunch_break"
    return "outside_session"


def combine_quotes(primary, secondary, now):
    quotes, issues = [], []
    for symbol in WATCHLIST:
        a = primary.get(symbol)
        b = secondary.get(symbol)
        candidates = []
        for q in (a, b):
            if q is None:
                continue
            t = datetime.fromisoformat(q["quote_time"])
            age = (now - t).total_seconds()
            if age < -MAX_FUTURE_SECONDS:
                issues.append(symbol + ": impossible future quote from " + q["source"])
                continue
            candidates.append((q, age))
        if not candidates:
            issues.append(symbol + ": no valid quote")
            continue
        # Pick the most recent quote. When equal, prefer Tencent.
        candidates.sort(key=lambda x: (x[1], 0 if x[0]["source"] == "tencent" else 1))
        chosen, age = candidates[0]
        quality = "single_source"
        comparison = None
        if len(candidates) == 2:
            other, other_age = candidates[1]
            gap = abs(age - other_age)
            diff = abs(chosen["price"] - other["price"])
            tolerance = max(0.01, chosen["price"] * 0.003)
            if gap <= SOURCE_COMPARISON_MAX_GAP_SECONDS:
                if diff > tolerance:
                    quality = "conflict"
                    comparison = {"source": other["source"], "price": other["price"],
                                  "quote_time": other["quote_time"]}
                    issues.append(symbol + ": sources disagree; not a verified price")
                else:
                    quality = "cross_checked"
            else:
                comparison = {"status": "secondary_too_old", "source": other["source"]}
        # Do not turn stale quotes into fake live prices.
        if age > CURRENT_MAX_AGE_SECONDS and classify_time(now) == "possible_trading_session":
            quality = "stale" if quality != "conflict" else "conflict_and_stale"
            issues.append(symbol + ": quote older than 15 minutes during session")
        item = dict(chosen)
        item["age_seconds_at_collection"] = int(age)
        item["quality"] = quality
        if comparison:
            item["comparison"] = comparison
        quotes.append(item)
    return quotes, issues


def collect(now=None, requester=_http):
    now = now or datetime.now(BJT)
    raw = {}
    errors = []
    symbols = ",".join(WATCHLIST)
    for source, url, referer, parser in (
        ("tencent", "https://qt.gtimg.cn/q=" + symbols, "https://gu.qq.com/", parse_tencent),
        ("sina", "https://hq.sinajs.cn/list=" + symbols, "https://finance.sina.com.cn/", parse_sina),
    ):
        try:
            raw[source] = parser(requester(url, referer))
            if not raw[source]:
                errors.append(source + ": response contains no valid quotes")
        except Exception as exc:
            raw[source] = {}
            errors.append(source + ": " + type(exc).__name__ + ": " + str(exc)[:180])
    quotes, issues = combine_quotes(raw["tencent"], raw["sina"], now)
    good = sum(q["quality"] in ("cross_checked", "single_source") for q in quotes)
    health = "ok" if good >= len(WATCHLIST) * .8 else ("partial" if good else "failed")
    status = {
        "schema": "market_status_v1",
        "checked_at_bjt": now.isoformat(timespec="seconds"),
        "phase_by_clock": classify_time(now),
        "health": health,
        "good_quote_count": good,
        "total_symbols": len(WATCHLIST),
        "providers": {name: len(raw[name]) for name in ("tencent", "sina")},
        "errors": errors, "issues": issues[:35],
        "disclaimer": "Free unofficial delayed/approximate quotes, not exchange-authorized realtime feeds.",
    }
    snapshot = {
        "schema": "market_quotes_v1",
        "collected_at_bjt": now.isoformat(timespec="seconds"),
        "market_phase_by_clock": classify_time(now),
        "quality": health,
        "total_symbols": len(WATCHLIST),
        "quotes": quotes,
        "source_urls": ["https://qt.gtimg.cn/", "https://hq.sinajs.cn/"],
        "usage": "Always compare quote_time to the current Asia/Shanghai time before describing as current. Source failures and conflicts are explicit.",
    }
    return snapshot, status


def main():
    MARKET_DIR.mkdir(parents=True, exist_ok=True)
    snapshot, status = collect()
    (MARKET_DIR / "status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Only replace the last successful snapshot when at least one usable price exists.
    if status["good_quote_count"]:
        (MARKET_DIR / "latest.json").write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"health": status["health"], "providers": status["providers"],
                      "good_quotes": status["good_quote_count"],
                      "checked_at_bjt": status["checked_at_bjt"],
                      "errors": status["errors"], "issues": status["issues"][:8]}, ensure_ascii=False))
    if not status["good_quote_count"]:
        print("::error::All current market quote providers failed; keeping previous snapshot untouched.")
        return 2
    if status["health"] != "ok":
        print("::warning::Market quotes partial or stale; check market/status.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
