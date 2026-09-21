# 全球市场与投资晨报 · GitHub Pages

这是一个面向手机阅读、由 GitHub Actions 独立生成的静态财经晨报。内容只使用公开延迟行情，不连接券商账户，不含个人持仓、账户资料、访问令牌、API 密钥或用户跟踪代码。

## 预览

解压全部文件后，在当前目录运行 `python -m http.server 8000 --bind 127.0.0.1`，电脑浏览器打开 `http://127.0.0.1:8000`。手机在本机打不开这个地址，除非部署到支持 HTTPS 的公开网站。不要直接双击 `index.html` 后期待它能够加载 `report.json`，浏览器的本地文件安全策略可能阻止读取。

## 文件说明

- `index.html`：语义化结构、CSP 安全限制、移动端 viewport。
- `style.css`：无广告/无第三方字体/无外链的简洁样式。
- `app.js`：导航、触摸翻页和安全 JSON 渲染，使用 `textContent` 而非将新闻注入 HTML。
- `report.json`：样刊数据。只有人工核实来源、时间与价格后，才能替换并将 status 改为 live。

## 自动化流程

每天北京时间约 08:03，`.github/workflows/daily-brief.yml` 会依次执行：

1. 从两个公开行情端点交叉容错采集数据；
2. 生成并校验 `report.json`，同时写入 `archive/YYYY-MM-DD.json`；
3. 部署 GitHub Pages，并从公网重新读取当天 JSON；
4. 只有公网内容日期正确时，才使用 Server酱发送一条微信通知。

GitHub 定时任务可能因平台排队晚几分钟。固定网址始终展示最新一期；网页底部保留最近历史晨报入口。

## 密钥配置

唯一需要的密钥是 Server酱 Turbo 的 SendKey，必须保存为 GitHub Actions Secret：`SERVERCHAN_SENDKEY`。工作流仅从环境变量读取，不会写入仓库、网页或正常日志。不要把 SendKey 发到聊天中；泄露后应立即在 Server酱控制台重置。

## 已实现的防护与局限

- 本原型无账户登录、支付、用户输入、遥测/统计、第三方脚本、图像抓取和交易功能；外链只允许 HTTPS 并使用 `noopener noreferrer`。
- 页面不请求除同域 `report.json` 外的任何接口；`report.json` 内容通过纯文本 DOM API 注入，减少恶意新闻文本的脚本注入风险。
- 静态网页不等于绝对安全：托管账户泄露、DNS 劫持、篡改的数据源、第三方微信推送服务及恶意新闻链接仍需生产环境防护。
- GitHub Pages 提供公开 HTTPS 地址；访问稳定性仍会受用户所在地网络环境影响。
