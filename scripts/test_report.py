import copy
import json
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import generate_report as g
import article_evidence as a
from validate_report import validate

class Regression(unittest.TestCase):
    def test_body_excludes_navigation_and_scripts(self):
        text='企业公告披露本次合同的履约期限、交易金额与付款安排。'*4
        result=a.extract('<nav><p>'+text+'</p></nav><article><p>'+text+'</p><script>'+text+'</script></article>')
        self.assertEqual(result,[text])
    def test_body_deduplicates_paragraphs(self):
        text='本次事件已经发生，公告披露了具体日期、合同对方与交易金额。'*4
        self.assertEqual(a.extract('<p>'+text+'</p><p>'+text+'</p>'),[text])
    def test_source_domain_boundary(self):
        self.assertTrue(a.trusted('https://www.news.cn/finance/article.html'))
        self.assertFalse(a.trusted('https://news.cn.evil.example/article'))
        self.assertFalse(a.trusted('http://www.news.cn/article'))
    def test_index_does_not_become_article_evidence(self):
        event={'url':'https://news.google.com/rss/articles/index'}
        self.assertEqual(a.retrieve(event,datetime.now(g.TZ)),event)
    def setUp(self):
        self.now=datetime(2026,10,9,10,45,tzinfo=ZoneInfo('Asia/Shanghai'))
        self.editorial=json.loads((g.ROOT/'editorial/2026-10-09.json').read_text())
        old=json.loads((g.ROOT/'scripts/fixture_2026_10_09.json').read_text())
        self.indicators={}
        # Actual archived indicator values are parsed without making new network requests.
        for key,p in zip([k for k,_ in g.INDICATORS], next(p['blocks'] for p in old['pages'] if p['id']=='markets')):
            if p['type']!='explainer': continue
            import re
            value=float(re.search(r'[\d,]+\.\d+',p['summary'])[0].replace(',',''))
            dates=re.findall(r'2026-\d\d-\d\d',p['summary']+' '+p['paragraphs'][0])
            self.indicators[key]=dict(label=p['title'],value=value,previousValue=value,change=0,changePct=0,previousDate=dates[0],date=dates[1],unit='参考值',provider='归档回归样本',source=p['links'][0]['url'])
    def report(self):
        return g.build_report(self.indicators,{},self.editorial['events'],[],self.now,self.editorial)
    def test_flock_has_no_gpu_transmission(self):
        r=self.report(); n=next(b for p in r['pages'] if p['id']=='news' for b in p['blocks'] if 'Flock' in b.get('title',''))
        for wrong in ('GPU','光模块','英伟达','存储'):
            self.assertNotIn(wrong,json.dumps(n,ensure_ascii=False))
        self.assertEqual(r['quality']['radarCount'],0)
        self.assertTrue(validate(r,'2026-10-09'))
    def test_unreviewed_profit_rejected(self):
        n=copy.deepcopy(self.editorial['events'][0]);n['analysis']='订单增长'
        with self.assertRaises(AssertionError):g.validate_event(n,self.now)
    def test_english_title_rejected(self):
        n=copy.deepcopy(self.editorial['events'][0]);n['event']='AI startup layoffs'
        with self.assertRaises(AssertionError):g.validate_event(n,self.now)
    def test_old_and_duplicate_facts_removed(self):
        n=copy.deepcopy(self.editorial['events'][0]);old=copy.deepcopy(n);old['published']='2026-10-01T08:00:00+08:00'
        self.assertEqual(len(g.select_facts([n,n,old],self.now)),1)
    def test_company_needs_article_evidence(self):
        n=copy.deepcopy(self.editorial['events'][0]);n.update(evidenceLevel='source-reviewed',facts='事实',analysis='假设',verify='核对',invalidate='反证')
        with self.assertRaises(AssertionError):g.validate_event(n,self.now)
    def test_lesson_progression(self):
        nextday=datetime(2026,10,10,8,tzinfo=g.TZ)
        self.assertNotEqual(g.lesson(self.indicators,self.now)['title'],g.lesson(self.indicators,nextday)['title'])
    def test_no_swipe_listeners(self):
        s=(g.ROOT/'app.js').read_text()
        self.assertNotIn("addEventListener('touch",s)
        self.assertIn("byId('next').addEventListener('click'",s)
    def test_old_template_report_rejected(self):
        r=self.report();r['generatorVersion']=2
        with self.assertRaises(AssertionError):validate(r,'2026-10-09')

if __name__=='__main__':unittest.main()
