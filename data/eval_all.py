# -*- coding: utf-8 -*-
"""用校正版引擎（Python 直跑，不经 GUI）重测三套样本，输出最终指标。

样本：
    域外正样本 labeled_pos.txt（100，Phishing.Database ACTIVE）
    域外负样本 labeled_neg.txt（102，官方/知名/高校/政府站点）
    域内样本   onsite_samples.json（39，仿冒 mku 的五类手法）
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

W = Path(__file__).resolve().parent
sys.path.insert(0, str(W / "build_env"))
sys.path.insert(0, str(W / "build_src"))

import tldextract  # noqa: E402

tldextract.extract = tldextract.TLDExtract(suffix_list_urls=())

from detector.engine import Detector  # noqa: E402

_shared = Detector()


def run_one(item):
    dom = item["domain"]
    url = item.get("url") or ("http://" + dom)
    try:
        r = _shared.detect(url)
        return {"domain": dom, "group": item.get("group", ""), "url": url,
                "level": r.get("level"), "score": r.get("score"),
                "domain_score": r.get("domain_score"), "content_score": r.get("content_score"),
                "reasons": (r.get("reasons") or [])[:3]}
    except Exception as e:
        return {"domain": dom, "group": item.get("group", ""), "url": url,
                "level": "错误", "score": -1, "error": f"{type(e).__name__}: {e}"}


def load(path, group=""):
    out = []
    for line in open(path, encoding="utf-8"):
        d = line.strip()
        if d:
            out.append({"domain": d, "group": group})
    return out


def evaluate(name, rows, label):
    """label: 1 钓鱼 / 0 正常"""
    if label == 1:
        tp = sum(1 for r in rows if r["level"] in ("可疑", "高危"))
        fn = len(rows) - tp
        print("%s: %d 条，检出 %d（%.1f%%），等级分布 %s"
              % (name, len(rows), tp, tp / len(rows) * 100, dist(rows)))
        return {"tp": tp, "fn": fn, "fp": 0, "tn": 0}
    fp = sum(1 for r in rows if r["level"] in ("可疑", "高危"))
    tn = len(rows) - fp
    print("%s: %d 条，误报 %d（%.1f%%），等级分布 %s"
          % (name, len(rows), fp, fp / len(rows) * 100, dist(rows)))
    return {"tp": 0, "fn": 0, "fp": fp, "tn": tn}


def dist(rows):
    d = {}
    for r in rows:
        d[r["level"]] = d.get(r["level"], 0) + 1
    return d


def metrics(tp, fn, fp, tn, tag):
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    acc = (tp + tn) / (tp + fn + fp + tn)
    print("%-18s 精确率 %.2f%% 召回率 %.2f%% F1 %.4f 误报率 %.2f%% 准确率 %.2f%%"
          % (tag, prec * 100, rec * 100, f1, fpr * 100, acc * 100))
    return {"scope": tag, "tp": tp, "fn": fn, "fp": fp, "tn": tn,
            "precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4),
            "false_positive_rate": round(fpr, 4), "accuracy": round(acc, 4)}


pos = load(W / "labeled_pos.txt")
neg = load(W / "labeled_neg.txt")
onsite = json.load(open(W / "onsite_samples.json", encoding="utf-8"))

print("开始检测 %d 条（4 线程）" % (len(pos) + len(neg) + len(onsite)))
res = {"pos": None, "neg": None, "onsite": None}
with ThreadPoolExecutor(max_workers=4) as ex:
    rp = list(ex.map(run_one, pos))
    rn = list(ex.map(run_one, neg))
    ro = list(ex.map(run_one, onsite))

json.dump(rp, open(W / "new_pos_results.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
json.dump(rn, open(W / "new_neg_results.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
json.dump(ro, open(W / "new_onsite_results.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)

print("\n=== 域外（标注集）===")
a = evaluate("正样本", rp, 1)
b = evaluate("负样本", rn, 0)
tp, fn, fp, tn = a["tp"], a["fn"], b["fp"], b["tn"]
m1 = metrics(tp, fn, fp, tn, "口径A 全样本")

pos_d = [r for r in rp if r["level"] != "未知"]
neg_d = [r for r in rn if r["level"] != "未知"]
tp2 = sum(1 for r in pos_d if r["level"] in ("可疑", "高危"))
fn2 = len(pos_d) - tp2
fp2 = sum(1 for r in neg_d if r["level"] in ("可疑", "高危"))
tn2 = len(neg_d) - fp2
m2 = metrics(tp2, fn2, fp2, tn2, "口径B 仅可判定")
print("可判定条数: 正 %d / 负 %d" % (len(pos_d), len(neg_d)))

print("\n=== 域内（39 条仿冒样本）===")
hit = sum(1 for r in ro if r["level"] in ("可疑", "高危"))
print("检出 %d/%d = %.1f%%，等级分布 %s" % (hit, len(ro), hit / len(ro) * 100, dist(ro)))
by_group = {}
for r in ro:
    g = r["group"]; s = by_group.setdefault(g, {"n": 0, "hit": 0})
    s["n"] += 1
    if r["level"] in ("可疑", "高危"):
        s["hit"] += 1
for g, s in by_group.items():
    print("  %-8s %d/%d" % (g, s["hit"], s["n"]))

cnt_bad = sum(1 for r in ro + rp + rn if r["level"] == "错误")
print("\n异常条数:", cnt_bad)
for r in ro + rp + rn:
    if r["level"] == "错误":
        print("  ", r["domain"], r.get("error"))

json.dump({"scope_a": m1, "scope_b": m2,
           "onsite": {"hit": hit, "n": len(ro), "by_group": by_group,
                      "dist": dist(ro)},
           "pos_dist": dist(rp), "neg_dist": dist(rn)},
          open(W / "new_metrics.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("已写入 new_metrics.json")
