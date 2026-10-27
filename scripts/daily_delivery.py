#!/usr/bin/env python3
"""Daily ServerChan delivery, independent of publication quality and job success."""
import json
import os
import re
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo('Asia/Shanghai')
SPORTS = re.compile(r'世界杯|CBA|NBA|意甲|英超|篮球|足球|攀岩|主帅|比分')


def render(report, today, published, site_url):
    current = isinstance(report, dict) and report.get('reportDate') == today
    mode = report.get('quality', {}).get('mode') if current else None
    edition = '财经晨报' if mode == 'research' else '财经晨报·简版' if current else '晨报更新通知'
    title = f'{today} {edition}'
    lines = [title]
    if not current:
        lines += ['今天的晨报生成暂未完成，正在自动重试。', '上次资料日期：' + str((report or {}).get('reportDate', '暂无'))]
    else:
        if mode != 'research':
            lines += ['今日先送达已采集资料；产业研究仍在补充。']
        for page in report.get('pages', []):
            if page.get('id') not in ('markets', 'news', 'radar', 'lesson'):
                continue
            entries = []
            for block in page.get('blocks', []):
                if block.get('type') != 'explainer':
                    continue
                heading = str(block.get('title') or '')
                if page['id'] == 'news' and SPORTS.search(heading):
                    continue
                summary = str(block.get('summary') or '')
                paragraphs = block.get('paragraphs') or []
                if page['id'] == 'news':
                    # Index titles remain labeled as clues; do not imply semantic review.
                    prefix = '线索：' if mode != 'research' else ''
                    text = prefix + heading + ('：' + summary if summary else '')
                else:
                    text = heading + '：' + summary + ' ' + ' '.join(str(p) for p in paragraphs[:2])
                entries.append('• ' + ' '.join(text.split())[:300])
            if entries:
                lines += ['', str(page.get('title') or ''), *entries[:10]]
        missing = report.get('quality', {}).get('unavailableIndicators') or []
        if missing:
            lines += ['数据缺口：' + '、'.join(missing)]
    if published and current:
        url = site_url.rstrip('/') + '/?date=' + today + '#overview'
        lines += ['', f'[阅读今日资料]({url})']
    else:
        lines += ['', '今日网页尚未验证发布，以上文字可直接阅读。', site_url]
    return title[:32], '\n\n'.join(lines)


def checkpoint(root, path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False) + '\n', encoding='utf-8')
    relative = str(path.relative_to(root))
    subprocess.run(['git', 'add', '--', relative], cwd=root, check=True)
    changed = subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=root).returncode
    if changed:
        subprocess.run(['git', 'commit', '-m', f"Daily delivery {state['date']} {state['status']}"], cwd=root, check=True)
        subprocess.run(['git', 'push', 'origin', 'HEAD:main'], cwd=root, check=True)


def deliver(root, env, now, save=checkpoint, opener=urllib.request.urlopen):
    today = now.astimezone(TZ).date().isoformat()
    path = root / '.state' / 'notifications' / f'{today}.json'
    previous = json.loads(path.read_text()) if path.exists() else {}
    if previous.get('status') == 'accepted':
        print('Daily notification already accepted; no duplicate request')
        return
    # A crashed runner may have submitted the request. Wait for the next recovery window.
    if previous.get('status') in ('sending', 'request_unknown') and previous.get('attemptedAt'):
        if now - datetime.fromisoformat(previous['attemptedAt']) < timedelta(minutes=10):
            raise RuntimeError('Previous attempt unresolved; recovery waits ten minutes')
    try:
        report = json.loads((root / 'report.json').read_text())
    except (OSError, ValueError):
        report = {}
    published = False
    site_url = env.get('SITE_URL', 'https://wsy-bj.github.io/finance-morning-brief/')
    if report.get('reportDate') == today:
        try:
            with opener(site_url.rstrip('/') + '/report.json?delivery=' + str(int(now.timestamp())), timeout=12) as response:
                published = json.load(response) == report
        except Exception:
            pass
    title, body = render(report, today, published, site_url)
    key = env.get('SERVERCHAN_SENDKEY', '').strip()
    if not key.startswith('SCT'):
        raise RuntimeError('ServerChan SendKey missing or invalid; no request made')
    state = dict(date=today, status='sending', delivery='unverified', attemptedAt=now.isoformat(),
                 attempt=int(previous.get('attempt', 0)) + 1, edition='current' if report.get('reportDate') == today else 'outage')
    # Persist BEFORE network access. A push failure prevents a potentially untracked send.
    save(root, path, state)
    payload = urllib.parse.urlencode({'title': title, 'desp': body}).encode()
    request = urllib.request.Request(f'https://sctapi.ftqq.com/{key}.send', data=payload, method='POST')
    try:
        with opener(request, timeout=25) as response:
            result = json.load(response)
    except Exception as exc:
        state.update(status='request_unknown', error=type(exc).__name__)
        save(root, path, state)
        raise RuntimeError('Delivery request unresolved; a later recovery run may retry') from None
    if result.get('code') != 0:
        state.update(status='rejected', code=result.get('code'))
        save(root, path, state)
        raise RuntimeError('ServerChan rejected request')
    state.update(status='accepted', acceptedAt=datetime.now(TZ).isoformat())
    save(root, path, state)
    print('ServerChan accepted daily message; client delivery unverified')


def main():
    now = datetime.now(TZ)
    if now.hour < 8:
        print('Prewarm completed; notification window opens at 08:00 Beijing')
        return
    deliver(ROOT, os.environ, now)


if __name__ == '__main__':
    main()
