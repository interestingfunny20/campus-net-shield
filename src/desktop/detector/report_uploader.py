# decompyle3 version 3.9.3
# Python bytecode version base 3.8.0 (3413)
# Decompiled from: Python 3.13.18 (main, Nov 11 2026, 00:19:14) [MSC v.1944 64 bit (AMD64)]
# Embedded file name: detector\report_uploader.py
"""
检测结果上报模块：桌面工具检测完成后，自动把结果上报到教师后台。
如果后台未启动，静默失败，不影响桌面工具使用。
"""
import json, threading, urllib.request, urllib.error
from urllib.parse import urlparse
SERVER_URL = "http://127.0.0.1:5000/api/report"
TIMEOUT = 2.0

def _host_of(url):
    try:
        return urlparse(url).netloc or url
    except Exception:
        return url


def upload_async(report):
    """异步上报，不阻塞 UI。report 是 detector.engine.detect 返回的 dict。"""
    t = threading.Thread(target=_do_upload, args=(report,), daemon=True)
    t.start()


def _do_upload(report):
    try:
        payload = {'url':(report.get)("url", ""), 
         'host':_host_of(report.get("url", "")), 
         'level':(report.get)("level", ""), 
         'score':(report.get)("score", 0), 
         'reason':("; ".join)(report.get("reasons", [])[:3]), 
         'time':(__import__("datetime").datetime.now().isoformat)(), 
         'source':"desktop"}
        req = urllib.request.Request(SERVER_URL,
          data=(json.dumps(payload).encode("utf-8")),
          headers={"Content-Type": "application/json"},
          method="POST")
        urllib.request.urlopen(req, timeout=TIMEOUT)
    except Exception:
        pass
