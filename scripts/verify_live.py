#!/usr/bin/env python3
"""Verify exact deployed report, archive and assets before any notification."""
import hashlib
import json
import os
import time
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parents[1]
site = os.environ['SITE_URL'].rstrip('/') + '/'
expected = os.environ['EXPECTED_DATE']
files = ['report.json', 'archive/'+expected+'.json', 'archive/index.json', 'app.js', 'index.html', 'style.css']
expected_hashes = {p: hashlib.sha256((root/p).read_bytes()).hexdigest() for p in files}
headers = {'User-Agent':'finance-morning-brief-deploy-check/3.0', 'Cache-Control':'no-cache'}
last_error = 'not attempted'
for attempt in range(18):
    try:
        for path, digest in expected_hashes.items():
            req = urllib.request.Request(site+path+'?check='+str(time.time_ns()), headers=headers)
            with urllib.request.urlopen(req, timeout=15) as response:
                payload = response.read(4_000_000)
            if hashlib.sha256(payload).hexdigest() != digest:
                raise ValueError('deployed content differs: '+path)
        print('Verified exact report, dated archive, history and reader assets for', expected)
        break
    except (OSError, ValueError) as exc:
        last_error = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
    time.sleep(10)
else:
    raise SystemExit('Live verification failed; notification blocked: '+last_error)
