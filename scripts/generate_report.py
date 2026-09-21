#!/usr/bin/env python3
"""Build the daily public-market brief without private account data."""
from __future__ import annotations

import csv
from concurrent.futures import ThreadPoolExecutor
import io
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Asia/Shanghai")
UA = "finance-morning-brief/1.0 (+https://github.com/WSY-BJ/finance-morning-brief)"
ASSETS = [
    ("SPY", "标普500 ETF", "spy.us"),
    ("QQQ", "纳指100 ETF", "qqq.us"),
    ("FXI", "中国大盘股 ETF", "fxi.us"),
    ("EEM", "新兴市场 ETF", "eem.us"),
    ("TLT", "长期美债 ETF", "tlt.us"),
    ("GLD", "黄金 ETF", "gld.us"),
    ("USO", "原油 ETF", "uso.us"),
]


def get_text(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/csv,application/json;q=0.9,*/*;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.read().decode("utf-8-sig")


def stooq_quote(ticker: str, stooq_symbol: str) -> dict:
    end = datetime.now(TZ).date()
    start = end - timedelta(days=20)
    url = "https://stooq.com/q/d/l/?" + urllib.parse.urlencode({"s": stooq_symbol, "d1": start.strftime("%Y%m%d"), "d2": end.strftime("%Y%m%d"), "i": "d"})
    rows = [r for r in csv.DictReader(io.StringIO(get_text(url))) if r.get("Close") not in (None, "", "N/D")]
    if len(rows) < 2:
        raise RuntimeError(f"{ticker}: Stooq returned fewer than two rows")
    prev, latest = rows[-2], rows[-1]
    close, previous = float(latest["Close"]), float(prev["Close"])
    return {"ticker": ticker, "date": latest["Date"], "close": close, "changePct": (close / previous - 1) * 100,
            "high": float(latest["High"]), "low": float(latest["Low"]), "provider": "Stooq",
            "source": f"https://stooq.com/q/?s={stooq_symbol}"}


def yahoo_quote(ticker: str) -> dict:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}?range=10d&interval=1d"
    result = json.loads(get_text(url))["chart"]["result"][0]
    timestamps, quote = result["timestamp"], result["indicators"]["quote"][0]
    rows = []
    for i, ts in enumerate(timestamps):
        close = quote["close"][i]
        if close is not None:
            rows.append((ts, float(close), quote["high"][i], quote["low"][i]))
    if len(rows) < 2:
        raise RuntimeError(f"{ticker}: Yahoo returned fewer than two rows")
    prev, latest = rows[-2], rows[-1]
    return {"ticker": ticker, "date": datetime.fromtimestamp(latest[0], TZ).date().isoformat(), "close": latest[1],
            "changePct": (latest[1] / prev[1] - 1) * 100, "high": float(latest[2]), "low": float(latest[3]),
            "provider": "Yahoo Finance", "source": f"https://finance.yahoo.com/quote/{ticker}/"}


def get_quote(ticker: str, stooq_symbol: str) -> dict:
    errors = []
    for fn, args in ((stooq_quote, (ticker, stooq_symbol)), (yahoo_quote, (ticker,))):
        try:
            return fn(*args)
        except Exception as exc:
            errors.append(type(exc).__name__)
            time.sleep(0.5)
    raise RuntimeError(f"{ticker}: all public quote sources failed ({', '.join(errors)})")


def fmt_pct(value: float) -> str:
    return f"{value:+.2f}%".replace("-", "−")


def build_report(quotes: list[dict]) -> dict:
    now = datetime.now(TZ)
    today = now.date().isoformat()
    by_ticker = {q["ticker"]: q for q in quotes}
    best = max(quotes, key=lambda q: q["changePct"])
    worst = min(quotes, key=lambda q: q["changePct"])
    latest_market_date = max(q["date"] for q in quotes)
    title = f"{best['ticker']}领涨，{worst['ticker']}相对承压"
    summary = f"最近交易日{best['ticker']}上涨{abs(best['changePct']):.2f}%，表现最强；{worst['ticker']}变动{fmt_pct(worst['changePct'])}。"
    names = {ticker: name for ticker, name, _ in ASSETS}
    metrics = [{"label": f"{q['ticker']} · {names[q['ticker']]}", "value": f"{q['close']:.2f}",
                "note": f"{fmt_pct(q['changePct'])} · {q['low']:.2f}–{q['high']:.2f}"} for q in quotes]
    risk_on = by_ticker["QQQ"]["changePct"] - by_ticker["TLT"]["changePct"]
    style_text = "成长资产相对占优" if risk_on > 0 else "防御资产相对占优"
    return {
        "edition": f"自动晨报 · {today}", "date": f"生成于北京时间 {now:%Y-%m-%d %H:%M}；行情截至 {latest_market_date}",
        "reportDate": today, "updatedAt": now.isoformat(timespec="seconds"), "status": "published", "title": title,
        "subtitle": "全球财经 · 跨资产研究 · 金融工程每日一课",
        "intro": "本期由独立 GitHub Actions 流水线采集公开行情生成，不连接交易账户，不包含个人持仓。",
        "notification": {"title": f"{today} 财经晨报", "summary": summary},
        "pages": [
            {"id":"overview","eyebrow":"01 · 开篇","title":"晨间速览","lead":"先看价格，再看跨资产关系；单日变化不等于趋势。","blocks":[
                {"type":"notice","tone":"neutral","title":"数据说明","text":"价格来自公开延迟行情；若核心数据采集或在线校验失败，本期不会发布，也不会发送微信通知。"},
                {"type":"bullets","title":"今日三条","items":[summary, f"风格：QQQ 相对 TLT 的当日差值为 {risk_on:+.2f} 个百分点，{style_text}。", "方法：ETF 价格不是指数点位、现货价格或期货结算价，比较前需统一口径。"]},
                {"type":"chain","title":"研究顺序","items":["价格变化","宏观证据","盈利与现金流","估值","风险情景"]}]},
            {"id":"markets","eyebrow":"02 · 市场","title":"公开市场快照","lead":"价格单位为美元；涨跌幅相对上一交易日收盘。","blocks":[
                {"type":"metricGrid","title":"最近交易日","items":metrics},
                {"type":"bullets","title":"观察要点","items":[f"权益：SPY {fmt_pct(by_ticker['SPY']['changePct'])}，QQQ {fmt_pct(by_ticker['QQQ']['changePct'])}。", f"跨资产：TLT {fmt_pct(by_ticker['TLT']['changePct'])}，GLD {fmt_pct(by_ticker['GLD']['changePct'])}，USO {fmt_pct(by_ticker['USO']['changePct'])}。", f"区域：FXI {fmt_pct(by_ticker['FXI']['changePct'])}，EEM {fmt_pct(by_ticker['EEM']['changePct'])}。"]}]},
            {"id":"radar","eyebrow":"03 · 研究","title":"跨资产观察","lead":"研究框架面向公开市场，不针对任何个人账户。","blocks":[
                {"type":"research","title":"权益与久期","thesis":"比较 QQQ 与 TLT，观察利率敏感资产之间的相对变化。","verify":"收益率曲线、盈利预期、市场宽度与成交量。","risk":"单日价格噪声不能证明宏观因果。"},
                {"type":"research","title":"黄金与原油","thesis":"区分避险、实际利率和供需冲击。","verify":"美元、实际收益率、库存与资金流。","risk":"ETF 结构与跟踪误差可能放大偏离。"},
                {"type":"research","title":"中国与新兴市场","thesis":"比较 FXI 与 EEM，观察区域风险偏好。","verify":"汇率、盈利预期、政策与资金流。","risk":"ETF 成分与本地指数并不完全一致。"}]},
            {"id":"lesson","eyebrow":"04 · 每日一课","title":"相关不等于因果","lead":"两类资产同向或反向变化，只是研究起点。","blocks":[
                {"type":"formula","title":"相关系数","expression":"ρ(X,Y) = Cov(X,Y) ÷ (σX · σY)","note":"相关系数描述线性共同变化，不证明 X 导致 Y；样本区间改变，结果也可能改变。"},
                {"type":"quiz","title":"30秒自测","question":"黄金上涨且美元下跌，能否仅凭一天数据断定美元下跌导致黄金上涨？","answer":"不能。还需控制利率、风险偏好、事件冲击等变量，并使用更长样本验证。"}]},
            {"id":"watch","eyebrow":"05 · 清单","title":"下一次更新看什么","lead":"固定网址提供最新晨报，历史入口用于推送失败时回看。","blocks":[
                {"type":"bullets","title":"公开观察清单","items":["主要央行政策与利率预期。","通胀、就业、消费数据是否偏离预期。","指数上涨是否集中于少数权重股。","黄金、原油变化是否得到利率和供需数据支持。"]},
                {"type":"notice","tone":"neutral","title":"隐私边界","text":"本站没有登录、支付、交易或统计功能；仓库不含账户信息、私人持仓、Cookie、访问令牌或 API 密钥。"}]}
        ],
        "sources": [{"title": f"{q['ticker']} · {q['provider']}", "url": q["source"], "asOf": q["date"]} for q in quotes]
    }


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
    items = [entry] + [x for x in index.get("items", []) if x.get("date") != date]
    items = sorted(items, key=lambda x: x.get("date", ""), reverse=True)[:120]
    index_path.write_text(json.dumps({"updatedAt": report["updatedAt"], "items": items}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {ticker: pool.submit(get_quote, ticker, stooq_symbol) for ticker, _, stooq_symbol in ASSETS}
        quotes = [futures[ticker].result() for ticker, _, _ in ASSETS]
    required = {"SPY", "QQQ", "GLD", "USO"}
    if not required.issubset({q["ticker"] for q in quotes}):
        raise SystemExit("Core public-market data is incomplete; refusing to publish")
    report = build_report(quotes)
    write_outputs(report)
    print(f"Generated {report['reportDate']} from {len(quotes)} public instruments")


if __name__ == "__main__":
    main()
