#!/usr/bin/env python3
"""Content/provenance checks, shared by local tests and publication."""
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from generate_report import validate_event, VERSION

ROOT = Path(__file__).resolve().parents[1]


def validate(report, expected_date=None):
    assert report['reportDate'] == (expected_date or datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat())
    assert report['status'] in ('published', 'preview')
    assert report.get('generatorVersion') == VERSION, 'legacy headline templates rejected'
    assert {'overview','markets','news','radar','lesson','watch'} == {p['id'] for p in report['pages']}
    assert report['quality']['indicatorCount'] >= 5
    now = datetime.fromisoformat(report['updatedAt'])
    events = report.get('events', [])
    for event in events:
        validate_event(event, now)
    reviewed = [e for e in events if e['evidenceLevel'] == 'source-reviewed']
    assert report['quality']['news24hCount'] == len(events) <= 10
    assert report['quality']['reviewedNewsCount'] == len(reviewed)
    radars = [b for p in report['pages'] if p['id'] == 'radar' for b in p['blocks'] if b['type'] == 'explainer' and b.get('title') != '今日线索']
    assert report['quality']['radarCount'] == len(radars) <= 4
    assert len(radars) == len([e for e in reviewed if e.get('profitLead')][:4])
    if report['quality']['mode'] == 'research':
        assert len(reviewed) >= 6 and len(radars) >= 2
    else:
        assert report['quality']['mode'] == 'limited'
    blob = json.dumps(report, ensure_ascii=False).lower()
    for forbidden in ('sendkey','api_key','authorization','private holding','account number'):
        assert forbidden not in blob, 'secret marker in public report'
    for source in report['sources']:
        assert re.match(r'^https://', source.get('url',''))
    news_blocks = next(p['blocks'] for p in report['pages'] if p['id'] == 'news')
    for b in news_blocks:
        if b['type'] == 'explainer':
            assert re.search(r'[\u4e00-\u9fff]', b['title'])
    return True


if __name__ == '__main__':
    report = json.loads((ROOT/'report.json').read_text())
    validate(report)
    assert json.loads((ROOT/'archive'/f"{report['reportDate']}.json").read_text()) == report
    print('Validated:', report['reportDate'], report['quality'])
