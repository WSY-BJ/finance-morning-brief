import io
import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from daily_delivery import deliver, render

class Response(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *args): self.close()

class DailyDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = datetime(2026,10,27,8,5,tzinfo=ZoneInfo('Asia/Shanghai'))
        self.env = {'SERVERCHAN_SENDKEY':'SCTtest-only','SITE_URL':'https://example.com/'}
        self.state = self.root/'.state/notifications/2026-10-27.json'
        self.calls = []
        self.status = 0
        self.timeout = False
    def save(self, root, path, state):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(state))
    def open(self, request, timeout):
        if isinstance(request,str): raise OSError('site unavailable')
        self.calls.append(request)
        if self.timeout: raise TimeoutError()
        return Response(json.dumps({'code':self.status}).encode())
    def send(self):
        deliver(self.root,self.env,self.now,self.save,self.open)
    def report(self, mode='limited'):
        r={'reportDate':'2026-10-27','quality':{'mode':mode},'pages':[]}
        (self.root/'report.json').write_text(json.dumps(r));return r
    def test_limited_quality_still_sends(self):
        self.report();self.send();self.assertEqual(len(self.calls),1)
        self.assertEqual(json.loads(self.state.read_text())['status'],'accepted')
    def test_missing_report_sends_outage(self):
        self.send();self.assertEqual(json.loads(self.state.read_text())['edition'],'outage')
    def test_stale_report_never_pretends_today(self):
        r=self.report();r['reportDate']='2026-10-26'
        title,body=render(r,'2026-10-27',False,'https://example.com/')
        self.assertIn('更新通知',title);self.assertIn('2026-10-26',body)
        self.assertNotIn('?date=2026-10-27',body)
    def test_accepted_receipt_suppresses_duplicate(self):
        self.send();self.send();self.assertEqual(len(self.calls),1)
    def test_rejected_request_is_retried(self):
        self.status=1
        with self.assertRaises(RuntimeError):self.send()
        self.assertEqual(json.loads(self.state.read_text())['status'],'rejected')
        self.status=0;self.send();self.assertEqual(len(self.calls),2)
    def test_timeout_recovery_waits_ten_minutes(self):
        self.timeout=True
        with self.assertRaises(RuntimeError):self.send()
        self.timeout=False
        with self.assertRaises(RuntimeError):self.send()
        self.assertEqual(len(self.calls),1)
        self.now+=timedelta(minutes=11);self.send();self.assertEqual(len(self.calls),2)
    def test_failed_checkpoint_prevents_network_send(self):
        def fail(*args):raise OSError('push failed')
        with self.assertRaises(OSError):deliver(self.root,self.env,self.now,fail,self.open)
        self.assertEqual(len(self.calls),0)
    def test_empty_radar_and_sports_filtered(self):
        r=self.report();r['pages']=[{'id':'radar','blocks':[{'type':'explainer','title':'今日线索','paragraphs':[]}]},{'id':'news','blocks':[{'type':'explainer','title':'CBA新闻'},{'type':'explainer','title':'央行政策'}]}]
        title,body=render(r,'2026-10-27',False,'https://example.com/')
        self.assertNotIn('CBA',body);self.assertIn('央行政策',body)
    def test_invalid_json_sends_outage(self):
        (self.root/'report.json').write_text('broken');self.send()
        self.assertEqual(json.loads(self.state.read_text())['edition'],'outage')
    def test_missing_key_does_not_claim(self):
        self.env['SERVERCHAN_SENDKEY']=''
        with self.assertRaises(RuntimeError):self.send()
        self.assertFalse(self.state.exists())

if __name__=='__main__':unittest.main()
