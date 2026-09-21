#!/usr/bin/env python3
import json
import os
import time
import urllib.request

site = os.environ["SITE_URL"].rstrip("/") + "/"
expected = os.environ["EXPECTED_DATE"]
run_id = os.environ.get("GITHUB_RUN_ID", str(int(time.time())))
headers = {"User-Agent": "finance-morning-brief-deploy-check/1.0", "Cache-Control": "no-cache"}
last_error = "not attempted"
for attempt in range(18):
    try:
        req = urllib.request.Request(f"{site}report.json?run={run_id}-{attempt}", headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
        if data.get("reportDate") == expected and data.get("status") == "published":
            print(f"Live report verified for {expected}")
            break
        last_error = f"published date is {data.get('reportDate')!r}"
    except Exception as exc:
        last_error = type(exc).__name__
    time.sleep(10)
else:
    raise SystemExit(f"Live page verification failed: {last_error}; notification blocked")
