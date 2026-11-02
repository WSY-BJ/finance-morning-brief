# 免费 A 股 / ETF 盘中快照

## ChatGPT 如何查询

用户提问“现在黄金股ETF/大盘/换赛道怎样”时：

1. **直接从连接的 GitHub 仓库读取** `market/status.json` 与 `market/latest.json` （主分支）。
2. 读取 `checked_at_bjt`、`collected_at_bjt` 和每个标的的 `quote_time`，与当前北京时间比较，必须说明快照时间。
3. 交易时间报价超过 **15 分钟** 的数据不再宣称最新行情，超过 **5 分钟** 则提示可能有延迟；行情质量标记 `conflict` 时明确两源不一致，不据此建议具体成交价。
4. 如果调度落后，可通过 GitHub 修改 `market/refresh-request.txt` 触发一次采集，再读取最新文件；或在 Actions 手动运行 `Market quote snapshots (free sources)`。GitHub 启动和执行不保证立即完成。
5. 盘后或节假日应称为“最近一次成交报价/收盘数据”，不要当作实时成交。
6. 使用市场信息前必须和重大事件、成交量、估值与历史行情分别核对；短期波动不能单独构成买卖建议。

## 文件

- `market/latest.json`：最后一次取得至少一笔有效报价时的快照。**失败时不覆盖**，因此每次读取都要检查时间戳。
- `market/status.json`：最新采集尝试的时间、各数据源有效标的数量、错误和警告。**先读这个文件**。
- `market/refresh-request.txt`：修改此文件可以通过 `push` 触发一次更新。
- `scripts/market_quotes.py`：腾讯/新浪双源采集和时效、异常校验。
- `scripts/test_market_quotes.py`：独立离线单元测试。
- `.github/workflows/market-quotes.yml`：交易日北京时间约09:02-15:57每五分钟计划运行。

## 免费来源及限制

- 腾讯财经：`https://qt.gtimg.cn/q=...`
- 新浪财经：`https://hq.sinajs.cn/list=...`

这两个接口属于**非官方公开接口**。并非交易所授权、无延迟承诺或服务级别协议，可能出现限流、拒绝访问、字段变化、假期不更新或访问条件变化。仅保存少量标的的快照，合理控制请求频率，不绕过访问限制。对需要逐笔成交/交易执行的场景使用授权交易终端。

GitHub Actions 定时触发可能排队、延迟或跳过，**五分钟是计划间隔，不是数据更新的保证**。首次运行可能只留下 `status.json`，行情源恢复后才生成 `latest.json`。

## 安全和隔离

无需付费密钥，不接触券商账号、交易密码和方糖 Server酱密钥；作为独立工作流，与每日财经晨报的生成、Pages 发布和微信通知相互隔离。

## 查询地址

- [最新采集结果](https://github.com/WSY-BJ/finance-morning-brief/blob/main/market/latest.json)
- [本次采集状态](https://github.com/WSY-BJ/finance-morning-brief/blob/main/market/status.json)
- [运行记录](https://github.com/WSY-BJ/finance-morning-brief/actions/workflows/market-quotes.yml)

