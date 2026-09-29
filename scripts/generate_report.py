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
    rows = [(datetime.fromtimestamp(ts, timezone.utc).date().isoformat(), float(v)) for ts, v in zip(result["timestamp"], q["close"]) if v is not None]
    if len(rows) < 2:
        raise ValueError(f"{label}: insufficient observations")
    (previous_date, previous), (date, value) = rows[-2:]
    return {"label": label, "value": value, "unit": unit, "date": date, "previousDate": previous_date,
            "change": value - previous, "changePct": (value / previous - 1) * 100,
            "source": "https://finance.yahoo.com/quote/" + urllib.parse.quote(symbol, safe="") + "/", "provider": "Yahoo Finance"}


def fred(series: str, label: str, unit: str) -> dict:
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=" + series
    rows = [(r.get("observation_date") or r.get("DATE"), float(r[series])) for r in csv.DictReader(io.StringIO(fetch(url))) if r.get(series, ".") not in (".", "")]
    if len(rows) < 2:
        raise ValueError(f"{series}: insufficient observations")
    (previous_date, previous), (date, value) = rows[-2:]
    return {"label": label, "value": value, "unit": unit, "date": date, "previousDate": previous_date,
            "change": value - previous, "changePct": (value / previous - 1) * 100,
            "source": "https://fred.stlouisfed.org/series/" + series, "provider": "FRED / 原始发布机构"}


def spot_gold() -> dict:
    end = datetime.now(TZ).date()
    url = "https://stooq.com/q/d/l/?" + urllib.parse.urlencode({"s": "xauusd", "d1": (end - timedelta(days=15)).strftime("%Y%m%d"), "d2": end.strftime("%Y%m%d"), "i": "d"})
    try:
        rows = [(r["Date"], float(r["Close"])) for r in csv.DictReader(io.StringIO(fetch(url))) if r.get("Close") not in (None, "", "N/D")]
    except (ValueError, KeyError):
        rows = []
    if len(rows) < 2:
        return yahoo("XAUUSD=X", "现货黄金 XAU/USD", "美元/盎司")
    (previous_date, previous), (date, value) = rows[-2:]
    return {"label": "现货黄金 XAU/USD", "value": value, "unit": "美元/盎司", "date": date, "previousDate": previous_date,
            "change": value - previous, "changePct": (value / previous - 1) * 100,
            "source": "https://stooq.com/q/?s=xauusd", "provider": "Stooq"}


INDICATORS = [
    ("brent", lambda: fred("DCOILBRENTEU", "Brent 原油现货", "美元/桶")),
    ("us2y", lambda: fred("DGS2", "美国 2 年期国债收益率", "%")),
    ("us10y", lambda: fred("DGS10", "美国 10 年期国债收益率", "%")),
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


# Each RSS title is treated only as evidence for the event it actually states.
# Sector and margin effects below are conditional research questions, never asserted outcomes.
TOPICS = [
    ("AI 与半导体", re.compile(r"\b(ai|artificial intelligence|chip|semiconductor|data center|gpu|memory|hbm)\b", re.I),
     "若订单和实际交付增加，芯片、存储、光模块及服务器环节可能先确认收入；电力和制冷订单通常更靠后。云服务还需证明算力支出能转为付费收入。", "季度订单、资本开支、毛利率与云业务收入", "英伟达 NVDA、台积电 TSM、工业富联 601138、阿里巴巴 9988"),
    ("汽车与新能源", re.compile(r"\b(ev|electric vehicle|battery|solar|vehicle|automaker|renewable)\b", re.I),
     "销量增长只有在售价与电池、原料成本相匹配时才改善利润；降价抢份额会挤压整车厂和部分供应商的毛利率。", "交付量、单车售价、库存和电池报价", "比亚迪 002594/1211、特斯拉 TSLA、宁德时代 300750"),
    ("能源与材料", re.compile(r"\b(oil|crude|gas|copper|steel|energy|power|lithium)\b", re.I),
     "原料价格提高上游单位收入，却增加下游采购成本；净利润取决于长协、套期保值、产量和转嫁成本的能力。", "现货与长协价格、库存、产量和下游毛利率", "中国海油 600938/0883、埃克森美孚 XOM、紫金矿业 601899/2899"),
    ("消费与医药", re.compile(r"\b(retail|consumer|drug|pharma|medicine|health|sales)\b", re.I),
     "需求增长可能推高销量，但折扣、渠道费用和研发投入会影响最终利润，不能仅凭销售额判断。", "同店销售、销量、费用率和现金流", "贵州茅台 600519、美团 3690、礼来 LLY"),
    ("贸易与制造", re.compile(r"\b(tariff|trade|export|manufactur|factory|industrial|order)\b", re.I),
     "出口或订单增长可能摊薄固定成本；关税、汇率和海外建厂支出则可能抵消收入增量。", "出口数量、订单积压、关税细则与产能利用率", "美的集团 000333/0300、卡特彼勒 CAT、立讯精密 002475"),
    ("宏观与金融", re.compile(r"\b(fed|central bank|interest rate|inflation|employment|bank|housing|property)\b", re.I),
     "利率或政策变化会影响融资成本和估值；企业盈利是否改善，还需看需求、坏账和真实现金流。", "政策原文、收益率、贷款与财报", "工商银行 601398/1398、摩根大通 JPM、沪深300 ETF 510300"),
]

FEEDS = [
    ("美联储", "https://www.federalreserve.gov/feeds/press_all.xml"),
    ("美国证监会", "https://www.sec.gov/news/pressreleases.rss"),
    ("美国能源信息署", "https://www.eia.gov/rss/todayinenergy.xml"),
    ("欧洲央行", "https://www.ecb.europa.eu/rss/press.html"),
]
NEWS_QUERIES = [
    "business economy central bank inflation when:1d",
    "semiconductor AI capital expenditure earnings when:1d",
    "energy electric vehicle manufacturing trade when:1d",
]


def parse_feed(name: str, url: str) -> list[dict]:
    root = ET.fromstring(fetch(url))
    items = []
    for el in root.findall(".//item"):
        title = " ".join((el.findtext("title") or "").split())
        link = (el.findtext("link") or "").strip()
        raw_date = el.findtext("pubDate") or ""
        try:
            published = parsedate_to_datetime(raw_date).astimezone(timezone.utc)
        except (ValueError, TypeError):
            continue
        if title and link.startswith("https://"):
            source = el.find("source")
            items.append({"title": title, "url": link, "published": published, "publisher": source.text if source is not None and source.text else name})
    return items


def collect_news(now: datetime) -> tuple[list[dict], list[str]]:
    endpoints = FEEDS + [("Google 新闻索引", "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"})) for q in NEWS_QUERIES]
    articles, errors = [], []
    with ThreadPoolExecutor(max_workers=len(endpoints)) as pool:
        jobs = {pool.submit(parse_feed, name, url): name for name, url in endpoints}
        for future in as_completed(jobs):
            try:
                articles.extend(future.result())
            except Exception as exc:
                errors.append(jobs[future] + ": " + type(exc).__name__)
    cutoff = now.astimezone(timezone.utc) - timedelta(hours=24)
    latest = [a for a in articles if cutoff <= a["published"] <= now.astimezone(timezone.utc) + timedelta(minutes=10)]
    seen, selected, counts = set(), [], {}
    for item in sorted(latest, key=lambda x: (x["publisher"] == "Google 新闻索引", -x["published"].timestamp())):
        normalized = re.sub(r"\W+", "", item["title"].lower())[:90]
        if normalized in seen:
            continue
        seen.add(normalized)
        topic = next((t for t in TOPICS if t[1].search(item["title"])), None)
        if not topic or counts.get(topic[0], 0) >= 2:
            continue
        counts[topic[0]] = counts.get(topic[0], 0) + 1
        selected.append((item, topic))
        if len(selected) == 10:
            break
    # A news shortage is visible in the report. Never backfill old stories as "past 24 hours".
    return [{"event": item["title"], "published": item["published"].astimezone(TZ).strftime("%Y-%m-%d %H:%M 北京时间"),
             "publisher": item["publisher"], "url": item["url"], "topic": topic[0],
             "why": "这条消息涉及" + topic[0] + "，值得核对原文中的规模、时间和落地条件；标题本身不足以确认利润已经变化。",
             "mechanism": topic[2], "horizon": "具体持续时间需由后续订单和财报验证；单条新闻不能证明趋势。",
             "verify": topic[3]} for item, topic in selected], errors


def signed(value: float, digits: int = 2) -> str:
    return f"{value:+.{digits}f}".replace("-", "−")


def indicator_block(key: str, item: dict) -> dict:
    direction = "上升" if item["change"] > 0 else "下降" if item["change"] < 0 else "持平"
    movement = signed(item["change"]) + (" 个百分点" if key in ("us2y", "us10y") else " " + item["unit"])
    explanations = {
        "brent": "Brent 是国际原油定价参考。油价变化可能改变油企每桶收入，也会改变航空、化工及运输的燃料成本；利润还取决于销量、库存与能否转嫁成本。",
        "us2y": "2 年期国债收益率是短期美元资金价格的重要参照。它上行会提高部分融资成本，利率敏感行业的估值也可能受影响。",
        "us10y": "10 年期国债收益率常被用作长期资金定价参照。它上行时，远期利润折回今天的估值可能降低，但企业利润增长可能抵消这种影响。",
        "dxy": "DXY 是美元相对一篮子主要货币的指数。美元走强可能影响人民币汇率、美元债成本及大宗商品报价，实际影响须看企业结算货币。",
        "gold": "这里是真实现货黄金报价，不是黄金 ETF。金价会影响黄金矿企销售收入；矿山成本、产量、套保和汇率决定利润能否同步增长。",
        "sp500": "标普 500 是美国大型上市公司指数。指数涨跌包含估值和盈利预期两部分，单日价格不能说明是哪一种在主导。",
        "nasdaq": "纳斯达克综合指数包含较多科技企业。观察它时应同时核对盈利、资本开支与利率，不能直接把上涨等同于 AI 利润增长。",
        "usdcny": "美元兑人民币数字上升表示一美元可兑换更多人民币。出口收入和进口成本可能同时变化，合同结算币种与套保安排决定净影响。",
    }
    return {"type": "explainer", "title": item["label"], "summary": f"{item['value']:,.2f} {item['unit']}；相对 {item['previousDate']} {direction} {movement}。",
            "paragraphs": [f"数据日期 {item['date']}；来源：{item['provider']}。这是与上一个可用观测日的变化，遇到休市不等于严格的过去 24 小时。",
                           "仅凭价格无法可靠判断这次变化的原因；需要对照同一时段的政策、供需和企业公告，当前不归因。" , explanations[key]],
            "links": [{"title": "查看原始数据", "url": item["source"]}]}


def radar_block(topic, evidence: list[dict]) -> dict:
    name, _, mechanism, verify, samples = topic
    first = evidence[0]
    return {"type": "explainer", "title": name + "：从消息追踪利润，而非追涨幅",
            "summary": "当前线索来自过去 24 小时的公开消息；利润增长仍是假设，须检查原文和后续数据。",
            "paragraphs": ["观察到的事实：" + first["event"] + "（" + first["published"] + "，" + first["publisher"] + "）。标题不提供完整数量和合同条件，不能把它直接写成新增利润。",
                           "可能的收入、成本和利润传导：" + mechanism + "最直接受益与可能被挤压的环节，需要结合每家公司实际业务占比、成本结构与合同判断。",
                           "研究样本（A 股、港股、美股，供核查而非排名或推荐）：" + samples + "。价格是否已提前反映预期，单靠新闻不能可靠判断；应与估值和一致预期比较。",
                           "反证与未来 1–4 周验证：若" + verify + "没有改善，或销量增加却伴随更大降价和费用，本线索应下调。关注 " + verify + "。"],
            "links": [{"title": "本条线索原文", "url": first["url"]}]}


def lesson(indicators: dict) -> dict:
    q = indicators.get("us10y")
    example = (f"本期美国 10 年期国债收益率为 {q['value']:.2f}%（{q['date']}），相对前一观测日变动 {signed(q['change'])} 个百分点。" if q else "以美国 10 年期国债收益率为例；本期该数值未取得，暂不填写具体数字。")
    return {"id": "lesson", "eyebrow": "05 · 每日一课", "title": "金融工程每日一课：折现", "lead": "一句话直觉：未来收到的钱，需要按时间和风险折算成今天的价值。",
            "blocks": [{"type": "explainer", "title": "今天市场里的例子", "summary": example,
                        "paragraphs": ["国债收益率可以作为资金价格的一项参照，企业未来现金流的折现率还包含风险补偿。收益率变动不会机械地等比例改变股价，因为利润预期也会变。",
                                       "必要公式：现值 PV = FV ÷ (1+r)^n。PV 是今天的价值；FV 是 n 期后预计收到的钱；r 是每期折现率；n 是等待期数。",
                                       "很短的练习：假设一年后确定收到 110 元，年折现率为 10%，今天值多少？答案：100 元，因为 110 ÷ 1.10 = 100。折现率越高，同一笔未来收入的今天价值越低。"]}]}


def build_report(indicators: dict, failures: dict, news: list[dict], news_errors: list[str], now: datetime) -> dict:
    today = now.date().isoformat()
    weekend = now.weekday() >= 5
    sources = [{"title": v["label"] + " · " + v["provider"], "url": v["source"], "asOf": v["date"]} for v in indicators.values()]
    sources += [{"title": "新闻 · " + item["publisher"] + " · " + item["event"], "url": item["url"], "asOf": item["published"]} for item in news]
    market_blocks = [indicator_block(key, indicators[key]) for key, _ in INDICATORS if key in indicators]
    if failures:
        market_blocks.append({"type": "notice", "tone": "warning", "title": "缺失的指标", "text": "以下指标未从对应的真实口径获得数据，已留空，不用 ETF 价格代替：" + "、".join(failures) + "。"})
    news_blocks = [{"type": "explainer", "title": str(i) + ". " + n["topic"], "summary": n["event"],
                    "paragraphs": ["发生时间：" + n["published"] + "；发布或索引来源：" + n["publisher"] + "。", n["why"],
                                   "可能影响产业链及收入、成本、利润率、订单或现金流的路径：" + n["mechanism"],
                                   "持续性与验证：" + n["horizon"] + "观察 " + n["verify"] + "。"],
                    "links": [{"title": "阅读消息原文或新闻索引", "url": n["url"]}]} for i, n in enumerate(news, 1)]
    if len(news) < 6:
        news_blocks.insert(0, {"type": "notice", "tone": "warning", "title": "过去 24 小时来源不足", "text": f"仅核实到 {len(news)} 条符合条件的公开消息；不把旧新闻冒充当天新闻。源站不可用数：{len(news_errors)}。"})
    seen_topics = []
    for n in news:
        if n["topic"] not in seen_topics:
            seen_topics.append(n["topic"])
    radar = [radar_block(next(t for t in TOPICS if t[0] == name), [n for n in news if n["topic"] == name]) for name in seen_topics[:4]]
    if len(radar) < 2:
        radar.insert(0, {"type": "notice", "tone": "warning", "title": "产业线索不足", "text": "可核查新闻不足以支持 2 条不同产业的利润假设，本期不填充未经验证的热门概念。"})
    gold = indicators.get("gold")
    gold_fact = f"现货金价 {gold['value']:,.2f} 美元/盎司（{gold['date']}）；相对前一观测日 {signed(gold['changePct'])}%。" if gold else "现货金价本期不可用，不能用黄金 ETF 冒充。"
    pages = [
        {"id": "overview", "eyebrow": "01 · 开篇", "title": "我今天不用自己查指标版", "lead": "先看真实口径与数据日期，再读它怎样可能影响企业赚钱。", "blocks": [
            {"type": "notice", "tone": "neutral", "title": "阅读方法", "text": "行情是事实，利润传导是待检验的条件推论。价格的变动原因无法从价格本身推出；新闻标题未核实的细节不会被写成事实。"},
            {"type": "explainer", "title": "今天先看什么", "summary": f"已取得 {len(indicators)} 个真实指标、过去 24 小时 {len(news)} 条消息。" + ("今天是周末，行情沿用最近可用交易日并逐项标注日期。" if weekend else "每项行情逐项标注最近可用观测日。"),
             "paragraphs": ["美国利率、美元、黄金和原油一起看：它们影响融资成本、以美元计价的收入和原材料成本，但对不同公司利润的方向可能相反。", "今天的研究线索从有时间和链接的消息出发，继续核对订单、售价、毛利率和现金流。"]}]},
        {"id": "markets", "eyebrow": "02 · 数据", "title": "关键指标与传导", "lead": "最新可靠观测值、上一观测日变化、数据时间和影响范围。", "blocks": market_blocks},
        {"id": "news", "eyebrow": "03 · 近 24 小时", "title": "过去 24 小时财经新闻梳理", "lead": "优先选有企业利润传导线索的消息；逐条给出原文和核验方向。", "blocks": news_blocks},
        {"id": "radar", "eyebrow": "04 · 研究", "title": "产业利润增长雷达", "lead": "从需求与成本走到收入、利润和估值，假设须有反证。", "blocks": radar},
        lesson(indicators),
        {"id": "goldminers", "eyebrow": "06 · 专题", "title": "159562 黄金矿企观察", "lead": "一个研究小节；不读取或公布持仓、成本和账户信息。", "blocks": [
            {"type": "explainer", "title": "金价上涨，矿企利润一定上涨吗？", "summary": gold_fact,
             "paragraphs": ["金价抬高未套保黄金的单位销售收入；美元和人民币汇率改变以人民币计价的收入。美国国债收益率可能影响黄金估值，但单日走势无法单独归因。",
                            "矿山的柴油、设备、人工、品位与开采量决定单位成本。原油变贵可能提高能源开支；长期销售合同和套期保值会改变金价传导。",
                            "159562 的价格还受 A 股风险偏好、基金成分与交易溢折价影响。未来核对矿企产量、全部维持成本、套保披露和基金净值；不把 ETF 涨跌当作现货金价。"]}]},
    ]
    if weekend:
        pages.insert(4, {"id": "weekend", "eyebrow": "周末 · 复盘", "title": "本周验证与下周日历", "lead": "周末不伪造开市行情；新闻仍按过去 24 小时核对。", "blocks": [
            {"type": "explainer", "title": "本周发生了什么", "summary": "以各指标最近可用交易日的变化和本期来源为起点。", "paragraphs": ["本期未自动重建完整一周的公告与预测，不能声称一条逻辑已经被验证或证伪。", "下周优先核对央行、统计机构和企业投资者关系页面公布的正式日历；自动源未获取具体日期时不虚构事件。", "最值得验证的产业利润线索见前一栏；关注订单、销量、价格、成本和财报是否兑现。"]}]})
    return {"edition": f"财经晨报 · {today}", "date": f"生成于北京时间 {now:%Y-%m-%d %H:%M}；各数据逐项标注观测日", "reportDate": today,
            "updatedAt": now.isoformat(timespec="seconds"), "status": "published", "title": "从新闻读到产业利润", "subtitle": "真实指标 · 近 24 小时新闻 · 产业利润线索 · 每日一课",
            "intro": "面向正在学习金融的读者：先辨认事实，再追踪收入、成本、利润和反证。公开信息仅供研究。",
            "notification": {"title": f"{today} 财经晨报", "summary": f"{len(indicators)} 项真实指标、{len(news)} 条近 24 小时消息、{len([b for b in radar if b['type']=='explainer'])} 条产业线索；点击阅读因果和反证。"},
            "pages": pages, "sources": sources,
            "quality": {"indicatorCount": len(indicators), "news24hCount": len(news), "radarCount": len([b for b in radar if b["type"] == "explainer"]), "unavailableIndicators": list(failures), "unavailableNewsSources": news_errors}}


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
    items = sorted([entry] + [x for x in index.get("items", []) if x.get("date") != date], key=lambda x: x.get("date", ""), reverse=True)[:120]
    index_path.write_text(json.dumps({"updatedAt": report["updatedAt"], "items": items}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true", help="Write preview/YYYY-MM-DD.json without changing published report or archive")
    args = parser.parse_args()
    now = datetime.now(TZ)
    indicators, failures = collect_indicators()
    news, errors = collect_news(now)
    report = build_report(indicators, failures, news, errors, now)
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
