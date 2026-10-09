"""Extract article paragraphs without turning source text into investment claims."""
import hashlib
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser

TRUSTED_HOSTS = ('news.cn', 'xinhuanet.com', 'cnstock.com', 'stcn.com', 'gov.cn', 'reuters.com')

def trusted(url):
    p = urllib.parse.urlsplit(url)
    host = (p.hostname or '').lower()
    return p.scheme == 'https' and any(host == h or host.endswith('.' + h) for h in TRUSTED_HOSTS)

class ArticleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.paragraphs = []
        self.current = None
    def handle_starttag(self, tag, attrs):
        if tag in ('meta', 'link', 'img', 'br', 'hr', 'input', 'source', 'wbr'):
            return
        self.stack.append(tag)
        if tag == 'p' and not set(self.stack).intersection(('nav', 'footer', 'header', 'script', 'style', 'aside')):
            self.current = []
    def handle_data(self, data):
        if self.current is not None and not set(self.stack).intersection(('script', 'style', 'nav', 'footer', 'aside')):
            self.current.append(data)
    def handle_endtag(self, tag):
        if tag == 'p' and self.current is not None:
            text = ' '.join(''.join(self.current).split())
            if len(text) >= 50:
                self.paragraphs.append(text)
            self.current = None
        if tag in self.stack:
            self.stack = self.stack[:len(self.stack) - 1 - self.stack[::-1].index(tag)]

def extract(document):
    parser = ArticleParser()
    parser.feed(document)
    return list(dict.fromkeys(parser.paragraphs))

def retrieve(event, now):
    url = event['url']
    # A news index is only a locator: find a publisher article before extraction.
    index = urllib.parse.urlsplit(url)
    if index.scheme == 'https' and index.hostname == 'news.google.com' and index.path.startswith('/rss/articles/'):
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=15) as response:
            final = response.geturl()
            if trusted(final):
                url = final
            else:
                if urllib.parse.urlsplit(final).hostname != 'news.google.com':
                    return dict(event)
                document = response.read(2_000_000).decode('utf-8', errors='replace')
                candidates = re.findall(r'href=[\"\'](https://[^\"\']+)[\"\']', document)
                candidates = [u for u in candidates if trusted(u) and len(urllib.parse.urlsplit(u).path) > 10]
                if len(set(candidates)) != 1:
                    return dict(event)
                url = candidates[0]
    # Unknown publishers cannot be treated as article evidence.
    if not trusted(url):
        return dict(event)
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 FinanceMorningBrief'})
    with urllib.request.urlopen(request, timeout=15) as response:
        final = response.geturl()
        if not trusted(final):
            raise ValueError('untrusted article redirect')
        raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError('article too large')
        document = raw.decode(response.headers.get_content_charset() or 'utf-8', errors='replace')
    paragraphs = extract(document)
    # Demand an actual article and a title anchor; navigation pages are not evidence.
    title_words = re.findall(r'[\u4e00-\u9fff]{4,}|[A-Za-z]{5,}', event['originalTitle'])
    if sum(map(len, paragraphs)) < 300 or not any(w in document for w in title_words):
        raise ValueError('article body or title missing')
    result = dict(event)
    result['articleEvidence'] = {'url': final, 'retrievedAt': now.isoformat(),
        'sha256': hashlib.sha256(raw).hexdigest(), 'paragraphCount': len(paragraphs),
        'excerpt': paragraphs[0][:500]}
    # Retrieval does not grant reviewed status or fabricate causal analysis.
    return result
