# -*- coding: utf-8 -*-
"""端到端抽验：Python 直接跑 Detector，比对 v23 复算值"""
import sys, os, json
HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(PKG, "01_检测程序", "源码"))

import tldextract
tldextract.extract = tldextract.TLDExtract(suffix_list_urls=())

from detector.engine import Detector
from detector import ml_detector

d = Detector()
print("ML 可用:", ml_detector.ml_available())

expect = {x["url"]: x for x in json.load(open(os.path.join(HERE, "v23_202.json"), encoding="utf-8"))}
onsite = {x["url"]: x for x in json.load(open(os.path.join(HERE, "v23_39.json"), encoding="utf-8"))}

# 抽 8 条 ML 提升过的正样本 + 3 条负样本 + 2 条域内
sample = [u for u, x in expect.items() if x["ml_floor"] > 0][:8]
sample += [u for u in expect if "baidu" in u or "gov.cn" in u][:3]
sample += [u for u in onsite if "login-verify" in u or "evil" in u][:2]

print("抽检 %d 条\n" % len(sample))
for u in sample:
    r = d.detect(u)
    ref = expect.get(u) or onsite.get(u)
    ref_score = ref["score"] if ref else None
    flag = "一致" if ref and abs(r["score"] - ref_score) < 0.6 else "差异"
    print("%-46s 实跑=%s(%s) 期望=%s | %s" % (u[:46], r["score"], r["level"], ref_score, flag))
    for reason in r.get("reasons", []):
        if "ML" in reason:
            print("        ", reason)
