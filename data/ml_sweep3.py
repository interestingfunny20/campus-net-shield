# -*- coding: utf-8 -*-
"""按 v2.3 实际逻辑（白名单跳过 + ML 命中即定级）复算 202 / 39 两套指标"""
import sys, os, json
W = r"C:\Users\MR\Doubao\chats\2026-11-24\new-chat-1\_work"
sys.path.insert(0, os.path.join(W, "build_src"))
sys.path.insert(0, os.path.join(W, "build_env"))

import tldextract
tldextract.extract = tldextract.TLDExtract(suffix_list_urls=())

from detector import ml_detector

print("模型可用:", ml_detector.ml_available())
print("白名单条数:", len(ml_detector._safe_lists()["domains"]))


def level_of(s):
    return "安全" if s <= 30 else ("可疑" if s <= 65 else "高危")


def apply(rows):
    out = []
    for r in rows:
        raw = r.get("score")
        s = float(raw) if isinstance(raw, (int, float)) else 0.0
        base_level = r.get("level") if isinstance(r.get("level"), str) else level_of(s)
        floor, prob = 0.0, 0.0
        if ml_detector.should_use_ml(s, r["url"]):
            floor, prob = ml_detector.ml_score_contribution(r["url"])
        ns = max(s, floor) if (floor > 0.5 and floor > s) else s
        out.append({
            "url": r["url"], "rule_score": s, "rule_level": base_level,
            "score": round(ns, 1), "level": level_of(ns),
            "ml_floor": floor, "ml_prob": round(prob, 4),
            "changed": level_of(ns) != base_level,
        })
    return out


r202 = json.load(open(os.path.join(W, "exe_202_results.json"), encoding="utf-8"))
r39 = json.load(open(os.path.join(W, "exe_onsite_results.json"), encoding="utf-8"))

# 白名单新增的 5 个站点规则分已变化，端到端重跑刷新真实分数
REFRESH = {"http://www.bankcomm.com", "http://www.wanfangdata.com.cn",
           "http://www.stackoverflow.com", "http://www.wikipedia.org",
           "http://www.microsoft.com"}
from detector.engine import Detector
_d = Detector()
for r in r202:
    if r["url"] in REFRESH:
        res = _d.detect(r["url"])
        old = r.get("score")
        r["score"], r["level"] = res["score"], res["level"]
        print("刷新 %-38s %s -> %s (%s)" % (r["url"][:38], old, res["score"], res["level"]))

a202 = apply(r202)
a39 = apply(r39)


def stats(rows, pos_n):
    pos, neg = rows[:pos_n], rows[pos_n:]
    tp = sum(1 for x in pos if x["level"] in ("可疑", "高危"))
    fp = sum(1 for x in neg if x["level"] in ("可疑", "高危"))
    rec = tp / len(pos); prec = tp / (tp + fp) if tp + fp else 0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0
    return dict(TP=tp, FN=len(pos) - tp, FP=fp, TN=len(neg) - fp,
                召回率=round(rec, 4), 精确率=round(prec, 4), F1=round(f1, 4),
                误报率=round(fp / len(neg), 4), 准确率=round((tp + len(neg) - fp) / len(rows), 4))


s = stats(a202, 100)
print("\n【202 条 · v2.3 规则+ML】", s)
print("ML 提升等级条数:", sum(1 for x in a202 if x["changed"]))

hit39 = sum(1 for x in a39 if x["level"] in ("可疑", "高危"))
print("\n【39 条域内 · v2.3】检出 %d/39 = %.1f%%" % (hit39, 100 * hit39 / 39))
for x in a39:
    if x["changed"]:
        print("   提升: %-38s %s(%s) -> %s(%s) prob=%.3f"
              % (x["url"][:38], x["rule_level"], x["rule_score"], x["level"], x["score"], x["ml_prob"]))

fp_rows = [x for x in a202[100:] if x["level"] in ("可疑", "高危")]
if fp_rows:
    print("\n负样本误报:")
    for x in fp_rows:
        print("   %-45s %s 分 prob=%.3f" % (x["url"][:45], x["score"], x["ml_prob"]))

json.dump(a202, open(os.path.join(W, "v23_202.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
json.dump(a39, open(os.path.join(W, "v23_39.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("\n已写出 v23_202.json / v23_39.json")
