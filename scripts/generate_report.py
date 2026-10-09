#!/usr/bin/env python3
"""Source-linked public morning brief. Facts and conditional research are kept distinct."""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from article_evidence import retrieve, cnstock_data

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Asia/Shanghai")
UA = "Mozilla/5.0 (compatible; FinanceMorningBrief/2.0; +https://github.com/WSY-BJ/finance-morning-brief)"


def fetch(url: str, timeout: int = 18) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json,text/csv,application/xml,text/xml,*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read(2_000_000).decode("utf-8-sig", errors="replace")


def yahoo(symbol: str, label: str, unit: str) -> dict:
    url = "https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(symbol, safe="") + "?range=10d&interval=1d"
    result = json.loads(fetch(url))["chart"]["result"][0]
    q = result["indicators"]["quote"][0]
    exchange_tz = ZoneInfo(result.get("meta", {}).get("exchangeTimezoneName", "UTC"))
    current_day = datetime.now(exchange_tz).date()
    rows = [(datetime.fromtimestamp(ts, exchange_tz).date().isoformat(), float(v))
            for ts, v in zip(result["timestamp"], q["close"])
            if v is not None and datetime.fromtimestamp(ts, exchange_tz).date() < current_day]
    if len(rows) < 2:
        raise ValueError(f"{label}: insufficient observations")
    (previous_date, previous), (date, value) = rows[-2:]
    return {"label": label, "value": value, "unit": unit, "date": date, "previousDate": previous_date, "previousValue": previous,
            "change": value - previous, "changePct": (value / previous - 1) * 100,
            "source": "https://finance.yahoo.com/quote/" + urllib.parse.quote(symbol, safe="") + "/", "provider": "Yahoo Finance"}


def fred(series: str, label: str, unit: str) -> dict:
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=" + series
    rows = [(r.get("observation_date") or r.get("DATE"), float(r[series])) for r in csv.DictReader(io.StringIO(fetch(url))) if r.get(series, ".") not in (".", "")]
    if len(rows) < 2:
        raise ValueError(f"{series}: insufficient observations")
    (previous_date, previous), (date, value) = rows[-2:]
    return {"label": label, "value": value, "unit": unit, "date": date, "previousDate": previous_date, "previousValue": previous,
            "change": value - previous, "changePct": (value / previous - 1) * 100,
            "source": "https://fred.stlouisfed.org/series/" + series, "provider": "FRED / 原始发布机构"}


def treasury(year_month: str, term: str, label: str) -> dict:
    url = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
           "daily-treasury-rates.csv/all/" + year_month + "?_format=csv&field_tdr_date_value_month=" + year_month
           + "&page=&type=daily_treasury_yield_curve")
    rows = []
    for row in csv.DictReader(io.StringIO(fetch(url))):
        raw = row.get("Date", "")
        if row.get(term) and raw:
            rows.append((datetime.strptime(raw, "%m/%d/%Y").date().isoformat(), float(row[term])))
    rows.sort()
    if len(rows) < 2:
        raise ValueError("Treasury CSV has insufficient observations")
    (previous_date, previous), (date, value) = rows[-2:]
    return {"label": label, "value": value, "unit": "%", "date": date, "previousDate": previous_date, "previousValue": previous,
            "change": value - previous, "changePct": (value / previous - 1) * 100,
            "source": "https://home.treasury.gov/resource-center/data-chart-center/interest-rates", "provider": "美国财政部"}


def best_yield(series: str, term: str, label: str) -> dict:
    today = datetime.now(TZ).date()
    try:
        direct = treasury(today.strftime("%Y%m"), term, label)
        if (today - datetime.fromisoformat(direct["date"]).date()).days <= 4:
            return direct
    except (ValueError, KeyError, OSError):
        pass
    return fred(series, label, "%")


def brent() -> dict:
    try:
        item = fred("DCOILBRENTEU", "Brent 原油现货", "美元/桶")
        if (datetime.now(TZ).date() - datetime.fromisoformat(item["date"]).date()).days <= 4:
            return item
    except (ValueError, KeyError, OSError):
        pass
    # BZ=F is a Brent futures price, clearly labeled rather than called spot.
    return yahoo("BZ=F", "Brent 原油期货", "美元/桶")


def spot_gold() -> dict:
    end = datetime.now(TZ).date()
    url = "https://stooq.com/q/d/l/?" + urllib.parse.urlencode({"s": "xauusd", "d1": (end - timedelta(days=15)).strftime("%Y%m%d"), "d2": end.strftime("%Y%m%d"), "i": "d"})
    try:
        rows = [(r["Date"], float(r["Close"])) for r in csv.DictReader(io.StringIO(fetch(url))) if r.get("Close") not in (None, "", "N/D")]
    except (ValueError, KeyError):
        rows = []
    if len(rows) < 2:
        try:
            raise ValueError("No comparable daily spot closes available")
        except (ValueError, KeyError, OSError):
            return yahoo("XAUUSD=X", "现货黄金 XAU/USD", "美元/盎司")
    (previous_date, previous), (date, value) = rows[-2:]
    return {"label": "现货黄金 XAU/USD", "value": value, "unit": "美元/盎司", "date": date, "previousDate": previous_date, "previousValue": previous,
            "change": value - previous, "changePct": (value / previous - 1) * 100,
            "source": "https://stooq.com/q/?s=xauusd", "provider": "Stooq"}


INDICATORS = [
    ("brent", brent),
    ("us2y", lambda: best_yield("DGS2", "2 Yr", "美国 2 年期国债收益率")),
    ("us10y", lambda: best_yield("DGS10", "10 Yr", "美国 10 年期国债收益率")),
    ("dxy", lambda: yahoo("DX-Y.NYB", "美元指数 DXY", "点")),
    ("gold", spot_gold),
    ("sp500", lambda: yahoo("^GSPC", "标普 500 指数", "点")),
    ("nasdaq", lambda: yahoo("^IXIC", "纳斯达克综合指数", "点")),
    ("usdcny", lambda: yahoo("CNY=X", "美元兑人民币", "人民币/美元")),
]


def collect_indicators() -> tuple[dict, dict]:
    found, failures = {}, {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(fn): key for key, fn in INDICATORS}
        for future in as_completed(futures):
            key = futures[future]
            try:
                found[key] = future.result()
            except Exception as exc:
                failures[key] = type(exc).__name__
    if len(found) < 5 or not ({"brent", "gold"} & found.keys()) or not ({"us2y", "us10y"} & found.keys()):
        raise RuntimeError("Fewer than five real indicators or essential commodity/yield data missing: " + str(failures))
    return found, failures


# No headline-to-sector inference and no automatic company recommendations.
# A reviewed edition may be provided in editorial/YYYY-MM-DD.json. The review
# gate below checks provenance; semantic review is still a human responsibility.
import html
import hashlib

VERSION = 3
CHINESE_QUERIES = [
    "site:news.cn 经济 财经 when:1d", "site:cnstock.com 公司 公告 when:1d",
    "site:stcn.com 财经 产业 when:1d", "site:gov.cn 经济 政策 when:1d",
]
FEEDS = [("中文新闻索引", "https://news.google.com/rss/search?" + urllib.parse.urlencode(
    {"q": q, "hl": "zh-CN", "gl": "CN", "ceid": "CN:zh-Hans"})) for q in CHINESE_QUERIES]
TRUSTED = re.compile(r"新华社|新华网|中国政府网|证券时报|上海证券报|中国证券网")


def plain(value):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", value or "")).split())


def parse_feed(name, url):
    items = []
    for el in ET.fromstring(fetch(url)).findall(".//item"):
        try:
            published = parsedate_to_datetime(el.findtext("pubDate") or "")
            if published.tzinfo is None:
                continue
            publisher = el.findtext("source") or name
            title = plain(el.findtext("title"))
            link = el.findtext("link") or ""
            # Index descriptions often only repeat the title. They are not article bodies.
            if TRUSTED.search(publisher) and re.search(r"[\u4e00-\u9fff]", title) and link.startswith("https://"):
                items.append({"event": title, "published": published.isoformat(),
                              "publisher": publisher, "url": link, "evidenceLevel": "headline-only",
                              "originalTitle": title})
        except (ValueError, TypeError):
            continue
    return items


def select_facts(items, now):
    selected, seen = [], set()
    for item in sorted(items, key=lambda n: n["published"], reverse=True):
        date = datetime.fromisoformat(item["published"])
        key = re.sub(r"\W+", "", item["event"]).lower()
        if date.tzinfo is None or not now - timedelta(hours=24) <= date <= now:
            continue
        if key in seen or item["url"] in seen:
            continue
        seen.update((key, item["url"]))
        selected.append(item)
    return selected[:10]


def collect_news(now):
    items, errors = [], []
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(parse_feed, name, url): name for name, url in FEEDS}
        jobs[pool.submit(collect_cnstock, now)] = '中国证券网原文'
        for job in as_completed(jobs):
            try:
                items.extend(job.result())
            except Exception as exc:
                errors.append(jobs[job] + ": " + type(exc).__name__)
    return enrich_news(select_facts(items, now), now, errors), errors


def collect_cnstock(now):
    home = fetch('https://www.cnstock.com/')
    paths = list(dict.fromkeys(re.findall(r'href="(/commonDetail/\d+)"', home)))[:12]
    def article(path):
        url = 'https://www.cnstock.com' + path
        data = cnstock_data(fetch(url))
        published = datetime.strptime(data['pubTime'], '%Y-%m-%d %H:%M').replace(tzinfo=TZ)
        if not now - timedelta(hours=24) <= published <= now:
            return None
        title = plain(data['title'])
        return {'event': title, 'originalTitle': title, 'published': published.isoformat(),
                'publisher': data.get('source') or '中国证券网', 'url': url, 'evidenceLevel': 'headline-only'}
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = []
        for job in as_completed([pool.submit(article, path) for path in paths]):
            try:
                item = job.result()
                if item:
                    results.append(item)
            except (ValueError, KeyError, OSError):
                continue
    return results


def enrich_news(news, now, errors):
    enriched = list(news)
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(retrieve, item, now): i for i, item in enumerate(news)}
        for job in as_completed(jobs):
            try:
                enriched[jobs[job]] = job.result()
            except Exception as exc:
                errors.append('article: ' + type(exc).__name__)
    return enriched


def load_editorial(now):
    path = ROOT / "editorial" / (now.date().isoformat() + ".json")
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["reportDate"] == now.date().isoformat()
    assert data["reviewMode"] in ("headline-translation", "source-reviewed")
    return data


def validate_event(n, now):
    assert re.search(r"[\u4e00-\u9fff]", n["event"]), "Chinese event title required"
    date = datetime.fromisoformat(n["published"])
    assert date.tzinfo and now - timedelta(hours=24) <= date <= now, "news outside 24h window"
    assert n["url"].startswith("https://") and n.get("originalTitle")
    if n.get("evidenceLevel") == "source-reviewed":
        evidence = n.get("evidence", [])
        assert evidence, "analysis needs article evidence"
        for e in evidence:
            assert e["url"].startswith("https://") and e.get("excerpt") and e.get("retrievedAt")
        assert n.get("facts") and n.get("analysis") and n.get("verify") and n.get("invalidate")
        for company in n.get("companies", []):
            assert company.get("relationship") and company.get("evidenceIndex") in range(len(evidence))
    else:
        assert n.get("evidenceLevel") == "headline-only"
        assert not any(n.get(k) for k in ("analysis", "companies", "profitLead")), "headline-only cannot support profit analysis"


def block(title, summary, paragraphs=(), links=()):
    return {"type": "explainer", "title": title, "summary": summary,
            "paragraphs": list(paragraphs), "links": list(links)}


def notice(title, text):
    return {"type": "notice", "tone": "warning", "title": title, "text": text}


def indicator_block(key, item):
    previous = item.get("previousValue", item["value"] - item["change"])
    digits = 4 if key == "usdcny" else 2
    movement = f"{item['change']:+.{digits}f}" + (" 个百分点" if key in ("us2y", "us10y") else " " + item["unit"])
    return block(item["label"], f"{item['value']:,.{digits}f} {item['unit']}；变化 {movement}",
                 [f"观测日 {item['date']}；前值 {previous:,.{digits}f}（{item['previousDate']}）；来源：{item['provider']}。"],
                 [{"title": "原始数据与口径", "url": item["source"]}])


CURRICULUM = [
    ("绝对变化与收益率", "收益率 = (新值 ÷ 前值 − 1) × 100%。金额变化和百分比变化回答不同问题。", "100 元涨到 110 元，收益率是 10%；再跌回 100 元，跌幅是 9.09%。"),
    ("百分点与基点", "利率从 4% 到 4.1%，增加 0.1 个百分点，即 10 个基点；不是只增加 0.1%。", "1 个基点 = 0.01 个百分点。对照本期国债收益率的前值和变化。"),
    ("汇率的报价方向", "美元兑人民币上升表示一美元兑换更多人民币；美元收入和美元采购成本的影响相反。", "美元收入 100 万，汇率从 7 到 7.1，未套保人民币收入增加 10 万。"),
    ("简单收益率与复利", "多期收益需要连乘，不能直接相加。累计收益 = 各期(1+收益率)连乘 − 1。", "先涨 10% 再跌 10%，100 元变成 99 元。"),
    ("对数收益率", "对数收益率 = ln(新值/前值)。跨期可相加，但不是账户实际盈亏百分比。", "把本期指数的前值和现值代入；对数收益率与简单收益率在小变动时接近。"),
    ("折现与现值", "现值 = 未来现金流 ÷ (1+折现率)^期数。利率变化和盈利变化应分开分析。", "一年后 110 元，以 10% 折现得到 100 元。"),
    ("债券价格与收益率", "固定现金流不变时，市场要求的收益率上升，债券价格下降。", "国债收益率的上涨不是持有旧债券的价格收益。"),
    ("久期", "修正久期近似衡量利率敏感度：价格变化率 ≈ −修正久期 × 收益率变化。", "久期 5，收益率上升 0.01，债券价格约跌 5%；大幅变化需考虑凸性。"),
    ("波动率", "波动率是收益率的标准差，需多期数据；单日涨跌无法给出可靠波动率。", "日波动年化常乘 √252，这依赖交易日及收益独立等假设。"),
    ("相关性与因果", "两个价格同涨不证明互相导致；共同利率冲击或样本选择也能产生相关性。", "本期油价与股指的方向可作观察，但标题不能证明因果。"),
    ("协方差与分散化", "组合风险取决于单项波动和共同变动；持有多个高相关资产未必分散风险。", "两资产方差含 2w₁w₂Cov 项，需要同频、同日收益样本。"),
    ("套期保值与基差", "期货和现货不是同一个价格；两者之差叫基差，套保仍可能有基差风险。", "本期 Brent 若为期货，就不能与昨天现货拼接计算涨跌。"),
    ("现金流与会计利润", "宣布投资先形成支出，订单、交付、收入确认和回款是不同阶段。", "裁员消息不等于其他企业的设备订单增长；需要独立订单证据。"),
    ("情景分析", "把销量、价格和成本分别改变，计算利润敏感度，而非给一个无条件预测。", "利润近似 = 销量 × (售价 − 单位变动成本) − 固定成本。"),
]


def lesson(indicators, now):
    day = max(0, (now.date() - datetime(2026, 10, 9).date()).days)
    topic, explanation, exercise = CURRICULUM[min(day, len(CURRICULUM)-1)]
    key = "usdcny" if day == 2 else "us10y" if day in (1, 5, 6, 7) else "sp500"
    key = key if key in indicators else next(iter(indicators))
    q = indicators[key]
    example = f"本期实例：{q['label']}，{q['previousDate']} 前值 {q.get('previousValue', q['value']-q['change']):.4f}，{q['date']} 现值 {q['value']:.4f}，变化 {q['change']:+.4f}。"
    return {"id": "lesson", "eyebrow": "05 · 每日一课", "title": f"第 {day+1} 课：{topic}",
            "lead": "按日期推进；先认识数据，再学习定价和风险。",
            "blocks": [block(topic, explanation, [example, exercise])]}


def build_report(indicators, failures, news, news_errors, now, editorial=None):
    now = now.astimezone(TZ)
    today = now.date().isoformat()
    for n in news:
        validate_event(n, now)
    reviewed = [n for n in news if n["evidenceLevel"] == "source-reviewed"]
    radar_events = [n for n in reviewed if n.get("profitLead")][:4]
    news_blocks = []
    for n in news:
        paragraphs = [f"发布时间：{n['published']}；来源：{n['publisher']}。"]
        if n.get('articleEvidence') and n not in reviewed:
            paragraphs.append('原文摘要：' + n['articleEvidence']['excerpt'])
        if n in reviewed:
            paragraphs += ["事实：" + n["facts"], "传导分析（假设）：" + n["analysis"],
                           "持续时间：" + n.get("horizon", "未确定"), "反证：" + n["invalidate"], "验证：" + n["verify"]]
            paragraphs += [c["name"] + "：" + c["relationship"] for c in n.get("companies", [])]
        news_blocks.append(block(n["event"], n.get("facts", ""), paragraphs,
                                 [{"title": "新闻来源", "url": n["url"]}]))
    limited = len(reviewed) < 6 or len(radar_events) < 2
    radar = [block(n["event"], n["facts"], ["利润假设：" + n["analysis"], "反证：" + n["invalidate"], "验证：" + n["verify"]],
                   [{"title": "支持证据", "url": n["url"]}]) for n in radar_events]
    if not radar:
        radar = [block("今日线索", "今日暂无新增线索。")]
    overview = editorial.get("mainlines", []) if editorial and editorial.get("reviewMode") == "source-reviewed" else []
    if not overview:
        overview = [block(v["label"], f"{v['date']}：{v['value']:,.2f} {v['unit']}；较 {v['previousDate']} 变化 {v['change']:+.2f} {('个百分点' if k in ('us2y','us10y') else v['unit'])}。", links=[{"title": "数据来源", "url": v["source"]}]) for k, v in indicators.items() if k in ("us10y", "brent", "sp500")]
    markets = [indicator_block(k, indicators[k]) for k, _ in INDICATORS if k in indicators]
    stale = [k for k, v in indicators.items() if (now.date()-datetime.fromisoformat(v["date"]).date()).days > 4]
    if stale or failures:
        markets.append(notice("数据缺口", "滞后：" + "、".join(stale) + "；缺失：" + "、".join(failures)))
    observation = [n["verify"] for n in reviewed][:5]
    if not observation:
        observation = ["核对同一交易日的 2 年与 10 年美债收益率：区分短期政策预期和长期资金价格。",
                       "核对原油同一合约的前后价格与库存数据：判断价格变化是否有供需证据。",
                       "核对企业公告中的订单金额、交付时间和现金回款，观察收入确认能否转化为经营现金流。"]
    pages = [
        {"id": "overview", "eyebrow": "01 · 市场主线", "title": "今天最重要的市场主线", "lead": "", "blocks": overview},
        {"id": "markets", "eyebrow": "02 · 市场数据", "title": "关键市场数据", "lead": "逐项提供日期、前值、变化和来源；期货与现货分开。", "blocks": markets},
        {"id": "news", "eyebrow": "03 · 财经新闻", "title": "过去 24 小时财经新闻", "lead": "", "blocks": news_blocks},
        {"id": "radar", "eyebrow": "04 · 产业研究", "title": "产业利润增长雷达", "lead": "", "blocks": radar},
        lesson(indicators, now),
        {"id": "watch", "eyebrow": "06 · 下一步", "title": "接下来重点观察什么", "lead": "用数据检验判断。", "blocks": [{"type": "bullets", "items": observation}]},
    ]
    sources = [{"title": v["label"] + " · " + v["provider"], "url": v["source"], "asOf": v["date"]} for v in indicators.values()]
    sources += [{"title": n["event"], "url": n["url"], "asOf": n["published"]} for n in news]
    summary = f"{len(indicators)} 项市场数据 · {len(news)} 条财经消息"
    return {"edition": f"财经晨报 · {today}", "date": f"更新于北京时间 {now:%Y-%m-%d %H:%M}", "reportDate": today,
            "updatedAt": now.isoformat(timespec="seconds"), "status": "published", "generatorVersion": VERSION,
            "title": "财经晨报", "subtitle": "市场数据 · 中文新闻 · 企业利润 · 每日一课",
            "intro": summary, "notification": {"title": today + " 财经晨报", "summary": summary},
            "pages": pages, "sources": sources, "events": news,
            "quality": {"mode": "limited" if limited else "research", "indicatorCount": len(indicators), "news24hCount": len(news),
                        "reviewedNewsCount": len(reviewed), "radarCount": len(radar_events), "staleIndicators": stale,
                        "unavailableIndicators": list(failures), "unavailableNewsSources": news_errors}}


def write_outputs(report: dict) -> None:
    archive_dir = ROOT / "archive"
    archive_dir.mkdir(exist_ok=True)
    date = report["reportDate"]
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    (ROOT / "report.json").write_text(encoded, encoding="utf-8")
    (archive_dir / f"{date}.json").write_text(encoded, encoding="utf-8")
    index_path = archive_dir / "index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        index = {"items": []}
    entry = {"date": date, "title": report["title"], "summary": report["notification"]["summary"], "url": f"?date={date}#overview"}
    items = sorted([entry] + [x for x in index.get("items", []) if x.get("date") != date], key=lambda x: x.get("date", ""), reverse=True)
    index_path.write_text(json.dumps({"updatedAt": report["updatedAt"], "items": items}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true", help="Write preview/YYYY-MM-DD.json without changing published report or archive")
    args = parser.parse_args()
    now = datetime.now(TZ)
    indicators, failures = collect_indicators()
    news, errors = collect_news(now)
    editorial = load_editorial(now)
    if editorial:
        news = enrich_news(editorial.get("events", []), now, errors)
    report = build_report(indicators, failures, news, errors, now, editorial)
    if args.preview:
        folder = ROOT / "preview"
        folder.mkdir(exist_ok=True)
        report["status"] = "preview"
        (folder / f"{report['reportDate']}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        write_outputs(report)
    print("Generated", report["reportDate"], report["quality"])


if __name__ == "__main__":
    main()
