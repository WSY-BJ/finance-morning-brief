"""Offline tests: no network and no paid APIs."""
import unittest
from datetime import datetime, timezone, timedelta
from scripts.market_quotes import (
    BJT, WATCHLIST, classify_time, collect, combine_quotes, parse_sina, parse_tencent
)


def make_tencent(symbol="sz159562", price="1.600", time="20261102100000"):
    f = [""] * 53
    f[0], f[1], f[2] = "51", "测试黄金股ETF", symbol[2:]
    f[3], f[4], f[5] = price, "1.700", "1.650"
    f[30], f[31], f[32] = time, "-0.1", "-5.88"
    f[33], f[34] = "1.68", "1.58"
    f[36], f[37] = "15000", "210.6"
    return 'v_%s="%s";' % (symbol, "~".join(f))


def make_sina(symbol="sz159562", price="1.600", time="10:00:02"):
    f = [""] * 34
    f[:10] = ["测试黄金股ETF", "1.650", "1.700", price, "1.680", "1.580",
              "1.600", "1.601", "1500000", "2106000"]
    f[30], f[31] = "2026-11-02", time
    return 'var hq_str_%s="%s";' % (symbol, ",".join(f))


class TestMarketQuotes(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 2, 10, 0, 20, tzinfo=BJT)

    def test_tencent_schema_time_and_money(self):
        q = parse_tencent(make_tencent())["sz159562"]
        self.assertEqual(q["price"], 1.6)
        self.assertEqual(q["previous_close"], 1.7)
        self.assertEqual(q["quote_time"], "2026-11-02T10:00:00+08:00")
        self.assertAlmostEqual(q["turnover_cny"], 2106000)
        self.assertAlmostEqual(q["change_percent"], -5.8824)

    def test_sina_schema(self):
        q = parse_sina(make_sina())["sz159562"]
        self.assertEqual(q["price"], 1.6)
        self.assertEqual(q["quote_time"], "2026-11-02T10:00:02+08:00")

    def test_garbled_quote_rejected(self):
        self.assertEqual(parse_tencent(make_tencent(price="0")), {})
        self.assertEqual(parse_tencent("v_sz159562=\"1~ab\";"), {})
        self.assertEqual(parse_sina(make_sina(price="NaN")), {})

    def test_crosscheck_and_conflicts(self):
        a = parse_tencent(make_tencent())
        b = parse_sina(make_sina())
        quotes, issues = combine_quotes(a, b, self.now)
        self.assertEqual(quotes[0]["quality"], "cross_checked")
        self.assertEqual(quotes[0]["symbol"], "sz159562")
        b = parse_sina(make_sina(price="1.8"))
        quotes, issues = combine_quotes(a, b, self.now)
        self.assertEqual(quotes[0]["quality"], "conflict")
        self.assertTrue(any("disagree" in x for x in issues))

    def test_old_and_future_quotes(self):
        old = parse_tencent(make_tencent(time="20261030150000"))
        q, issues = combine_quotes(old, {}, self.now)
        self.assertEqual(q[0]["quality"], "stale")
        future = parse_tencent(make_tencent(time="20261103100000"))
        q, _ = combine_quotes(future, {}, self.now)
        self.assertEqual(q, [])

    def test_weekends_and_lunch(self):
        self.assertEqual(classify_time(self.now), "possible_trading_session")
        self.assertEqual(classify_time(datetime(2026, 11, 2, 12, 0, tzinfo=BJT)), "lunch_break")
        self.assertEqual(classify_time(datetime(2026, 11, 1, 10, 0, tzinfo=BJT)), "weekend")

    def test_secondary_only_works_and_status(self):
        def requester(url, referer):
            if "qt.gtimg" in url:
                raise OSError("provider down")
            return make_sina()
        snap, status = collect(now=self.now, requester=requester)
        self.assertEqual(status["health"], "partial")
        self.assertEqual(status["providers"]["sina"], 1)
        self.assertEqual(status["good_quote_count"], 1)
        self.assertEqual(snap["quotes"][0]["source"], "sina")
        self.assertTrue(status["errors"])

    def test_all_down_no_fake_price(self):
        def requester(url, referer):
            raise OSError("no internet")
        snap, status = collect(now=self.now, requester=requester)
        self.assertEqual(status["health"], "failed")
        self.assertEqual(status["good_quote_count"], 0)
        self.assertEqual(snap["quotes"], [])


if __name__ == "__main__":
    unittest.main()
